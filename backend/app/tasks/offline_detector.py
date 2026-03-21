"""
主机离线检测任务模块。

定期扫描所有在线主机的心跳状态，当心跳超时时将主机标记为离线状态。
超时时间优先使用用户配置的 host_offline 告警规则中的 cooldown_seconds，
未配置时 fallback 到系统默认值 300 秒。

主机离线时，自动静默该主机下所有活跃的服务告警，避免产生大量服务异常噪音。
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, update

from app.core.database import async_session
from app.core.redis import get_redis
from app.models.alert import Alert, AlertRule
from app.models.host import Host

logger = logging.getLogger(__name__)

HEARTBEAT_TIMEOUT = 300  # 心跳超时时间（秒），即 5 分钟，可被 host_offline 告警规则覆盖
CHECK_INTERVAL = 60  # 检查间隔（秒）


async def _get_heartbeat_timeout(db) -> int:
    """
    获取心跳超时时间。
    优先使用用户配置的 host_offline 告警规则中的 cooldown_seconds，
    但至少是 Agent 心跳间隔（60s）的 2 倍，避免误判。
    未配置或未启用时 fallback 到系统默认值。
    """
    AGENT_HEARTBEAT_INTERVAL = 60
    result = await db.execute(
        select(AlertRule).where(
            AlertRule.metric == "host_offline",
            AlertRule.is_enabled == True,  # noqa: E712
        ).limit(1)
    )
    rule = result.scalar_one_or_none()
    if rule and rule.cooldown_seconds and rule.cooldown_seconds > 0:
        timeout = max(rule.cooldown_seconds, AGENT_HEARTBEAT_INTERVAL * 2)
        logger.debug(f"Using host_offline rule cooldown as heartbeat timeout: {timeout}s")
        return timeout
    return HEARTBEAT_TIMEOUT


async def _suppress_service_alerts_for_host(db, host_id: int):
    """
    主机离线时，将该主机下所有活跃的服务告警标记为 resolved（已解决）。
    这些告警在主机重新上线后，由告警引擎根据服务实际状态重新评估。
    """
    result = await db.execute(
        select(Alert).where(
            Alert.host_id == host_id,
            Alert.service_id.isnot(None),
            Alert.status.in_(["firing", "acknowledged"]),
        )
    )
    service_alerts = result.scalars().all()

    if not service_alerts:
        return

    now = datetime.now(timezone.utc)
    for alert in service_alerts:
        alert.status = "resolved"
        alert.resolved_at = now
        alert.message = (alert.message or "") + " [主机离线，服务告警已自动静默]"

    logger.info(
        f"Suppressed {len(service_alerts)} service alert(s) for offline host {host_id}"
    )


async def check_offline_hosts():
    """扫描所有在线主机的 Redis 心跳记录，将心跳超时的主机标记为离线。"""
    redis = await get_redis()
    async with async_session() as db:
        # 优先使用用户配置的 host_offline 规则超时时间
        heartbeat_timeout = await _get_heartbeat_timeout(db)

        # 只查询当前状态为在线的主机
        result = await db.execute(
            select(Host).where(Host.status == "online")
        )
        hosts = result.scalars().all()

        now = datetime.now(timezone.utc)
        for host in hosts:
            hb = await redis.get(f"heartbeat:{host.id}")
            if hb is None:
                # Redis 中无心跳记录，回退到数据库中的 last_heartbeat 字段判断
                if host.last_heartbeat and (now - host.last_heartbeat) > timedelta(seconds=heartbeat_timeout):
                    host.status = "offline"
                    logger.warning(f"Host {host.hostname} (id={host.id}) marked offline (timeout={heartbeat_timeout}s)")
                    # 主机离线时静默其所有活跃服务告警，避免告警风暴
                    await _suppress_service_alerts_for_host(db, host.id)
            # Redis 键存在说明主机仍在线（心跳键有 300s TTL，由 Agent 续期）

        await db.commit()


async def offline_detector_loop():
    """离线检测后台循环，定期检查主机心跳状态。"""
    logger.info("Offline detector started")
    while True:
        try:
            await check_offline_hosts()
        except Exception:
            logger.exception("Error in offline detector")
        await asyncio.sleep(CHECK_INTERVAL)
