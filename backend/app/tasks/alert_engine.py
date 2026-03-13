"""
告警引擎任务模块。

后台定时评估所有已启用的告警规则，将最新主机指标与规则阈值进行比对，
触发或恢复告警，并通过通知服务发送告警通知。
支持智能去重和聚合，防止告警风暴。
"""
import asyncio
import json
import logging
import operator as op
from datetime import datetime, timezone, timedelta
from functools import partial

from sqlalchemy import select, and_

from app.core.database import async_session, SessionLocal
from app.core.redis import get_redis
from app.models.alert import Alert, AlertRule
from app.models.host import Host
from app.models.service import Service
from app.services.alert_deduplication import AlertDeduplicationService

logger = logging.getLogger(__name__)

CHECK_INTERVAL = 60  # 检查间隔（秒）

# 支持的比较运算符映射
OPERATORS = {
    ">": op.gt,
    ">=": op.ge,
    "<": op.lt,
    "<=": op.le,
    "==": op.eq,
    "!=": op.ne,
}

# 可从 Redis 缓存中读取的主机指标字段
METRIC_FIELDS = {"cpu_percent", "memory_percent", "disk_percent", "cpu_load_1", "cpu_load_5", "cpu_load_15"}


async def evaluate_host_rules():
    """评估所有已启用的主机类型告警规则，对每台主机逐一检查。"""
    redis = await get_redis()
    async with async_session() as db:
        # 查询所有已启用的主机类型告警规则
        result = await db.execute(
            select(AlertRule).where(
                and_(AlertRule.is_enabled == True, AlertRule.target_type == "host")  # noqa: E712
            )
        )
        rules = result.scalars().all()
        if not rules:
            return

        # 获取所有主机
        result = await db.execute(select(Host))
        hosts = result.scalars().all()

        for host in hosts:
            # 从 Redis 获取该主机的最新指标缓存
            cached = await redis.get(f"metrics:latest:{host.id}")
            if cached:
                try:
                    metrics = json.loads(cached)
                except (json.JSONDecodeError, TypeError):
                    metrics = {}
            else:
                metrics = {}

            # 对每条规则逐一评估
            for rule in rules:
                await _evaluate_rule(db, redis, rule, host, metrics)

        await db.commit()


async def _evaluate_rule(db, redis, rule: AlertRule, host: Host, metrics: dict):
    """评估单条规则在单台主机上是否触发告警。

    处理逻辑：
    1. 获取当前指标值并与阈值比较
    2. 如果违规且有持续时间要求，通过 Redis 跟踪首次违规时间
    3. 达到持续时间后创建告警并发送通知
    4. 如果恢复正常，自动解除告警
    """
    # 特殊指标：主机离线状态
    if rule.metric == "host_offline":
        is_violated = host.status == "offline"
        current_value = 1.0 if is_violated else 0.0
    elif rule.metric in METRIC_FIELDS:
        current_value = metrics.get(rule.metric)
        if current_value is None:
            return  # 无数据则跳过
        cmp_fn = OPERATORS.get(rule.operator)
        if not cmp_fn:
            return
        is_violated = cmp_fn(float(current_value), rule.threshold)
    else:
        return  # 未知指标类型，跳过

    # 查询该规则+主机是否已有触发中的告警
    result = await db.execute(
        select(Alert)
        .where(
            and_(
                Alert.rule_id == rule.id,
                Alert.host_id == host.id,
                Alert.status == "firing",
            )
        )
        .order_by(Alert.fired_at.desc())
        .limit(1)
    )
    existing_alert = result.scalar_one_or_none()

    if is_violated:
        if existing_alert:
            return  # 已在触发状态，无需重复处理

        # 持续时间检查：通过 Redis 记录首次违规时间
        if rule.duration_seconds > 0:
            redis_key = f"alert:pending:{rule.id}:{host.id}"
            first_seen = await redis.get(redis_key)
            now = datetime.now(timezone.utc)
            if first_seen is None:
                # 首次违规，记录时间戳并等待
                await redis.set(redis_key, now.isoformat(), ex=rule.duration_seconds * 2)
                return
            if isinstance(first_seen, bytes):
                first_seen = first_seen.decode('utf-8')
            try:
                first_dt = datetime.fromisoformat(first_seen)
            except (ValueError, TypeError):
                first_dt = datetime.now(timezone.utc)
            if (now - first_dt).total_seconds() < rule.duration_seconds:
                return  # 尚未达到持续时间要求

            # 持续时间已满，清理跟踪键
            await redis.delete(redis_key)

        # 告警去重和聚合检查
        rule_name_en = rule.name_en or rule.name
        alert_title = f"{rule.name} - {host.hostname}"
        alert_title_en = f"{rule_name_en} - {host.hostname}"

        # 用 run_in_executor 包装同步 DB 调用，避免阻塞事件循环
        def _run_dedup_host():
            sync_db = SessionLocal()
            try:
                dedup_service = AlertDeduplicationService(sync_db)
                return dedup_service.process_alert_deduplication(
                    rule, host.id, None, float(current_value), alert_title
                )
            finally:
                sync_db.close()

        loop = asyncio.get_running_loop()
        should_create_alert, dedup_info = await loop.run_in_executor(None, _run_dedup_host)

        if not should_create_alert:
            logger.info(f"Alert suppressed by deduplication: {alert_title} - {dedup_info}")
            return  # 不创建告警，直接返回

        logger.info(f"Alert will be created: {alert_title} - {dedup_info}")

        # 创建新告警
        alert = Alert(
            rule_id=rule.id,
            host_id=host.id,
            severity=rule.severity,
            status="firing",
            title=alert_title,
            title_en=alert_title_en,
            message=f"{rule.metric} = {current_value} {rule.operator} {rule.threshold}",
            metric_value=float(current_value),
            threshold=rule.threshold,
        )
        db.add(alert)
        await db.flush()  # 刷新以获取 alert.id
        logger.info(f"Alert fired: {alert.title}")
        # 发送告警通知
        from app.services.notifier import send_alert_notification
        await send_alert_notification(db, alert)
        # 发布 Redis 事件，供 remediation listener 消费
        await redis.publish("vigilops:alert:new", json.dumps({
            "alert_id": alert.id,
            "rule_id": rule.id,
            "host_id": host.id,
            "severity": rule.severity,
            "metric": rule.metric,
            "metric_value": float(current_value),
            "threshold": rule.threshold,
            "title": alert.title,
        }))

    else:
        # 条件恢复正常，清理持续时间跟踪
        if rule.duration_seconds > 0:
            await redis.delete(f"alert:pending:{rule.id}:{host.id}")

        # 如果存在触发中的告警，标记为已恢复
        if existing_alert:
            existing_alert.status = "resolved"
            existing_alert.resolved_at = datetime.now(timezone.utc)
            logger.info(f"Alert resolved: {existing_alert.title}")
            from app.services.notifier import send_alert_notification
            await send_alert_notification(db, existing_alert)


async def evaluate_service_rules():
    """评估所有已启用的服务类型告警规则，对每个服务逐一检查。"""
    redis = await get_redis()
    async with async_session() as db:
        # 查询所有已启用的服务类型告警规则
        result = await db.execute(
            select(AlertRule).where(
                and_(AlertRule.is_enabled == True, AlertRule.target_type == "service")  # noqa: E712
            )
        )
        rules = result.scalars().all()

        if not rules:
            return

        # 获取所有服务
        result = await db.execute(select(Service))
        services = result.scalars().all()

        for service in services:
            for rule in rules:
                await _evaluate_service_rule(db, redis, rule, service)

        await db.commit()


async def _evaluate_service_rule(db, redis, rule: AlertRule, service: Service):
    """评估单条服务规则是否触发告警。"""
    # service_down: 服务状态为 down 时触发
    if rule.metric == "service_down":
        is_violated = service.status == "down"
        current_value = 1.0 if is_violated else 0.0
    else:
        return  # 未知指标类型，跳过

    # 查询该规则+服务是否已有触发中的告警
    result = await db.execute(
        select(Alert)
        .where(
            and_(
                Alert.rule_id == rule.id,
                Alert.service_id == service.id,
                Alert.status == "firing",
            )
        )
        .order_by(Alert.fired_at.desc())
        .limit(1)
    )
    existing_alert = result.scalar_one_or_none()

    if is_violated:
        if existing_alert:
            return  # 已在触发状态

        # 持续时间检查
        if rule.duration_seconds > 0:
            redis_key = f"alert:pending:{rule.id}:svc:{service.id}"
            first_seen = await redis.get(redis_key)
            now = datetime.now(timezone.utc)
            if first_seen is None:
                await redis.set(redis_key, now.isoformat(), ex=rule.duration_seconds * 2)
                return
            if isinstance(first_seen, bytes):
                first_seen = first_seen.decode('utf-8')
            try:
                first_dt = datetime.fromisoformat(first_seen)
            except (ValueError, TypeError):
                first_dt = datetime.now(timezone.utc)
            if (now - first_dt).total_seconds() < rule.duration_seconds:
                return
            await redis.delete(redis_key)

        # 告警去重
        rule_name_en = rule.name_en or rule.name
        alert_title = f"{rule.name} - {service.name}"
        alert_title_en = f"{rule_name_en} - {service.name}"

        # 用 run_in_executor 包装同步 DB 调用，避免阻塞事件循环
        def _run_dedup_service():
            sync_db = SessionLocal()
            try:
                dedup_service = AlertDeduplicationService(sync_db)
                return dedup_service.process_alert_deduplication(
                    rule, service.host_id, service.id, float(current_value), alert_title
                )
            finally:
                sync_db.close()

        loop = asyncio.get_running_loop()
        should_create, dedup_info = await loop.run_in_executor(None, _run_dedup_service)

        if not should_create:
            logger.info(f"Service alert suppressed: {alert_title} - {dedup_info}")
            return
        logger.info(f"Service alert will be created: {alert_title} - {dedup_info}")

        # 创建告警
        alert = Alert(
            rule_id=rule.id,
            host_id=service.host_id,
            service_id=service.id,
            severity=rule.severity,
            status="firing",
            title=alert_title,
            title_en=alert_title_en,
            message=f"Service {service.name} is {service.status}",
            metric_value=float(current_value),
            threshold=rule.threshold,
        )
        db.add(alert)
        await db.flush()
        logger.info(f"Service alert fired: {alert.title}")

        from app.services.notifier import send_alert_notification
        await send_alert_notification(db, alert)

        # 发布 Redis 事件供 remediation listener 消费
        await redis.publish("vigilops:alert:new", json.dumps({
            "alert_id": alert.id,
            "rule_id": rule.id,
            "host_id": service.host_id,
            "service_id": service.id,
            "severity": rule.severity,
            "metric": rule.metric,
            "metric_value": float(current_value),
            "threshold": rule.threshold,
            "title": alert.title,
        }))

    else:
        # 恢复正常
        if rule.duration_seconds > 0:
            await redis.delete(f"alert:pending:{rule.id}:svc:{service.id}")

        if existing_alert:
            existing_alert.status = "resolved"
            existing_alert.resolved_at = datetime.now(timezone.utc)
            logger.info(f"Service alert resolved: {existing_alert.title}")
            from app.services.notifier import send_alert_notification
            await send_alert_notification(db, existing_alert)


async def alert_engine_loop():
    """告警引擎后台循环，定期执行告警规则评估。"""
    logger.info("Alert engine started")
    while True:
        try:
            await evaluate_host_rules()
            await evaluate_service_rules()
        except Exception:
            logger.exception("Error in alert engine")
        await asyncio.sleep(CHECK_INTERVAL)
