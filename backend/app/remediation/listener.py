"""
NightMend 自动修复系统 - 告警监听器
NightMend Remediation System - Alert Event Listener

监听 Redis PubSub 告警事件并触发修复流程。
Listens to Redis PubSub alert events and triggers remediation processes.
"""
import asyncio
import json
import logging

from app.core.redis import get_redis
from app.core.config import settings
from app.core.database import async_session

logger = logging.getLogger(__name__)

CHANNEL = "nightmend:alert:new"


async def start_listener():
    """启动告警事件监听器。"""
    redis = await get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe(CHANNEL)
    logger.info(f"Remediation listener subscribed to {CHANNEL}")

    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue

            try:
                data = json.loads(message["data"])
                alert_id = data.get("alert_id")
                if alert_id is None:
                    logger.warning("Received alert event without alert_id, skipping")
                    continue

                logger.info(f"Received alert event: alert_id={alert_id}")

                # 延迟导入避免循环依赖
                from app.remediation.agent import RemediationAgent
                from app.remediation.ai_client import RemediationLLMClient
                from app.remediation.command_executor import CommandExecutor
                from app.remediation.models import RemediationAlert

                # 查询主机信息用于构建 RemediationAlert
                host_name = "unknown"
                service_name = ""
                async with async_session() as db:
                    if data.get("host_id"):
                        from app.models.host import Host
                        from sqlalchemy import select
                        result = await db.execute(select(Host).where(Host.id == data["host_id"]))
                        host = result.scalar_one_or_none()
                        if host:
                            host_name = host.display_hostname

                    if data.get("service_id"):
                        from app.models.service import Service
                        from sqlalchemy import select as sel
                        result = await db.execute(sel(Service).where(Service.id == data["service_id"]))
                        svc = result.scalar_one_or_none()
                        if svc:
                            service_name = svc.name or ""

                    # 从服务名中提取容器/进程名，如 "redis (:6379)" -> "redis"
                    container_name = service_name.split(" (")[0] if service_name else ""

                    # 构建 RemediationAlert
                    labels = {}
                    if service_name:
                        labels["service"] = service_name
                        labels["service_name"] = container_name
                    alert = RemediationAlert(
                        alert_id=alert_id,
                        alert_type=data.get("metric", "unknown"),
                        severity=data.get("severity", "warning"),
                        host=host_name,
                        host_id=data.get("host_id"),
                        message=data.get("title", ""),
                        labels=labels,
                    )

                    ai_client = RemediationLLMClient()
                    executor = CommandExecutor(
                        dry_run=settings.agent_dry_run,
                        remote_host=host_name if host_name != "unknown" else "",
                        ssh_user=settings.agent_ssh_user,
                        ssh_password=settings.agent_ssh_password,
                    )
                    agent = RemediationAgent(ai_client=ai_client, executor=executor)
                    result = await agent.handle_alert(alert, db)
                    await db.commit()

                    if result.success:
                        logger.info(f"Remediation succeeded for alert {alert_id}")
                    else:
                        logger.warning(f"Remediation failed for alert {alert_id}: {result.blocked_reason}")

            except Exception:
                logger.exception("Error handling alert event")
    except asyncio.CancelledError:
        logger.info("Remediation listener shutting down")
    finally:
        await pubsub.unsubscribe(CHANNEL)
        await pubsub.close()
