"""
AI引擎服务 (AI Engine Service)

功能描述 (Description):
    NightMend 核心 AI 服务模块，提供智能运维分析能力。
    支持：日志异常分析、自然语言运维问答、告警根因分析。

升级说明 (v2 - 2026-03-02 故障模式记忆):
    - analyze_root_cause(): recall 时使用 service_name + metric 关键词
    - analyze_root_cause(): store 时携带 memory_type=episode, importance=7,
      tags=["fault-pattern", service_name]
    - ROOT_CAUSE_SYSTEM_PROMPT 新增「历史相似故障」段落
    - 所有 recall/store 操作显式传 namespace="nightmend"
"""
import asyncio
import json
import logging
from typing import List, Dict, Any, Optional

import httpx

from app.core.config import settings
from app.services.memory_client import memory_client

logger = logging.getLogger(__name__)

# ─── System Prompts ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """你是一位资深运维专家和日志分析师。你的任务是分析服务器日志，识别异常模式、潜在风险和安全威胁。

分析要求：
1. 识别异常模式和错误聚类
2. 评估风险等级（info/warning/critical）
3. 提供具体的建议操作
4. 用中文回复

请以 JSON 格式返回分析结果：
{
  "severity": "info|warning|critical",
  "title": "简短的异常标题",
  "summary": "异常摘要描述",
  "anomalies": [
    {
      "pattern": "异常模式描述",
      "count": 出现次数,
      "risk": "风险等级",
      "suggestion": "建议操作"
    }
  ],
  "overall_assessment": "总体评估"
}"""

CHAT_SYSTEM_PROMPT = """你是 NightMend AI 运维助手，基于以下系统数据回答运维问题。用中文回答，简洁明了。

回答要求：
1. 基于提供的系统数据进行分析和回答
2. 如果数据不足以回答，明确说明
3. 给出具体的建议和操作步骤
4. 保持简洁，重点突出

请以 JSON 格式返回：
{
  "answer": "你的回答内容",
  "sources": [
    {"type": "log/metric/alert/service", "summary": "数据来源摘要"}
  ]
}"""

ROOT_CAUSE_SYSTEM_PROMPT = """你是 NightMend AI 运维专家，擅长告警根因分析。基于提供的告警信息、系统指标、日志以及历史相似故障经验，分析告警的可能根因。

分析要求：
1. 关联指标异常和日志错误，找出根本原因
2. 若【历史相似故障】中存在相关经验，优先结合历史经验给出洞察，并在 evidence 中注明"参考历史故障：xxx"
3. 评估置信度（历史匹配可适当提高置信度）
4. 列出支持证据
5. 给出排查和修复建议

请以 JSON 格式返回：
{
  "root_cause": "根因描述",
  "confidence": "high/medium/low",
  "evidence": ["证据1", "证据2"],
  "recommendations": ["建议1", "建议2"]
}"""


class AIEngine:
    """AI引擎核心类"""

    def __init__(self) -> None:
        self.api_base = settings.ai_api_base
        self.api_key = settings.ai_api_key
        self.model = settings.ai_model
        self.max_tokens = settings.ai_max_tokens

    async def _call_api(self, messages: List[Dict[str, str]], max_retries: int = 2) -> str:
        if not self.api_key:
            raise ValueError("AI API key not configured. Set AI_API_KEY environment variable.")

        url = f"{self.api_base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": 0.3,
        }

        last_error: Optional[Exception] = None
        for attempt in range(max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(url, json=payload, headers=headers)
                    response.raise_for_status()
                    data = response.json()
                    return data["choices"][0]["message"]["content"]
            except Exception as e:
                last_error = e
                logger.warning("AI API call attempt %d failed: %s", attempt + 1, str(e))
                if attempt < max_retries:
                    continue

        raise last_error  # type: ignore[misc]

    def _parse_json_response(self, text: str) -> Dict[str, Any]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines)
        return json.loads(cleaned)

    async def analyze_logs(self, logs: List[dict], context: str = "") -> dict:
        if not logs:
            return {
                "severity": "info",
                "title": "无日志数据",
                "summary": "指定时间范围内没有找到日志数据",
                "anomalies": [],
                "overall_assessment": "无数据可分析",
            }

        log_text_parts = []
        for log in logs[:200]:
            log_text_parts.append(
                f"[{log.get('timestamp', '')}] [{log.get('level', '')}] "
                f"host={log.get('host_id', '')} service={log.get('service', '')} "
                f"{log.get('message', '')}"
            )
        log_text = "\n".join(log_text_parts)

        user_msg = f"请分析以下 {len(logs)} 条服务器日志，识别异常和风险：\n\n{log_text}"
        if context:
            user_msg += f"\n\n附加上下文：{context}"

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ]

        try:
            result_text = await self._call_api(messages)
            result = self._parse_json_response(result_text)

            if result.get("severity", "info") != "info":
                title = result.get("title", "未知异常")
                summary = result.get("summary", "")
                store_content = f"日志异常发现: {title}\n摘要: {summary}"
                asyncio.create_task(
                    memory_client.store(
                        store_content,
                        source="nightmend-log-analysis",
                        memory_type="episode",
                        importance=5,
                        tags=["log-anomaly"],
                        namespace="nightmend",
                    )
                )

            return result

        except json.JSONDecodeError:
            return {
                "severity": "info",
                "title": "AI 分析完成",
                "summary": result_text,
                "anomalies": [],
                "overall_assessment": result_text,
            }
        except Exception as e:
            logger.error("AI log analysis failed: %s", str(e))
            return {
                "severity": "info",
                "title": "分析失败",
                "summary": f"AI 分析过程中出现错误：{str(e)}",
                "anomalies": [],
                "overall_assessment": f"错误：{str(e)}",
                "error": True,
            }

    async def chat(self, question: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        context_parts: List[str] = []

        if context:
            if context.get("logs"):
                log_lines = []
                for log in context["logs"][:50]:
                    log_lines.append(
                        f"  [{log.get('timestamp', '')}] [{log.get('level', '')}] "
                        f"host={log.get('host_id', '')} service={log.get('service', '')} "
                        f"{log.get('message', '')}"
                    )
                context_parts.append("【最近日志（ERROR/WARN）】\n" + "\n".join(log_lines))

            if context.get("metrics"):
                metric_lines = []
                for m in context["metrics"]:
                    metric_lines.append(
                        f"  主机{m.get('host_id', '?')}({m.get('hostname', '?')}): "
                        f"CPU={m.get('cpu_percent', 'N/A')}%, "
                        f"内存={m.get('memory_percent', 'N/A')}%, "
                        f"磁盘={m.get('disk_percent', 'N/A')}%"
                    )
                context_parts.append("【主机指标摘要】\n" + "\n".join(metric_lines))

            if context.get("alerts"):
                alert_lines = []
                for a in context["alerts"]:
                    alert_lines.append(
                        f"  [{a.get('severity', '')}] {a.get('title', '')} "
                        f"(状态: {a.get('status', '')}, 触发: {a.get('fired_at', '')})"
                    )
                context_parts.append("【活跃告警】\n" + "\n".join(alert_lines))

            if context.get("services"):
                svc_lines = []
                for s in context["services"]:
                    svc_lines.append(
                        f"  {s.get('name', '?')}: {s.get('status', 'unknown')} "
                        f"(类型: {s.get('type', '?')}, 目标: {s.get('target', '?')})"
                    )
                context_parts.append("【服务健康状态】\n" + "\n".join(svc_lines))

        context_text = "\n\n".join(context_parts) if context_parts else "当前没有可用的系统数据。"

        memories = await memory_client.recall(question, namespace="nightmend")
        memory_context: List[Dict[str, Any]] = []
        memory_prompt = ""
        if memories:
            memory_context = memories
            memory_lines = []
            for i, mem in enumerate(memories[:5], 1):
                content = mem.get("content", mem.get("text", str(mem)))
                memory_lines.append(f"{i}. {content}")
            memory_prompt = (
                "\n\n【历史运维经验（来自记忆系统）】\n"
                + "\n".join(memory_lines)
                + "\n请参考以上历史经验回答问题。"
            )

        user_msg = f"系统上下文数据：\n{context_text}\n\n用户问题：{question}"
        system_prompt = CHAT_SYSTEM_PROMPT + memory_prompt

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ]

        try:
            result_text = await self._call_api(messages)
            try:
                result = self._parse_json_response(result_text)
            except json.JSONDecodeError:
                result = {"answer": result_text, "sources": []}

            answer = result.get("answer", "")
            store_content = f"用户问题: {question}\nAI 回答: {answer[:500]}"
            asyncio.create_task(
                memory_client.store(
                    store_content,
                    source="nightmend-chat",
                    memory_type="episode",
                    importance=4,
                    tags=["chat-qa"],
                    namespace="nightmend",
                )
            )

            result["memory_context"] = memory_context
            return result

        except Exception as e:
            logger.error("AI chat failed: %s", str(e))
            return {
                "answer": f"AI 对话出错：{str(e)}",
                "sources": [],
                "error": True,
                "memory_context": [],
            }

    async def analyze_root_cause(
        self, alert: dict, metrics: List[dict], logs: List[dict]
    ) -> Dict[str, Any]:
        """
        告警根因分析引擎 (Alert Root Cause Analysis Engine)

        v2 升级 (2026-03-02):
            - Working Memory: 用 service_name + metric 关键词召回历史相似故障
            - Long-term Memory: 存储时携带 memory_type=episode, importance=7,
              tags=["fault-pattern", service_name]
        """
        # 1. 告警信息解构
        alert_title = alert.get("title", "")
        service_name = alert.get("service_name", alert.get("service", ""))
        metric_name = alert.get("metric_name", alert.get("metric", ""))

        alert_text = (
            f"告警标题: {alert_title}\n"
            f"严重级别: {alert.get('severity', '')}\n"
            f"状态: {alert.get('status', '')}\n"
            f"告警消息: {alert.get('message', '')}\n"
            f"服务: {service_name}\n"
            f"指标: {metric_name}\n"
            f"指标值: {alert.get('metric_value', 'N/A')}\n"
            f"阈值: {alert.get('threshold', 'N/A')}\n"
            f"触发时间: {alert.get('fired_at', '')}"
        )

        # 2. 性能指标趋势
        metric_lines = []
        for m in metrics[:30]:
            metric_lines.append(
                f"  [{m.get('recorded_at', '')}] host={m.get('host_id', '')} "
                f"CPU={m.get('cpu_percent', 'N/A')}% 内存={m.get('memory_percent', 'N/A')}% "
                f"磁盘={m.get('disk_percent', 'N/A')}%"
            )
        metrics_text = "\n".join(metric_lines) if metric_lines else "无相关指标数据"

        # 3. 错误日志关联
        log_lines = []
        for log in logs[:50]:
            log_lines.append(
                f"  [{log.get('timestamp', '')}] [{log.get('level', '')}] "
                f"service={log.get('service', '')} {log.get('message', '')}"
            )
        logs_text = "\n".join(log_lines) if log_lines else "无相关日志数据"

        # 4. Working Memory: 召回历史相似故障
        # 用 service_name + metric 关键词构建精准查询（比单用标题更准确）
        recall_parts = [p for p in [alert_title, service_name, metric_name] if p]
        recall_query = " ".join(recall_parts) if recall_parts else alert_title

        memories = await memory_client.recall(
            recall_query,
            top_k=3,
            namespace="nightmend",
        )
        memory_context: List[Dict[str, Any]] = []
        memory_prompt = ""
        if memories:
            memory_context = memories
            memory_lines = []
            for i, mem in enumerate(memories[:3], 1):
                content = mem.get("content", mem.get("text", str(mem)))
                memory_lines.append(f"{i}. {content}")
            memory_prompt = (
                "\n\n【历史相似故障（来自记忆系统，优先参考）】\n"
                + "\n".join(memory_lines)
                + "\n如以上历史故障与本次告警相似，请在分析中明确指出此模式曾出现过，并提升置信度。"
            )

        # 5. 构建多维分析请求
        user_msg = (
            f"请分析以下告警的根因：\n\n"
            f"【告警信息】\n{alert_text}\n\n"
            f"【相关时段指标】\n{metrics_text}\n\n"
            f"【相关时段日志】\n{logs_text}"
        )

        system_prompt = ROOT_CAUSE_SYSTEM_PROMPT + memory_prompt

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ]

        try:
            # 6. 执行 AI 根因分析
            result_text = await self._call_api(messages)
            try:
                result = self._parse_json_response(result_text)
            except json.JSONDecodeError:
                result = {
                    "root_cause": result_text,
                    "confidence": "low",
                    "evidence": [],
                    "recommendations": [],
                }

            # 7. Long-term Memory: 存储故障模式
            root_cause = result.get("root_cause", "")
            recommendations = result.get("recommendations", [])

            # 构建结构化的故障模式记录
            fault_description_parts = [
                f"故障模式: {alert_title}",
                f"受影响服务: {service_name}" if service_name else "",
                f"关联指标: {metric_name}" if metric_name else "",
                f"根因: {root_cause}",
                f"解决建议: {'; '.join(recommendations[:3])}" if recommendations else "",
            ]
            fault_content = "\n".join([p for p in fault_description_parts if p])

            # 构建 tags：固定 fault-pattern + 服务名（如果有）
            fault_tags = ["fault-pattern"]
            if service_name:
                fault_tags.append(service_name)
            if metric_name:
                fault_tags.append(metric_name)

            asyncio.create_task(
                memory_client.store(
                    fault_content,
                    source="nightmend-root-cause",
                    memory_type="episode",
                    importance=7,       # 故障模式重要性高
                    tags=fault_tags,
                    namespace="nightmend",
                )
            )

            result["memory_context"] = memory_context
            return result

        except Exception as e:
            logger.error("AI root cause analysis failed: %s", str(e))
            return {
                "root_cause": f"根因分析出错：{str(e)}",
                "confidence": "low",
                "evidence": [],
                "recommendations": [],
                "error": True,
                "memory_context": [],
            }


# 模块级单例实例
ai_engine = AIEngine()
