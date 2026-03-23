"""轻量 LLM 客户端（OpenAI 兼容接口）。"""
from __future__ import annotations

import json
from typing import Any

import logging

import httpx

from app.core.config import settings

# 防止 httpx 调试日志泄露 Authorization header 中的 API Key
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


class LLMClientError(RuntimeError):
    """LLM 调用异常。"""


async def chat_completion(
    messages: list[dict[str, Any]],
    *,
    max_tokens: int = 1200,
    temperature: float = 0.3,
) -> str:
    """调用聊天补全接口并返回文本内容。"""
    if not settings.ai_api_key:
        raise LLMClientError("AI API Key 未配置")

    url = f"{settings.ai_api_base}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.ai_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.ai_model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    _verify_ssl = settings.environment != "development"
    async with httpx.AsyncClient(timeout=45.0, verify=_verify_ssl) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    return data["choices"][0]["message"]["content"]


async def analyze_logs_brief(logs_data: list[dict[str, Any]]) -> dict[str, Any]:
    """
    对日志做简要异常分析，输出结构化结果。
    返回字段对齐 anomaly_scanner 现有写入逻辑。
    """
    prompt = (
        "你是运维异常检测助手。基于给定日志输出 JSON："
        '{"title":"", "summary":"", "severity":"info|warning|critical"}。\n'
        "要求：标题 <= 30字；summary <= 200字；仅输出 JSON。"
    )
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": json.dumps(logs_data[:200], ensure_ascii=False)},
    ]

    try:
        content = await chat_completion(messages, max_tokens=500, temperature=0.1)
        content = content.strip()
        if content.startswith("```"):
            lines = content.splitlines()
            content = "\n".join(
                line for line in lines if not line.strip().startswith("```")
            ).strip()
        parsed = json.loads(content)
        return {
            "title": parsed.get("title", "日志异常扫描结果"),
            "summary": parsed.get("summary", ""),
            "severity": parsed.get("severity", "info"),
        }
    except Exception as e:
        return {"error": str(e), "title": "日志异常扫描失败", "severity": "warning"}

