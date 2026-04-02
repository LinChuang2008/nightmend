"""
外部告警源 Webhook 端点 (External Alert Source Webhook Endpoints)

接收来自 Prometheus AlertManager 等外部告警系统的 webhook 回调，
解析告警数据并触发 AI 自动诊断和修复流程。

认证方式: Bearer token (与 Agent token 共用 HMAC 机制)
响应模式: 202 Accepted (异步处理)
幂等性: 基于 alertname + instance + startsAt 去重

架构:
    AlertManager → POST /api/v1/webhooks/alertmanager
                      → PrometheusAdapter.parse()
                      → map_to_host()
                      → RemediationAgent.handle_alert()
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.alert_sources.base import IncomingAlert
from app.alert_sources.prometheus import PrometheusAdapter
from app.core.config import settings
from app.core.database import get_db
from app.core.redis import get_redis
from app.models.alert import Alert
from app.models.remediation_log import RemediationLog
from app.remediation.agent import RemediationAgent
from app.routers.alert_stream import DIAGNOSIS_CHANNEL
from app.services.ai_engine import AIEngine

logger = logging.getLogger("nightmend.webhooks")

router = APIRouter(prefix="/api/v1/webhooks", tags=["Webhooks"])

# 适配器实例 (Adapter instances)
_prometheus_adapter = PrometheusAdapter()

# 去重 TTL (秒)
_DEDUP_TTL = 300  # 5 min


async def _verify_webhook_token(authorization: str = Header(default="")) -> str:
    """验证 webhook Bearer token。

    使用与 Agent token 相同的 HMAC 机制验证。
    简化版: 直接比较配置中的 webhook token。
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = authorization[7:]
    expected = settings.alertmanager_webhook_token
    if not expected:
        raise HTTPException(status_code=503, detail="Webhook token not configured")

    # 常量时间比较，防止时序攻击
    if not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="Invalid webhook token")

    return token


async def _is_duplicate(external_id: str) -> bool:
    """检查告警是否重复 (Redis 去重, TTL 5min)。"""
    try:
        redis = await get_redis()
        key = f"webhook:dedup:{hashlib.sha256(external_id.encode()).hexdigest()[:16]}"
        result = await redis.set(key, "1", nx=True, ex=_DEDUP_TTL)
        return result is None  # None = key already existed = duplicate
    except Exception as e:
        logger.warning(f"Redis dedup check failed, allowing through: {e}")
        return False  # Redis 不可用时放行，宁可重复也不丢


async def _run_diagnosis(incoming: IncomingAlert, alert_id: int | None):
    """仅诊断模式: 调用 AI 引擎分析根因，通过 Redis 发布给 SSE 订阅者。"""
    try:
        engine = AIEngine()
        alert_dict = {
            "title": f"[Prometheus] {incoming.alertname}",
            "service_name": incoming.labels.get("job", incoming.alertname),
            "metric_name": incoming.alertname,
            "severity": incoming.severity,
            "instance": incoming.instance,
            "annotations": incoming.annotations,
            "labels": incoming.labels,
        }
        result = await engine.analyze_root_cause(alert_dict, [], [])

        event = {
            "alertname": incoming.alertname,
            "instance": incoming.instance,
            "severity": incoming.severity,
            "summary": incoming.annotations.get("summary", ""),
            "diagnosis": result,
            "timestamp": incoming.starts_at.isoformat() if incoming.starts_at else None,
            "alert_id": alert_id,
        }
        redis = await get_redis()
        await redis.publish(
            DIAGNOSIS_CHANNEL, json.dumps(event, ensure_ascii=False)
        )
        logger.info(f"Diagnosis published: alertname={incoming.alertname}")
    except Exception as e:
        logger.error(f"Diagnosis failed for {incoming.alertname}: {e}")


async def _process_alert(
    incoming: IncomingAlert,
    db: AsyncSession,
) -> dict[str, Any]:
    """处理单个告警: 映射 Host → 创建 Alert 记录 → 触发修复。"""
    # 1. 映射 Host
    host = await _prometheus_adapter.map_to_host(incoming, db)
    if host is None:
        if settings.enable_remediation:
            logger.warning(
                f"Unmatched alert: alertname={incoming.alertname} instance={incoming.instance} — "
                f"no matching Host found in NightMend"
            )
            return {
                "alertname": incoming.alertname,
                "instance": incoming.instance,
                "status": "skipped",
                "reason": "host_not_found",
            }
        # 诊断模式: 无 Host 也继续运行 AI 诊断
        logger.info(
            f"Demo diagnosis: alertname={incoming.alertname} instance={incoming.instance} (no host match)"
        )
        asyncio.create_task(_run_diagnosis(incoming, None))
        return {
            "alertname": incoming.alertname,
            "instance": incoming.instance,
            "status": "diagnosing",
        }

    # 2. 创建 NightMend Alert 记录
    alert_record = Alert(
        rule_id=0,  # 外部告警无 rule
        host_id=host.id,
        severity=incoming.severity,
        status="firing",
        title=f"[Prometheus] {incoming.alertname}",
        message=incoming.annotations.get("summary", incoming.alertname),
        fired_at=incoming.starts_at,
    )
    db.add(alert_record)
    await db.flush()  # 获取 alert_record.id

    if settings.enable_remediation:
        # 3. 转换为 RemediationAlert
        remediation_alert = _prometheus_adapter.to_remediation_alert(
            incoming, host, alert_record.id
        )

        # 4. 触发修复 (异步, 不等待完成)
        async def _run_remediation():
            try:
                agent = RemediationAgent()
                result = await agent.handle_alert(
                    alert=remediation_alert,
                    db=db,
                    triggered_by="alertmanager",
                )
                logger.info(
                    f"Remediation completed: alertname={incoming.alertname} "
                    f"host={host.hostname} success={result.success} "
                    f"runbook={result.runbook_name}"
                )
            except Exception as e:
                logger.error(f"Remediation failed for {incoming.alertname}: {e}")

        asyncio.create_task(_run_remediation())
    else:
        asyncio.create_task(_run_diagnosis(incoming, alert_record.id))

    return {
        "alertname": incoming.alertname,
        "instance": incoming.instance,
        "host": host.hostname,
        "status": "processing" if settings.enable_remediation else "diagnosing",
        "alert_id": alert_record.id,
    }


@router.post("/alertmanager", status_code=202)
async def receive_alertmanager_webhook(
    request: Request,
    _token: str = Depends(_verify_webhook_token),
    db: AsyncSession = Depends(get_db),
):
    """接收 Prometheus AlertManager webhook 回调。

    解析告警 → 映射 Host → 触发 AI 诊断和修复。
    返回 202 Accepted，修复异步执行。

    幂等性: 相同的 alertname + instance + startsAt 在 5 分钟内不会重复处理。
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # 解析 AlertManager payload
    try:
        incoming_alerts = _prometheus_adapter.parse(payload)
    except Exception as e:
        logger.error(f"Failed to parse AlertManager payload: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to parse payload: {e}")

    if not incoming_alerts:
        return {"status": "ok", "message": "No alerts in payload", "processed": 0}

    results = []
    for incoming in incoming_alerts:
        # 跳过已解决的告警
        if incoming.status == "resolved":
            results.append({
                "alertname": incoming.alertname,
                "status": "skipped",
                "reason": "resolved",
            })
            continue

        # 去重检查
        if await _is_duplicate(incoming.external_id):
            results.append({
                "alertname": incoming.alertname,
                "status": "skipped",
                "reason": "duplicate",
            })
            continue

        # 处理告警
        result = await _process_alert(incoming, db)
        results.append(result)

    await db.commit()

    processed = sum(1 for r in results if r.get("status") in ("processing", "diagnosing"))
    skipped = len(results) - processed
    logger.info(
        f"AlertManager webhook: {len(incoming_alerts)} alerts received, "
        f"{processed} processing, {skipped} skipped"
    )

    return {
        "status": "accepted",
        "received": len(incoming_alerts),
        "processing": processed,
        "skipped": skipped,
        "details": results,
    }
