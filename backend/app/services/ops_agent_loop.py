"""
OpsAgentLoop - AI 运维助手核心引擎

负责：多轮对话推理、工具调用执行、命令确认等待、上下文压缩、会话标题生成。
每个 OpsSession 对应一个 OpsAgentLoop 实例，在内存中维护对话上下文。
"""
import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import AsyncIterator, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.redis import get_redis
from app.core.database import async_session as AsyncSessionLocal
from app.models.ops_session import OpsSession
from app.models.ops_message import OpsMessage
from app.models.setting import Setting
from app.models.host import Host
from app.models.ai_operation_log import AIOperationLog
from app.services.approval_service import ApprovalService
from app.tools import tool_registry
from app.tools.base import ToolEventType
from app.tools.context import ToolContext
from app.tools.safety import SafetyChecker

logger = logging.getLogger(__name__)

# Redis channel 前缀
CMD_TO_AGENT_CHANNEL = "cmd_to_agent:"      # 后端 → Agent Worker
CMD_RESULT_CHANNEL = "cmd_result:"          # Agent Worker → OpsAgentLoop
OPS_WS_CHANNEL = "ops_ws:"                  # OpsAgentLoop → 前端 Worker

# 上下文压缩阈值（token 数超过此值触发压缩）
COMPACTION_THRESHOLD = 40000
# 命令确认超时（秒）
COMMAND_CONFIRM_TIMEOUT = 60

OPS_AI_BASE_URL_KEY = "ops_ai_base_url"
OPS_AI_MODEL_KEY = "ops_ai_model"
OPS_AI_API_KEY_KEY = "ops_ai_api_key"
OPS_AI_MAX_TOKENS_KEY = "ops_ai_max_tokens"
OPS_AI_EXTRA_CONTEXT_KEY = "ops_ai_extra_context"
OPS_AI_CONFIGS_V2_KEY = "ops_ai_configs_v2"
OPS_AI_DEFAULT_ID_KEY = "ops_ai_default_config_id"

# ─── Tool Schemas（从 ToolRegistry 动态生成）─────────────────────────────────
# 旧的硬编码 TOOLS 列表已移除，改用 tool_registry.get_openai_schemas()
TOOL_EXECUTION_TIMEOUT = 300  # 工具执行超时秒数


SYSTEM_PROMPT = """你是 VigilOps AI 运维助手，一个专业的 Linux/云原生运维专家。

你的工作方式：
1. 理解用户描述的问题，通过工具调用收集信息
2. 优先使用 list_hosts 工具推断用户意图中的目标主机
3. 识别到相关中间件问题时，主动调用 load_skill 加载对应技能知识
4. 生成诊断命令时，使用 execute_command 工具（命令需用户确认后才执行）
5. 多步骤排障时，用 update_todo 维护任务清单
6. 信息不足时，用 ask_user 主动提问
7. 得出结论时，调用 provide_conclusion 结束本轮诊断

注意事项：
- 每次只生成一条 execute_command，等待结果后再决定下一步
- 命令要简洁精准，避免产生大量输出（使用 head/tail/grep 过滤）
- 用中文与用户交流
"""


class OpsAgentLoop:
    """AI Agent Loop 引擎，每个 OpsSession 对应一个实例。"""

    def __init__(self, session_id: str, user_id: int):
        self.session_id = session_id
        self.user_id = user_id
        # 内存中的对话上下文（OpenAI messages 格式）
        self._context: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
        # 标记是否已从 DB 回放历史消息
        self._context_loaded = False
        # 统一审批/问答等待服务
        self._approval_service = ApprovalService(self._update_message_content)
        # 同一 session 全局串行推理锁（跨多个 WebSocket 连接也生效）
        self._run_lock = asyncio.Lock()
        # 统一安全层（延迟初始化，等 Redis 可用）
        self._safety_checker: SafetyChecker | None = None

    # ─── 公开接口 ──────────────────────────────────────────────────────────────

    async def run(
        self,
        user_message: str,
        host_id: Optional[int] = None,
        ai_config_id: Optional[str] = None,
        use_deep_thinking: bool = False,
    ) -> AsyncIterator[dict]:
        """主推理循环，yield 推送事件给前端。"""
        async with self._run_lock:
            runtime_cfg = await self._load_ai_runtime_config(
                ai_config_id=ai_config_id,
                feature_key="ops_assistant",
            )
            runtime_cfg["use_deep_thinking"] = bool(
                use_deep_thinking and runtime_cfg.get("supports_deep_thinking")
            )
            await self._ensure_context_loaded()
            if host_id:
                await self._attach_target_host_context(host_id)
            # 持久化用户消息
            await self._save_message("user", "text", {"text": user_message})
            self._context.append({"role": "user", "content": user_message})

            # 第一次对话时异步生成标题
            session = await self._get_session()
            if session and not session.title:
                asyncio.create_task(self._generate_title(user_message))

            # 检查是否需要压缩
            compaction_threshold = max(8000, int(runtime_cfg.get("allowed_context_tokens", 120000) * 0.8))
            if session and session.token_count > compaction_threshold:
                async for event in self._compact_context():
                    yield event

            # 推理循环
            async for event in self._inference_loop(runtime_cfg):
                yield event

    async def handle_command_confirm(self, message_id: str, action: str):
        """处理前端命令确认/拒绝。action: 'confirm' | 'reject'"""
        await self.handle_approval_reply(
            message_id=message_id,
            action=action,
            request_type="command_request",
        )

    async def handle_ask_user_answer(self, message_id: str, answer: str):
        """处理前端 ask_user 回答。"""
        await self.handle_approval_reply(
            message_id=message_id,
            action="answer",
            answer=answer,
            request_type="ask_user",
        )

    async def handle_approval_reply(
        self,
        message_id: str,
        action: str,
        answer: Optional[str] = None,
        request_type: Optional[str] = None,
    ):
        """统一处理审批/问答回复。"""
        await self._approval_service.resolve(
            message_id=message_id,
            action=action,
            answer=answer,
            request_type=request_type,
        )

    # ─── 推理循环 ──────────────────────────────────────────────────────────────

    async def _inference_loop(self, runtime_cfg: dict) -> AsyncIterator[dict]:
        """多轮推理，直到 AI 不再调用工具或调用 provide_conclusion。"""
        max_rounds = 20  # 防止无限循环
        for _ in range(max_rounds):
            # 调用 AI API
            response_text = ""
            reasoning_text = ""
            tool_calls = []

            async for chunk in self._call_api_stream(runtime_cfg):
                if chunk.get("type") == "text_delta":
                    response_text += chunk["delta"]
                    yield {"event": "text_delta", "delta": chunk["delta"]}
                elif chunk.get("type") == "reasoning_delta":
                    reasoning_text += chunk["delta"]
                    yield {"event": "reasoning_delta", "delta": chunk["delta"]}
                elif chunk.get("type") == "tool_calls":
                    tool_calls = chunk["tool_calls"]

            # 保存 AI 文本响应
            if response_text or reasoning_text:
                await self._save_message("assistant", "text", {
                    "text": response_text,
                    "reasoning": reasoning_text,
                })

            # 没有工具调用，推理结束
            if not tool_calls:
                if response_text or reasoning_text:
                    self._context.append({
                        "role": "assistant",
                        "content": response_text,
                        "reasoning": reasoning_text or None,
                    })
                yield {"event": "done"}
                return

            # 将本轮 assistant 响应（文字 + tool_calls）合并成一条消息追加到上下文
            # 注意：不能拆成两条 assistant 消息，否则 API 会报 400
            self._context.append({
                "role": "assistant",
                "content": response_text or None,
                "tool_calls": tool_calls,
            })

            # 执行所有工具调用
            should_stop = False
            for tc in tool_calls:
                tool_name = tc["function"]["name"]
                try:
                    arguments = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    arguments = {}
                tool_call_id = tc["id"]
                msg_id = str(uuid.uuid4())

                # 推送工具开始事件
                yield {"event": "tool_start", "message_id": msg_id,
                       "tool_name": tool_name, "arguments": arguments}
                await self._save_message("assistant", "tool_call", {
                    "tool_name": tool_name, "arguments": arguments, "status": "running"
                }, tool_call_id=tool_call_id)

                # 执行工具（async generator，支持中途 yield 事件）
                result = None
                stop = False
                async for item in self._execute_tool(
                    tool_name, arguments, msg_id, tool_call_id
                ):
                    if item.get("__type") == "__result":
                        result = item["result"]
                        stop = item["stop"]
                    else:
                        yield item

                if stop:
                    should_stop = True

                # 将工具结果追加到上下文
                self._context.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": json.dumps(result, ensure_ascii=False),
                })

                # 仅在 tool 消息追加后再注入额外 system 上下文，避免打断
                # assistant(tool_calls) -> tool 的协议顺序。
                if (
                    tool_name == "load_skill"
                    and isinstance(result, dict)
                    and result.get("loaded")
                    and result.get("skill_name")
                ):
                    self._context.append({
                        "role": "system",
                        "content": (
                            f"【已加载技能：{result['skill_name']}】\n\n"
                            f"{result.get('skill_content', '')}"
                        ),
                    })

                # 推送工具完成事件
                yield {"event": "tool_done", "message_id": msg_id,
                       "tool_name": tool_name, "result": result}
                await self._save_message("tool", "tool_result", {
                    "tool_name": tool_name, "result": result, "error": None
                }, tool_call_id=tool_call_id)

            if should_stop:
                yield {"event": "done"}
                return

        yield {"event": "done"}

    # ─── 工具执行 ──────────────────────────────────────────────────────────────

    async def _get_safety_checker(self) -> SafetyChecker:
        """延迟初始化 SafetyChecker（需要 Redis 连接）。"""
        if self._safety_checker is None:
            redis = await get_redis()
            self._safety_checker = SafetyChecker(redis=redis)
        return self._safety_checker

    def _get_tools_schema(self) -> list[dict]:
        """从 ToolRegistry 动态获取工具 schema 列表。"""
        return tool_registry.get_openai_schemas()

    async def _execute_tool(
        self, tool_name: str, arguments: dict, msg_id: str, tool_call_id: str
    ):
        """
        通过 ToolRegistry 调度工具执行（async generator）。
        自动包装审计日志 + 执行遥测。
        yield 普通事件 dict，最后 yield {"__type": "__result", "result": ..., "stop": bool}
        """
        tool = tool_registry.get(tool_name)
        if not tool:
            result = {"error": f"Unknown tool: {tool_name}"}
            yield {"event": "tool_error", "message_id": msg_id,
                   "tool_name": tool_name, "error": result["error"]}
            yield {"__type": "__result", "result": result, "stop": False}
            return

        # 构建 ToolContext
        redis = await get_redis()
        safety_checker = await self._get_safety_checker()
        ctx = ToolContext(
            session_id=self.session_id,
            user_id=self.user_id,
            db_session_factory=AsyncSessionLocal,
            redis=redis,
            safety_checker=safety_checker,
            approval_service=self._approval_service,
            save_message=self._save_message,
            context_messages=self._context,
            caller="ops_assistant",
        )

        # 执行工具（带超时保护 + 审计日志 + 遥测）
        start_time = datetime.now(timezone.utc)
        result = None
        should_stop = False
        has_result = False
        error_msg = None

        try:
            async for event in asyncio.wait_for(
                self._consume_tool_events(tool, arguments, ctx, msg_id),
                timeout=TOOL_EXECUTION_TIMEOUT,
            ):
                if event.get("__type") == "__result":
                    result = event["result"]
                    should_stop = event.get("stop", False)
                    has_result = True
                else:
                    yield event

        except asyncio.TimeoutError:
            error_msg = f"工具 {tool_name} 执行超时（{TOOL_EXECUTION_TIMEOUT}秒）"
            logger.error(error_msg)
            result = {"error": error_msg}
            yield {"event": "tool_error", "message_id": msg_id,
                   "tool_name": tool_name, "error": error_msg}

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Tool {tool_name} failed: {e}", exc_info=True)
            result = {"error": error_msg}
            yield {"event": "tool_error", "message_id": msg_id,
                   "tool_name": tool_name, "error": error_msg}

        # 兜底：如果工具未 yield RESULT，补一个空结果
        if not has_result and result is None:
            result = {"error": "Tool did not produce a result"}

        # 遥测：记录工具执行指标
        duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
        try:
            async with AsyncSessionLocal() as db:
                log = AIOperationLog(
                    user_id=self.user_id,
                    session_id=self.session_id,
                    request_id=tool_call_id,
                    host_id=arguments.get("host_id"),
                    host_name=arguments.get("host_name", ""),
                    command=f"tool:{tool_name}",
                    reason=json.dumps(arguments, ensure_ascii=False)[:500],
                    exit_code=0 if error_msg is None else -1,
                    duration_ms=duration_ms,
                    status="success" if error_msg is None else "failed",
                )
                db.add(log)
                await db.commit()
        except Exception:
            logger.warning("Failed to write tool telemetry for %s", tool_name, exc_info=True)

        yield {"__type": "__result", "result": result, "stop": should_stop}

    async def _consume_tool_events(self, tool, arguments, ctx, msg_id):
        """消费工具的 ToolEvent 流，转换为前端事件格式。"""
        async for event in tool.execute(arguments, ctx):
            if event.type == ToolEventType.RESULT:
                yield {"__type": "__result", "result": event.data, "stop": event.stop}
            elif event.type == ToolEventType.APPROVAL_REQUEST:
                yield {"event": event.data.get("event_name", "command_request"), **event.data}
            elif event.type == ToolEventType.TODO_UPDATE:
                yield {"event": "todo_update", **event.data}
            elif event.type == ToolEventType.SKILL_LOADED:
                # 注入技能内容到对话上下文
                if ctx.context_messages is not None:
                    ctx.context_messages.append({
                        "role": "system",
                        "content": (
                            f"【已加载技能：{event.data.get('skill_name', '')}】\n\n"
                            f"{event.data.get('content', '')}"
                        ),
                    })
                yield {"event": "skill_loaded", "message_id": msg_id, **event.data}
            elif event.type == ToolEventType.PROGRESS:
                yield {"event": event.data.get("event_name", "progress"), **event.data}
            elif event.type == ToolEventType.TEXT:
                yield {"event": "text_delta", "delta": event.data.get("text", "")}

    # ─── 旧的 _tool_* 方法已迁移到 app/tools/builtins/ ──────────────────────

    # ─── 上下文压缩（保留） ────────────────────────────────────────────────────
    # 注意：以下旧代码块已删除，用占位标记。实际的 _tool_* 方法在 git 历史中可查。
    # _tool_get_host_metrics, _tool_get_alerts, _tool_search_logs,
    # _DANGEROUS_COMMAND_PATTERNS, _is_dangerous_command, _tool_execute_command,
    # _wait_command_result, _tool_ask_user, _tool_load_skill
    # 全部迁移到 app/tools/builtins/ 目录下的独立模块。

    # ─── 上下文压缩 ────────────────────────────────────────────────────────────

    async def _compact_context(self) -> AsyncIterator[dict]:
        """压缩历史上下文，保留最近 6 条消息。"""
        if len(self._context) <= 8:
            return

        keep_recent = 6
        to_compact = self._context[1:-keep_recent]  # 跳过 system prompt
        recent = self._context[-keep_recent:]

        # 序列化历史消息
        history_text = "\n".join(
            f"[{m['role']}]: {m.get('content') or json.dumps(m.get('tool_calls', ''))}"
            for m in to_compact
        )

        # 调用 AI 生成摘要
        summary_messages = [
            {"role": "system", "content": "请将以下运维排障对话历史压缩为结构化摘要，保留：已执行的命令及结果、发现的问题、已完成的排障步骤、当前目标主机信息。用中文输出，不超过 500 字。"},
            {"role": "user", "content": history_text[:8000]},
        ]
        try:
            summary = await self._call_api_simple(summary_messages, max_tokens=600)
        except Exception as e:
            logger.warning(f"Compaction failed: {e}")
            return

        # 重建上下文
        self._context = [
            self._context[0],  # system prompt
            {"role": "system", "content": f"【历史对话摘要】\n{summary}"},
            *recent,
        ]

        # 持久化摘要
        original_count = len(to_compact)
        await self._save_message("system", "compaction_summary", {
            "summary": summary,
            "original_token_count": original_count * 200,  # 估算
        })

        # 更新 session token_count
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(OpsSession).where(OpsSession.id == self.session_id))
            session = result.scalar_one_or_none()
            if session:
                session.token_count = len(self._context) * 200
                session.compacted_at = datetime.now(timezone.utc)
                await db.commit()

        yield {"event": "compaction", "summary": summary}

    # ─── 会话标题生成 ──────────────────────────────────────────────────────────

    async def _generate_title(self, first_message: str):
        """异步生成会话标题（3-8 字）。"""
        try:
            messages = [
                {"role": "system", "content": "根据用户的运维问题，生成一个 3-8 字的简短标题，只输出标题文字，不加任何标点或解释。"},
                {"role": "user", "content": first_message[:200]},
            ]
            title = await self._call_api_simple(messages, max_tokens=20)
            title = title.strip().strip("。.\"'")[:50]

            async with AsyncSessionLocal() as db:
                result = await db.execute(select(OpsSession).where(OpsSession.id == self.session_id))
                session = result.scalar_one_or_none()
                if session:
                    session.title = title
                    await db.commit()

            # 推送标题更新事件
            redis = await get_redis()
            await redis.publish(
                f"{OPS_WS_CHANNEL}{self.session_id}",
                json.dumps({"event": "title_update", "title": title}),
            )
        except Exception as e:
            logger.warning(f"Title generation failed: {e}", exc_info=True)

    # ─── AI API 调用 ───────────────────────────────────────────────────────────

    async def _call_api_stream(self, runtime_cfg: dict) -> AsyncIterator[dict]:
        """流式调用 OpenAI 兼容 Chat Completions API，yield text_delta 和 tool_calls。"""
        if not runtime_cfg["api_key"]:
            yield {"type": "text_delta", "delta": "AI API Key 未配置，请在设置中配置 AI_API_KEY。"}
            return

        url = f"{runtime_cfg['base_url'].rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {runtime_cfg['api_key']}", "Content-Type": "application/json"}
        safe_messages = self._normalized_messages_for_tool_protocol(self._context, runtime_cfg["extra_context"])
        payload = {
            "model": runtime_cfg["model"],
            "messages": safe_messages,
            "tools": self._get_tools_schema(),
            "tool_choice": "auto",
            "stream": True,
            "temperature": 0.3,
            "max_tokens": runtime_cfg["max_tokens"],
        }
        if runtime_cfg.get("use_deep_thinking"):
            payload["reasoning"] = {
                "enabled": True,
                "max_tokens": int(runtime_cfg.get("deep_thinking_max_tokens") or 0),
            }

        logger.info(f"Calling AI API for session {self.session_id}, context_len={len(self._context)}")

        text_buffer = ""
        reasoning_buffer = ""
        tool_calls_buffer: dict[int, dict] = {}

        stream_queue: asyncio.Queue = asyncio.Queue()
        STREAM_TIMEOUT = 45

        async def _do_stream():
            """在独立 task 中运行流式读取，结果写入 queue。"""
            nonlocal text_buffer
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, read=15.0), verify=False) as client:
                    async with client.stream("POST", url, json=payload, headers=headers) as resp:
                        if resp.status_code != 200:
                            error_body = await resp.aread()
                            logger.error(f"AI API error {resp.status_code}: {error_body.decode()[:500]}")
                            await stream_queue.put({"type": "text_delta", "delta": f"\n[AI API 错误 {resp.status_code}，请重试]"})
                            return
                        async for line in resp.aiter_lines():
                            if not line.startswith("data: "):
                                continue
                            data_str = line[6:]
                            if data_str == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data_str)
                            except json.JSONDecodeError:
                                continue

                            choices = chunk.get("choices")
                            if not isinstance(choices, list) or not choices:
                                if chunk.get("error"):
                                    logger.error(f"AI API stream chunk error: {chunk.get('error')}")
                                continue
                            first_choice = choices[0] if isinstance(choices[0], dict) else {}
                            delta = first_choice.get("delta", {})

                            reasoning_delta = self._extract_reasoning_delta(delta)
                            if reasoning_delta:
                                reasoning_buffer += reasoning_delta
                                await stream_queue.put({"type": "reasoning_delta", "delta": reasoning_delta})

                            if delta.get("content"):
                                text_buffer += delta["content"]
                                await stream_queue.put({"type": "text_delta", "delta": delta["content"]})

                            for tc in delta.get("tool_calls", []):
                                idx = tc.get("index", 0)
                                if idx not in tool_calls_buffer:
                                    tool_calls_buffer[idx] = {
                                        "id": tc.get("id", ""),
                                        "type": "function",
                                        "function": {"name": "", "arguments": ""},
                                    }
                                if tc.get("id"):
                                    tool_calls_buffer[idx]["id"] = tc["id"]
                                fn = tc.get("function", {})
                                if fn.get("name"):
                                    tool_calls_buffer[idx]["function"]["name"] += fn["name"]
                                if fn.get("arguments"):
                                    tool_calls_buffer[idx]["function"]["arguments"] += fn["arguments"]
            except asyncio.CancelledError:
                logger.info(f"AI stream cancelled for session {self.session_id}")
            except Exception as e:
                logger.error(f"AI API stream error in task: {e}")
                await stream_queue.put({"type": "text_delta", "delta": f"\n\n[AI 调用失败：{e}]"})
            finally:
                await stream_queue.put(None)  # sentinel

        stream_task = asyncio.create_task(_do_stream())
        deadline = asyncio.get_event_loop().time() + STREAM_TIMEOUT
        try:
            while True:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    stream_task.cancel()
                    logger.warning(f"AI stream timeout ({STREAM_TIMEOUT}s) for session {self.session_id}")
                    yield {"type": "text_delta", "delta": "\n\n[AI 响应超时，请重试]"}
                    break
                try:
                    item = await asyncio.wait_for(stream_queue.get(), timeout=remaining)
                except asyncio.TimeoutError:
                    stream_task.cancel()
                    logger.warning(f"AI stream timeout ({STREAM_TIMEOUT}s) for session {self.session_id}")
                    yield {"type": "text_delta", "delta": "\n\n[AI 响应超时，请重试]"}
                    break
                if item is None:  # stream finished
                    break
                yield item
        except Exception as e:
            stream_task.cancel()
            logger.error(f"AI API stream error: {e}")
            yield {"type": "text_delta", "delta": f"\n\n[AI 调用失败：{e}]"}
        finally:
            if not stream_task.done():
                stream_task.cancel()

        if tool_calls_buffer:
            yield {"type": "tool_calls", "tool_calls": list(tool_calls_buffer.values())}

    @staticmethod
    def _extract_reasoning_delta(delta: dict) -> str:
        """兼容多种 OpenAI 兼容接口返回的 reasoning 增量字段。"""
        candidates = [
            delta.get("reasoning_content"),
            delta.get("reasoning"),
            delta.get("reasoning_text"),
        ]
        for value in candidates:
            text = OpsAgentLoop._normalize_reasoning_text(value)
            if text:
                return text
        return ""

    @staticmethod
    def _normalize_reasoning_text(value: object) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            parts: list[str] = []
            for item in value:
                if isinstance(item, str):
                    parts.append(item)
                    continue
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        parts.append(text)
                        continue
                    content = item.get("content")
                    if isinstance(content, str):
                        parts.append(content)
            return "".join(parts)
        if isinstance(value, dict):
            for key in ("text", "content"):
                text = value.get(key)
                if isinstance(text, str):
                    return text
        return ""

    @staticmethod
    def _normalized_messages_for_tool_protocol(messages: list[dict], extra_context: str = "") -> list[dict]:
        """
        修复 assistant(tool_calls) 与 tool 响应不配对的上下文，避免上游 API 400。

        规则：若 assistant 带 tool_calls，但紧随其后的连续 tool 消息未覆盖全部 tool_call_id，
        则自动补一条占位 tool 结果，保证协议完整。
        """
        normalized: list[dict] = []
        if messages and messages[0].get("role") == "system" and extra_context:
            merged_system = dict(messages[0])
            merged_system["content"] = f"{messages[0].get('content', '')}\n\n【额外上下文】\n{extra_context}"
            messages = [merged_system, *messages[1:]]
        total = len(messages)
        for idx, msg in enumerate(messages):
            normalized.append(msg)
            if msg.get("role") != "assistant":
                continue
            tool_calls = msg.get("tool_calls") or []
            if not tool_calls:
                continue

            required_ids = {
                tc.get("id") for tc in tool_calls
                if isinstance(tc, dict) and tc.get("id")
            }
            if not required_ids:
                continue

            present_ids: set[str] = set()
            j = idx + 1
            while j < total and messages[j].get("role") == "tool":
                t_id = messages[j].get("tool_call_id")
                if t_id:
                    present_ids.add(t_id)
                j += 1

            missing_ids = required_ids - present_ids
            for missing_id in missing_ids:
                normalized.append({
                    "role": "tool",
                    "tool_call_id": missing_id,
                    "content": json.dumps(
                        {"error": "tool result missing in history, auto-recovered"},
                        ensure_ascii=False,
                    ),
                })
        return normalized

    async def _call_api_simple(self, messages: list[dict], max_tokens: int = 500) -> str:
        """非流式 AI 调用，用于标题生成和上下文压缩。"""
        runtime_cfg = await self._load_ai_runtime_config()
        url = f"{runtime_cfg['base_url'].rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {runtime_cfg['api_key']}", "Content-Type": "application/json"}
        payload = {
            "model": runtime_cfg["model"],
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.3,
        }
        if runtime_cfg.get("use_deep_thinking"):
            payload["reasoning"] = {
                "enabled": True,
                "max_tokens": int(runtime_cfg.get("deep_thinking_max_tokens") or 0),
            }
        async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            choices = data.get("choices")
            if not isinstance(choices, list) or not choices:
                raise RuntimeError(f"AI API returned no choices: {json.dumps(data, ensure_ascii=False)[:500]}")
            first_choice = choices[0] if isinstance(choices[0], dict) else {}
            message = first_choice.get("message", {}) if isinstance(first_choice.get("message", {}), dict) else {}
            return str(message.get("content") or "")

    async def _load_ai_runtime_config(
        self,
        ai_config_id: str | None = None,
        feature_key: str | None = None,
    ) -> dict:
        """加载 AI 运行时配置：优先 v2 多业务配置，再回退到旧单配置。"""
        cfg = {
            "base_url": settings.ai_api_base,
            "model": settings.ai_model,
            "api_key": settings.ai_api_key,
            "max_tokens": settings.ai_max_tokens,
            "supports_deep_thinking": False,
            "deep_thinking_max_tokens": 0,
            "extra_context": "",
            "model_context_tokens": 200000,
            "allowed_context_tokens": 120000,
        }
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Setting).where(
                    Setting.key.in_(
                        [
                            OPS_AI_CONFIGS_V2_KEY,
                            OPS_AI_DEFAULT_ID_KEY,
                            OPS_AI_BASE_URL_KEY,
                            OPS_AI_MODEL_KEY,
                            OPS_AI_API_KEY_KEY,
                            OPS_AI_MAX_TOKENS_KEY,
                            OPS_AI_EXTRA_CONTEXT_KEY,
                        ]
                    )
                )
            )
            settings_rows = {row.key: row.value for row in result.scalars().all()}

        raw_configs = settings_rows.get(OPS_AI_CONFIGS_V2_KEY)
        default_id = settings_rows.get(OPS_AI_DEFAULT_ID_KEY) or ""
        if raw_configs:
            try:
                parsed = json.loads(raw_configs)
            except json.JSONDecodeError:
                parsed = []
            if isinstance(parsed, list) and parsed:
                scoped = parsed
                if feature_key:
                    scoped = [
                        c for c in parsed
                        if str(c.get("feature_key") or c.get("business_key") or "ops_assistant") == feature_key
                    ]
                    if not scoped:
                        fallback_default = [
                            c for c in parsed
                            if str(c.get("feature_key") or c.get("business_key") or "ops_assistant") == "default"
                        ]
                        scoped = fallback_default or parsed
                target = None
                if ai_config_id:
                    target = next((c for c in scoped if str(c.get("id")) == str(ai_config_id)), None)
                if not target and default_id:
                    target = next((c for c in scoped if str(c.get("id")) == str(default_id)), None)
                if not target:
                    target = next((c for c in scoped if bool(c.get("enabled", True))), scoped[0])
                if target:
                    cfg["base_url"] = str(target.get("base_url") or cfg["base_url"])
                    cfg["model"] = str(target.get("model") or cfg["model"])
                    cfg["api_key"] = str(target.get("api_key") or cfg["api_key"])
                    cfg["max_tokens"] = int(target.get("max_output_tokens") or cfg["max_tokens"])
                    cfg["supports_deep_thinking"] = bool(target.get("supports_deep_thinking", False))
                    cfg["deep_thinking_max_tokens"] = int(target.get("deep_thinking_max_tokens") or 0)
                    cfg["extra_context"] = str(target.get("extra_context") or "")
                    cfg["model_context_tokens"] = int(target.get("model_context_tokens") or 200000)
                    cfg["allowed_context_tokens"] = int(target.get("allowed_context_tokens") or 120000)
                    return cfg

        # 兼容旧单配置
        if settings_rows.get(OPS_AI_BASE_URL_KEY):
            cfg["base_url"] = settings_rows[OPS_AI_BASE_URL_KEY]
        if settings_rows.get(OPS_AI_MODEL_KEY):
            cfg["model"] = settings_rows[OPS_AI_MODEL_KEY]
        if settings_rows.get(OPS_AI_API_KEY_KEY):
            cfg["api_key"] = settings_rows[OPS_AI_API_KEY_KEY]
        if settings_rows.get(OPS_AI_MAX_TOKENS_KEY):
            try:
                cfg["max_tokens"] = int(settings_rows[OPS_AI_MAX_TOKENS_KEY])
            except ValueError:
                pass
        if settings_rows.get(OPS_AI_EXTRA_CONTEXT_KEY):
            cfg["extra_context"] = settings_rows[OPS_AI_EXTRA_CONTEXT_KEY]
        return cfg

    # ─── 辅助方法 ──────────────────────────────────────────────────────────────

    async def _ensure_context_loaded(self):
        """首次运行前从数据库回放消息，重建上下文。"""
        if self._context_loaded:
            return

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(OpsMessage)
                .where(
                    OpsMessage.session_id == self.session_id,
                    OpsMessage.compacted == False,  # noqa: E712
                )
                .order_by(OpsMessage.created_at.asc())
            )
            messages = result.scalars().all()

        rebuilt: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
        for msg in messages:
            rebuilt_item = self._to_context_message(msg)
            if rebuilt_item is None:
                continue
            if isinstance(rebuilt_item, list):
                rebuilt.extend(rebuilt_item)
            else:
                rebuilt.append(rebuilt_item)

        self._context = rebuilt
        self._context_loaded = True
        logger.info(
            "Ops context rebuilt from DB: session_id=%s, messages=%s, context_len=%s",
            self.session_id,
            len(messages),
            len(self._context),
        )

    def _to_context_message(self, msg: OpsMessage) -> Optional[dict | list[dict]]:
        """将持久化消息转换为 OpenAI messages 格式。"""
        content = msg.content or {}
        msg_type = msg.msg_type

        if msg_type == "text":
            text = content.get("text")
            if not text:
                return None
            if msg.role in ("user", "assistant", "system"):
                return {"role": msg.role, "content": text}
            return None

        if msg_type == "compaction_summary":
            summary = content.get("summary")
            if not summary:
                return None
            return {"role": "system", "content": f"【历史对话摘要】\n{summary}"}

        if msg_type == "tool_call":
            tool_name = content.get("tool_name") or "unknown_tool"
            arguments = content.get("arguments", {})
            if not isinstance(arguments, dict):
                arguments = {}
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": msg.tool_call_id or str(uuid.uuid4()),
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "arguments": json.dumps(arguments, ensure_ascii=False),
                        },
                    }
                ],
            }

        if msg_type == "tool_result":
            if not msg.tool_call_id:
                return None
            result = content.get("result")
            if result is None and content.get("error"):
                result = {"error": content.get("error")}
            if result is None:
                result = {}
            try:
                serialized = json.dumps(result, ensure_ascii=False)
            except TypeError:
                serialized = json.dumps({"result": str(result)}, ensure_ascii=False)
            if len(serialized) > 8000:
                serialized = serialized[:8000] + "...(truncated)"
            return {
                "role": "tool",
                "tool_call_id": msg.tool_call_id,
                "content": serialized,
            }

        return None

    async def _get_session(self) -> Optional[OpsSession]:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(OpsSession).where(OpsSession.id == self.session_id))
            return result.scalar_one_or_none()

    async def _save_message(self, role: str, msg_type: str, content: dict,
                             tool_call_id: Optional[str] = None,
                             message_id: Optional[str] = None) -> str:
        msg_id = message_id or str(uuid.uuid4())
        async with AsyncSessionLocal() as db:
            msg = OpsMessage(
                id=msg_id,
                session_id=self.session_id,
                role=role,
                msg_type=msg_type,
                content=content,
                tool_call_id=tool_call_id,
            )
            db.add(msg)
            result = await db.execute(select(OpsSession).where(OpsSession.id == self.session_id))
            session = result.scalar_one_or_none()
            if session:
                session.updated_at = datetime.now(timezone.utc)
                session.status = "active"
                session.token_count += len(json.dumps(content)) // 4
            await db.commit()
        return msg_id

    async def _update_message_content(self, message_id: str, patch: dict):
        """按 message_id 合并更新消息 content。"""
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(OpsMessage).where(
                    OpsMessage.id == message_id,
                    OpsMessage.session_id == self.session_id,
                )
            )
            msg = result.scalar_one_or_none()
            if not msg:
                return
            merged = dict(msg.content or {})
            merged.update(patch)
            msg.content = merged

            session_result = await db.execute(select(OpsSession).where(OpsSession.id == self.session_id))
            session = session_result.scalar_one_or_none()
            if session:
                session.updated_at = datetime.now(timezone.utc)
            await db.commit()

    async def _write_audit_log(self, host_id: int, command: str):
        from app.models.audit_log import AuditLog
        async with AsyncSessionLocal() as db:
            log = AuditLog(
                user_id=self.user_id,
                action="ops_command_execute",
                resource_type="host",
                resource_id=host_id,
                detail=json.dumps({"command": command, "session_id": self.session_id}, ensure_ascii=False),
            )
            db.add(log)
            await db.commit()

    async def _write_ai_operation_log(
        self,
        host_id: int,
        host_name: str,
        command: str,
        reason: str,
        request_id: str,
        cmd_result: dict,
    ):
        exit_code = cmd_result.get("exit_code")
        status = "success" if exit_code == 0 else "failed"
        async with AsyncSessionLocal() as db:
            log = AIOperationLog(
                user_id=self.user_id,
                session_id=self.session_id,
                request_id=request_id,
                host_id=host_id,
                host_name=host_name,
                command=command,
                reason=reason or None,
                exit_code=exit_code if isinstance(exit_code, int) else None,
                duration_ms=cmd_result.get("duration_ms"),
                status=status,
            )
            db.add(log)
            await db.commit()

    async def _attach_target_host_context(self, host_id: int):
        """将前端指定的目标主机注入会话与上下文，提升命令下发稳定性。"""
        host_name = f"host-{host_id}"
        async with AsyncSessionLocal() as db:
            host_result = await db.execute(select(Host).where(Host.id == host_id))
            host = host_result.scalar_one_or_none()
            if host:
                host_name = host.display_hostname

            session_result = await db.execute(select(OpsSession).where(OpsSession.id == self.session_id))
            session = session_result.scalar_one_or_none()
            if session:
                session.target_host_id = host_id
                session.updated_at = datetime.now(timezone.utc)
                await db.commit()

        self._context.append({
            "role": "system",
            "content": (
                "【用户已指定本轮目标主机】\n"
                f"- host_id: {host_id}\n"
                f"- host_name: {host_name}\n"
                "后续执行命令时优先针对该主机，除非用户明确要求切换目标。"
            ),
        })


# 内存中的 session → loop 映射（单 worker 内有效，跨 worker 通过 Redis 路由）
_active_loops: dict[str, OpsAgentLoop] = {}


def get_or_create_loop(session_id: str, user_id: int) -> OpsAgentLoop:
    if session_id not in _active_loops:
        _active_loops[session_id] = OpsAgentLoop(session_id, user_id)
    return _active_loops[session_id]


def remove_loop(session_id: str):
    _active_loops.pop(session_id, None)
