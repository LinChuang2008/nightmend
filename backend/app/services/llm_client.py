"""轻量 LLM 客户端（OpenAI 兼容接口）。"""
from __future__ import annotations

import json
from typing import Any

import httpx
from sqlalchemy import select

from app.core.config import settings
from app.core.database import async_session as AsyncSessionLocal
from app.models.setting import Setting


class LLMClientError(RuntimeError):
    """LLM 调用异常。"""


async def chat_completion(
    messages: list[dict[str, Any]],
    *,
    max_tokens: int = 1200,
    temperature: float = 0.3,
    feature_key: str | None = None,
) -> str:
    """调用聊天补全接口并返回文本内容。"""
    cfg = await _load_ai_runtime_config(feature_key=feature_key)
    if not cfg["api_key"]:
        raise LLMClientError("AI API Key 未配置")

    url = f"{cfg['base_url']}/chat/completions"
    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": cfg["model"],
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    async with httpx.AsyncClient(timeout=45.0, verify=False) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    return data["choices"][0]["message"]["content"]


async def _load_ai_runtime_config(feature_key: str | None = None) -> dict[str, Any]:
    cfg = {
        "base_url": settings.ai_api_base.rstrip("/"),
        "model": settings.ai_model,
        "api_key": settings.ai_api_key,
    }
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Setting).where(Setting.key.in_(["ops_ai_configs_v2", "ops_ai_default_config_id"]))
        )
        kv = {row.key: row.value for row in result.scalars().all()}
    raw = kv.get("ops_ai_configs_v2")
    default_id = kv.get("ops_ai_default_config_id") or ""
    if raw:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = []
        if isinstance(parsed, list) and parsed:
            scoped = parsed
            if feature_key:
                scoped = [
                    c for c in parsed
                    if str(c.get("feature_key") or c.get("business_key") or "ops_assistant") == feature_key
                ]
                # 当前功能未配置专属模型时，优先回退到 default 功能配置
                if not scoped:
                    fallback_default = [
                        c for c in parsed
                        if str(c.get("feature_key") or c.get("business_key") or "ops_assistant") == "default"
                    ]
                    scoped = fallback_default or parsed
            if scoped:
                target = None
                if default_id:
                    target = next((c for c in scoped if str(c.get("id")) == default_id), None)
                if not target:
                    target = next((c for c in scoped if bool(c.get("enabled", True))), scoped[0])
                cfg["base_url"] = str(target.get("base_url") or cfg["base_url"]).rstrip("/")
                cfg["model"] = str(target.get("model") or cfg["model"])
                cfg["api_key"] = str(target.get("api_key") or cfg["api_key"])
    return cfg


async def analyze_logs_brief(
    logs_data: list[dict[str, Any]],
    *,
    feature_key: str = "log_analysis",
) -> dict[str, Any]:
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
        content = await chat_completion(messages, max_tokens=500, temperature=0.1, feature_key=feature_key)
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
