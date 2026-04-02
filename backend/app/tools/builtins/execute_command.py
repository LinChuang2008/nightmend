"""
ExecuteCommandTool — 远程执行命令

迁移自 OpsAgentLoop._tool_execute_command。
通过 Redis pub/sub 将命令下发到 Agent Worker，等待执行结果返回。
包含危险命令拦截、用户确认流程、审计日志写入。

风险等级 HIGH，需要用户确认后才会执行。
MCP 模式下（approval_service 为 None）自动拒绝执行。
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import TYPE_CHECKING

from app.tools.base import OpsTool, RiskLevel, ToolEvent, ToolEventType

if TYPE_CHECKING:
    from app.tools.context import ToolContext

logger = logging.getLogger(__name__)

# 命令确认超时（秒）
COMMAND_CONFIRM_TIMEOUT = 60


class ExecuteCommandTool(OpsTool):
    name = "execute_command"
    description = (
        "Execute a shell command on a remote host via the monitoring agent. "
        "The command must pass safety checks and requires user approval before execution. "
        "Returns stdout, stderr, exit_code, and duration_ms."
    )
    risk_level = RiskLevel.HIGH
    requires_approval = True

    @property
    def tags(self) -> list[str]:
        return ["execution", "diagnosis"]

    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute on the remote host.",
                },
                "host_id": {
                    "type": "integer",
                    "description": "The ID of the target host to execute the command on.",
                },
                "timeout": {
                    "type": "integer",
                    "default": 120,
                    "description": "Command execution timeout in seconds (default 120).",
                },
                "reason": {
                    "type": "string",
                    "description": "Optional reason for executing this command (for audit trail).",
                },
            },
            "required": ["command", "host_id"],
        }

    async def execute(self, args: dict, context: ToolContext):
        command = args["command"]
        host_id = args["host_id"]
        timeout = args.get("timeout", 120)
        reason = args.get("reason", "")
        msg_id = str(uuid.uuid4())

        # MCP 模式下不支持需要确认的工具
        if context.approval_service is None:
            yield ToolEvent(
                type=ToolEventType.RESULT,
                data={
                    "error": "execute_command requires user approval and is not available in MCP mode.",
                },
            )
            return

        # 安全检查：拦截危险命令
        if context.safety_checker.is_dangerous(command):
            logger.warning("Blocked dangerous command: %s", command)
            yield ToolEvent(
                type=ToolEventType.PROGRESS,
                data={
                    "event": "command_blocked",
                    "message_id": msg_id,
                    "command": command,
                    "reason": "命令被安全策略拦截（匹配危险模式）",
                },
            )
            yield ToolEvent(
                type=ToolEventType.RESULT,
                data={
                    "error": "安全策略拦截：此命令匹配危险模式，已被自动阻止。请使用更安全的替代方案。",
                },
            )
            return

        # 获取主机名
        from sqlalchemy import select
        from app.models.host import Host

        async with context.db_session_factory() as db:
            result = await db.execute(select(Host).where(Host.id == host_id))
            host = result.scalar_one_or_none()
        host_name = host.display_hostname if host else f"host-{host_id}"

        # 持久化 command_request 消息
        if context.save_message is not None:
            await context.save_message("assistant", "command_request", {
                "command": command, "host_id": host_id, "host_name": host_name,
                "timeout": timeout, "reason": reason, "status": "pending",
            }, message_id=msg_id)

        await context.approval_service.register(msg_id, "command_request")

        # 向前端推送确认请求
        yield ToolEvent(
            type=ToolEventType.APPROVAL_REQUEST,
            data={
                "event": "command_request",
                "message_id": msg_id,
                "command": command,
                "host_id": host_id,
                "host_name": host_name,
                "timeout": timeout,
                "reason": reason,
            },
        )

        # 等待用户确认
        reply = await context.approval_service.wait_for_reply(
            msg_id,
            timeout=COMMAND_CONFIRM_TIMEOUT,
            timeout_action="expired",
        )
        action = reply.get("action", "reject")

        if action == "confirm":
            request_id = msg_id
            redis = context.redis

            # 存储请求会话映射，用于结果路由
            await redis.set(
                f"cmd_req_session:{request_id}",
                context.session_id,
                ex=timeout + 60,
            )

            # 下发命令到 Agent Worker
            payload = json.dumps({
                "type": "exec_command",
                "request_id": request_id,
                "command": command,
                "timeout": timeout,
            })
            await redis.publish(f"cmd_to_agent:{host_id}", payload)

            # 写审计日志
            await self._write_audit_log(context, host_id, command)

            # 等待命令执行结果
            cmd_result = await self._wait_command_result(
                redis, context.session_id, request_id, timeout + 10,
            )

            # 写 AI 操作日志
            await self._write_ai_operation_log(
                context,
                host_id=host_id,
                host_name=host_name,
                command=command,
                reason=reason,
                request_id=request_id,
                cmd_result=cmd_result,
            )

            # 持久化命令结果
            if context.save_message is not None:
                await context.save_message("tool", "command_result", {
                    "request_id": request_id,
                    "exit_code": cmd_result.get("exit_code", -1),
                    "duration_ms": cmd_result.get("duration_ms", 0),
                    "stdout": cmd_result.get("stdout", ""),
                    "stderr": cmd_result.get("stderr", ""),
                })

            # 推送执行结果事件
            yield ToolEvent(
                type=ToolEventType.PROGRESS,
                data={
                    "event": "command_result",
                    "message_id": msg_id,
                    "exit_code": cmd_result.get("exit_code", -1),
                    "duration_ms": cmd_result.get("duration_ms", 0),
                },
            )
            yield ToolEvent(type=ToolEventType.RESULT, data=cmd_result)

        elif action == "reject":
            yield ToolEvent(
                type=ToolEventType.PROGRESS,
                data={"event": "command_expired", "message_id": msg_id, "reason": "rejected"},
            )
            yield ToolEvent(
                type=ToolEventType.RESULT,
                data={"error": "用户拒绝执行此命令", "action": "rejected"},
            )
        else:
            yield ToolEvent(
                type=ToolEventType.PROGRESS,
                data={"event": "command_expired", "message_id": msg_id, "reason": "timeout"},
            )
            yield ToolEvent(
                type=ToolEventType.RESULT,
                data={"error": "命令确认超时，已自动取消", "action": "expired"},
            )

    # ─── Private helpers ──────────────────────────────────────────────────────

    @staticmethod
    async def _wait_command_result(
        redis, session_id: str, request_id: str, timeout: int,
    ) -> dict:
        """订阅 Redis channel 等待命令执行结果，带硬超时防止永久阻塞。"""
        channel = f"cmd_result:{session_id}"
        pubsub = redis.pubsub()
        await pubsub.subscribe(channel)
        try:
            deadline = asyncio.get_event_loop().time() + timeout
            while True:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    logger.warning(
                        "Command result timeout (%ds) for request %s", timeout, request_id,
                    )
                    break
                try:
                    message = await asyncio.wait_for(
                        pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0),
                        timeout=min(remaining, 5.0),
                    )
                except asyncio.TimeoutError:
                    continue
                if message is None:
                    continue
                try:
                    data = json.loads(message["data"])
                    if data.get("request_id") == request_id:
                        return data
                except Exception:
                    continue
        except (asyncio.TimeoutError, asyncio.CancelledError):
            pass
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()
        return {
            "error": "command result timeout",
            "exit_code": -1,
            "stdout": "",
            "stderr": "timeout",
        }

    @staticmethod
    async def _write_audit_log(context: ToolContext, host_id: int, command: str):
        """写入审计日志。"""
        from app.models.audit_log import AuditLog

        async with context.db_session_factory() as db:
            log = AuditLog(
                user_id=context.user_id,
                action="ops_command_execute",
                resource_type="host",
                resource_id=host_id,
                detail=json.dumps(
                    {"command": command, "session_id": context.session_id},
                    ensure_ascii=False,
                ),
            )
            db.add(log)
            await db.commit()

    @staticmethod
    async def _write_ai_operation_log(
        context: ToolContext,
        host_id: int,
        host_name: str,
        command: str,
        reason: str,
        request_id: str,
        cmd_result: dict,
    ):
        """写入 AI 操作日志。"""
        from app.models.ai_operation_log import AIOperationLog

        exit_code = cmd_result.get("exit_code")
        status = "success" if exit_code == 0 else "failed"
        async with context.db_session_factory() as db:
            log = AIOperationLog(
                user_id=context.user_id,
                session_id=context.session_id,
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
