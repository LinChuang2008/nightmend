"""Alertmanager 反向路由客户端 (Alertmanager Reverse Route Client)

正向：Prom → AM → NightMend webhook（由 alertmanager/alertmanager.yml 配置完成）
反向：NightMend → AM silence API

反向用途：
    - Runbook 执行期间，主动把目标告警设成 silence，防止 flap / 重复告警噪音
    - 用户在 UI 点"静默 1h"按钮直接投递到 AM（而不是只在 NightMend 自己记忆）
    - 维护窗口：批量 silence 某一批主机
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class AlertmanagerUnavailable(RuntimeError):
    pass


def _iso(dt: datetime) -> str:
    """Alertmanager 期望 RFC3339 (UTC, 带 Z 或 +00:00)。"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


async def create_silence(
    matchers: list[dict],
    *,
    duration: timedelta,
    created_by: str,
    comment: str,
    starts_at: datetime | None = None,
) -> str:
    """
    创建一条 silence，返回 silence ID。

    matchers 示例：
        [{"name": "alertname", "value": "HighCPU", "isRegex": False, "isEqual": True},
         {"name": "instance", "value": "web-0[12]", "isRegex": True, "isEqual": True}]

    生产调用示例（runbook 执行前）：
        await create_silence(
            [{"name": "alertname", "value": rule.name, "isRegex": False, "isEqual": True}],
            duration=timedelta(minutes=10),
            created_by="nightmend-runbook",
            comment=f"auto-silence during remediation run {log_id}",
        )
    """
    if not settings.alertmanager_url:
        raise AlertmanagerUnavailable("alertmanager_url not configured")

    start = starts_at or datetime.now(timezone.utc)
    end = start + duration
    payload = {
        "matchers": matchers,
        "startsAt": _iso(start),
        "endsAt": _iso(end),
        "createdBy": created_by,
        "comment": comment,
    }

    url = f"{settings.alertmanager_url.rstrip('/')}/api/v2/silences"
    try:
        async with httpx.AsyncClient(timeout=settings.prometheus_remote_timeout_seconds) as client:
            response = await client.post(url, json=payload)
    except httpx.RequestError as exc:
        logger.warning("Alertmanager silence POST failed: %s", exc)
        raise AlertmanagerUnavailable(f"Alertmanager unreachable: {exc}") from exc

    if response.status_code >= 400:
        raise AlertmanagerUnavailable(
            f"Alertmanager rejected silence: status={response.status_code} body={response.text[:200]}"
        )

    data = response.json()
    silence_id = data.get("silenceID") or data.get("silenceId") or data.get("id")
    if not silence_id:
        raise AlertmanagerUnavailable(f"Alertmanager response missing silenceID: {data}")
    logger.info("silence created: id=%s by=%s duration=%s", silence_id, created_by, duration)
    return silence_id


async def delete_silence(silence_id: str) -> None:
    """提前解除 silence。"""
    if not settings.alertmanager_url:
        raise AlertmanagerUnavailable("alertmanager_url not configured")
    url = f"{settings.alertmanager_url.rstrip('/')}/api/v2/silence/{silence_id}"
    try:
        async with httpx.AsyncClient(timeout=settings.prometheus_remote_timeout_seconds) as client:
            response = await client.delete(url)
    except httpx.RequestError as exc:
        raise AlertmanagerUnavailable(f"Alertmanager unreachable: {exc}") from exc
    if response.status_code >= 400 and response.status_code != 404:
        raise AlertmanagerUnavailable(
            f"delete silence failed: status={response.status_code} body={response.text[:200]}"
        )


async def list_silences(active_only: bool = True) -> list[dict]:
    """列出当前 silences，用于 UI 展示。"""
    if not settings.alertmanager_url:
        raise AlertmanagerUnavailable("alertmanager_url not configured")
    url = f"{settings.alertmanager_url.rstrip('/')}/api/v2/silences"
    try:
        async with httpx.AsyncClient(timeout=settings.prometheus_remote_timeout_seconds) as client:
            response = await client.get(url)
    except httpx.RequestError as exc:
        raise AlertmanagerUnavailable(f"Alertmanager unreachable: {exc}") from exc
    if response.status_code >= 400:
        raise AlertmanagerUnavailable(f"list silences failed: {response.status_code}")
    silences = response.json() or []
    if active_only:
        silences = [s for s in silences if (s.get("status") or {}).get("state") == "active"]
    return silences


async def is_healthy() -> bool:
    if not settings.alertmanager_url:
        return False
    url = f"{settings.alertmanager_url.rstrip('/')}/-/healthy"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(url)
        return response.status_code == 200
    except httpx.RequestError:
        return False
