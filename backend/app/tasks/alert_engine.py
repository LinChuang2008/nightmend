"""
告警引擎任务模块（重构版）

后台定时评估所有已启用的告警规则，利用 Redis 历史数据进行精确持续时间判断
支持持续告警和静默聚合两种模式

核心改进：
1. 使用 Redis 历史数据判断指标是否真正持续违规
2. 分离聚合记录与通知发送
3. 支持续告警模式（每冷却期发送）和静默聚合模式（仅恢复时发送）
4. 恢复时始终发送通知并报告持续时长
"""
import asyncio
import json
import logging
import operator as op
from datetime import datetime, timezone, timedelta
from typing import Dict, List

from sqlalchemy import select, and_

from app.core.database import async_session, SessionLocal
from app.core.redis import get_redis
from app.models.alert import Alert, AlertRule
from app.models.host import Host
from app.models.service import Service
from app.services.alert_deduplication import AlertDeduplicationService
from app.services.suppression_service import SuppressionService

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


async def _check_suppression_for_host(
    db,
    host_id: int,
    alert_rule_id: int,
    check_type: str = "alerts"
) -> bool:
    """检查主机是否被屏蔽 (Check if Host is Suppressed)

    Args:
        db: 数据库会话
        host_id: 主机 ID
        alert_rule_id: 告警规则 ID
        check_type: 检查类型（alerts/notifications）

    Returns:
        bool: True 表示被屏蔽，False 表示未被屏蔽
    """
    try:
        suppression_service = SuppressionService(db)
        return await suppression_service.is_suppressed(
            resource_type=SuppressionService.RESOURCE_HOST,
            resource_id=host_id,
            alert_rule_id=alert_rule_id,
            check_type=check_type
        )
    except Exception as e:
        logger.warning(f"Failed to check suppression for host {host_id}: {e}")
        return False


async def _check_suppression_for_service(
    db,
    service_id: int,
    host_id: int,
    alert_rule_id: int,
    check_type: str = "alerts"
) -> bool:
    """检查服务是否被屏蔽 (Check if Service is Suppressed)

    Args:
        db: 数据库会话
        service_id: 服务 ID
        host_id: 主机 ID
        alert_rule_id: 告警规则 ID
        check_type: 检查类型（alerts/notifications）

    Returns:
        bool: True 表示被屏蔽，False 表示未被屏蔽
    """
    try:
        suppression_service = SuppressionService(db)
        return await suppression_service.is_suppressed(
            resource_type=SuppressionService.RESOURCE_SERVICE,
            resource_id=service_id,
            alert_rule_id=alert_rule_id,
            check_type=check_type
        )
    except Exception as e:
        logger.warning(f"Failed to check suppression for service {service_id}: {e}")
        return False


async def get_metrics_history(redis, host_id: int) -> List[Dict]:
    """
    从 Redis 获取指标历史数据

    Args:
        redis: Redis 客户端
        host_id: 主机 ID

    Returns:
        List[Dict]: 指标历史列表，按时间升序排列
    """
    history_key = f"metrics:history:{host_id}"
    try:
        data = await redis.get(history_key)
        if data:
            history = json.loads(data)
            return history
    except Exception as e:
        logger.warning(f"Failed to get metrics history for host {host_id}: {e}")
    return []


async def check_duration_continuously_violated(
    redis,
    host_id: int,
    rule: AlertRule,
    current_value: float
) -> bool:
    """
    检查指标是否持续违规（精确判断）

    利用 Redis 历史数据判断在过去 duration_seconds 秒内是否一直违规

    Args:
        redis: Redis 客户端
        host_id: 主机 ID
        rule: 告警规则
        current_value: 当前值

    Returns:
        bool: 是否持续违规
    """
    if rule.duration_seconds <= 0:
        # 没有持续时间要求，当前违规即可
        return True

    history = await get_metrics_history(redis, host_id)

    if not history:
        # 没有历史数据，无法判断
        return False

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=rule.duration_seconds)

    cmp_fn = OPERATORS.get(rule.operator)
    if not cmp_fn:
        return False

    # 筛选出在持续时间窗口内的数据点
    relevant_points = []
    for point in history:
        try:
            ts_str = point.get("ts")
            if ts_str:
                ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                if ts >= cutoff:
                    relevant_points.append(point)
        except (ValueError, TypeError):
            continue

    if not relevant_points:
        return False

    # 检查所有数据点是否都违规
    for point in relevant_points:
        value = point.get(rule.metric)
        if value is None:
            return False
        if not cmp_fn(float(value), rule.threshold):
            return False

    logger.debug(f"Host {host_id} {rule.metric} continuously violated for {rule.duration_seconds}s")
    return True


async def check_duration_continuously_normal(
    redis,
    host_id: int,
    rule: AlertRule
) -> bool:
    """
    检查指标是否持续正常（精确判断）

    利用 Redis 历史数据判断在过去 duration_seconds 秒内是否一直正常

    Args:
        redis: Redis 客户端
        host_id: 主机 ID
        rule: 告警规则

    Returns:
        bool: 是否持续正常
    """
    if rule.duration_seconds <= 0:
        return True

    history = await get_metrics_history(redis, host_id)

    if not history:
        return True  # 没有历史数据，假设正常

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=rule.duration_seconds)

    cmp_fn = OPERATORS.get(rule.operator)
    if not cmp_fn:
        return True

    # 筛选出在持续时间窗口内的数据点
    relevant_points = []
    for point in history:
        try:
            ts_str = point.get("ts")
            if ts_str:
                ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                if ts >= cutoff:
                    relevant_points.append(point)
        except (ValueError, TypeError):
            continue

    if not relevant_points:
        return True

    # 检查所有数据点是否都正常
    for point in relevant_points:
        value = point.get(rule.metric)
        if value is not None and cmp_fn(float(value), rule.threshold):
            return False

    logger.debug(f"Host {host_id} {rule.metric} continuously normal for {rule.duration_seconds}s")
    return True


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
            logger.debug("No enabled host alert rules found")
            return

        logger.info(f"Evaluating {len(rules)} host alert rules")

        # 获取所有主机
        result = await db.execute(select(Host))
        hosts = result.scalars().all()
        logger.info(f"Found {len(hosts)} hosts to evaluate")

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
    """评估单条规则在单台主机上是否触发告警（重构版）

    使用新的告警机制：
    1. 精确持续时间判断（基于 Redis 历史）
    2. 分离聚合与通知
    3. 支持续告警和静默聚合两种模式
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

    # 调用去重服务处理评估结果
    def _run_dedup_service():
        sync_db = SessionLocal()
        try:
            dedup_service = AlertDeduplicationService(sync_db)
            if is_violated:
                return dedup_service.process_alert_evaluation(
                    rule, host.id, None, float(current_value),
                    f"{rule.name} - {host.display_hostname}"
                )
            else:
                return dedup_service.process_recovery(rule, host.id, None)
        finally:
            sync_db.close()

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, _run_dedup_service)

    if is_violated:
        # === 违规处理 ===
        # 首先检查是否真正持续违规（精确判断）
        is_continuously_violated = await check_duration_continuously_violated(
            redis, host.id, rule, float(current_value)
        )

        if not is_continuously_violated:
            # 未达到持续时间要求，不处理
            return

        # 检查是否已有活跃告警
        existing_alert_result = await db.execute(
            select(Alert)
            .where(
                and_(
                    Alert.rule_id == rule.id,
                    Alert.host_id == host.id,
                    Alert.status.in_(["firing", "acknowledged"]),
                )
            )
            .order_by(Alert.fired_at.desc())
            .limit(1)
        )
        existing_alert = existing_alert_result.scalar_one_or_none()

        if existing_alert:
            # 已有活跃告警，检查是否需要发送持续告警通知
            if result["should_send_notification"] and result["notification_type"] == "continuous":
                # 检查是否屏蔽通知
                if await _check_suppression_for_host(db, host.id, rule.id, check_type="notifications"):
                    logger.debug(f"Host {host.id} notifications are suppressed for rule {rule.id}")
                    return

                # 更新告警记录的当前指标值和消息
                existing_alert.metric_value = float(current_value)
                duration_seconds = result["duration_seconds"]
                if rule.metric == "host_offline":
                    existing_alert.message = f"主机 {host.display_hostname} 已离线 (已持续 {duration_seconds}秒)"
                else:
                    existing_alert.message = f"{rule.metric} = {current_value} {rule.operator} {rule.threshold} (已持续 {duration_seconds}秒)"
                await db.flush()

                logger.info(f"Sending continuous alert notification for existing alert: {existing_alert.title}")

                from app.services.notifier import send_alert_notification
                await send_alert_notification(
                    db, existing_alert,
                    notification_type=result["notification_type"],
                    duration_seconds=duration_seconds
                )
            return

        if result["should_send_notification"]:
            # 检查是否屏蔽告警创建
            if await _check_suppression_for_host(db, host.id, rule.id, check_type="alerts"):
                logger.debug(f"Host {host.id} alert creation is suppressed for rule {rule.id}")
                return

            # 发送首次告警或持续告警通知
            notification_type = result["notification_type"]
            duration_seconds = result["duration_seconds"]

            # 创建告警记录
            rule_name_en = rule.name_en or rule.name
            alert_title = f"{rule.name} - {host.display_hostname}"
            alert_title_en = f"{rule_name_en} - {host.display_hostname}"

            if rule.metric == "host_offline":
                if notification_type == "first":
                    message = f"主机 {host.display_hostname} 已离线"
                else:
                    message = f"主机 {host.display_hostname} 已离线 (已持续 {duration_seconds}秒)"
            else:
                if notification_type == "first":
                    message = f"{rule.metric} = {current_value} {rule.operator} {rule.threshold}"
                else:
                    message = f"{rule.metric} = {current_value} {rule.operator} {rule.threshold} (已持续 {duration_seconds}秒)"

            alert = Alert(
                rule_id=rule.id,
                host_id=host.id,
                severity=rule.severity,
                status="firing",
                title=alert_title,
                title_en=alert_title_en,
                message=message,
                metric_value=float(current_value),
                threshold=rule.threshold,
            )
            db.add(alert)
            await db.flush()
            logger.info(f"Alert fired ({notification_type}): {alert.title}")

            # 发送通知（传递通知类型和持续时长）
            from app.services.notifier import send_alert_notification
            await send_alert_notification(
                db, alert,
                notification_type=notification_type,
                duration_seconds=duration_seconds
            )

            # 发布 Redis 事件
            await redis.publish("nightmend:alert:new", json.dumps({
                "alert_id": alert.id,
                "rule_id": rule.id,
                "host_id": host.id,
                "severity": rule.severity,
                "metric": rule.metric,
                "metric_value": float(current_value),
                "threshold": rule.threshold,
                "title": alert.title,
                "notification_type": notification_type,
                "duration_seconds": duration_seconds,
            }))
    else:
        # === 恢复处理 ===
        # 检查是否去重服务允许发送恢复通知
        if not result.get("should_send_notification"):
            # 去重记录不存在或未触发过告警，不发送通知
            return

        # 检查是否持续恢复正常
        is_continuously_normal = await check_duration_continuously_normal(redis, host.id, rule)

        if not is_continuously_normal:
            # 尚未持续正常，不处理恢复
            return

        # 检查是否有活跃告警需要恢复
        existing_alert_result = await db.execute(
            select(Alert)
            .where(
                and_(
                    Alert.rule_id == rule.id,
                    Alert.host_id == host.id,
                    Alert.status.in_(["firing", "acknowledged"]),
                )
            )
            .order_by(Alert.fired_at.desc())
            .limit(1)
        )
        existing_alert = existing_alert_result.scalar_one_or_none()

        if existing_alert:
            # 标记告警已恢复
            existing_alert.status = "resolved"
            existing_alert.resolved_at = datetime.now(timezone.utc)

            duration_seconds = result.get("duration_seconds", 0)
            logger.info(f"Alert resolved: {existing_alert.title} (持续 {duration_seconds}秒)")

            # 检查是否屏蔽恢复通知
            if not await _check_suppression_for_host(db, host.id, rule.id, check_type="notifications"):
                # 发送恢复通知（传递通知类型和持续时长）
                from app.services.notifier import send_alert_notification
                await send_alert_notification(
                    db, existing_alert,
                    notification_type="recovery",
                    duration_seconds=duration_seconds
                )


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

        # 获取所有离线主机的 ID 集合，主机离线时其服务告警无意义
        offline_result = await db.execute(
            select(Host.id).where(Host.status == "offline")
        )
        offline_host_ids = {row[0] for row in offline_result.fetchall()}

        # 获取所有服务
        result = await db.execute(select(Service))
        services = result.scalars().all()

        for service in services:
            # 若服务关联的主机已离线，跳过告警评估
            # 主机离线时服务必然不可达，不应产生独立的服务告警噪音
            if service.host_id and service.host_id in offline_host_ids:
                logger.debug(
                    f"Skipping service {service.name} (id={service.id}): "
                    f"host {service.host_id} is offline"
                )
                continue

            for rule in rules:
                await _evaluate_service_rule(db, redis, rule, service)

        await db.commit()


async def _evaluate_service_rule(db, redis, rule: AlertRule, service: Service):
    """评估单条服务规则是否触发告警（重构版）"""
    # service_down: 服务状态为 down 时触发
    if rule.metric == "service_down":
        is_violated = service.status == "down"
        current_value = 1.0 if is_violated else 0.0
    else:
        return  # 未知指标类型，跳过

    # 调用去重服务处理评估结果
    def _run_dedup_service():
        sync_db = SessionLocal()
        try:
            dedup_service = AlertDeduplicationService(sync_db)
            if is_violated:
                return dedup_service.process_alert_evaluation(
                    rule, service.host_id, service.id, float(current_value),
                    f"{rule.name} - {service.name}"
                )
            else:
                return dedup_service.process_recovery(rule, service.host_id, service.id)
        finally:
            sync_db.close()

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, _run_dedup_service)

    if is_violated:
        # === 违规处理 ===
        # 首先检查是否真正持续违规（精确判断）
        if service.host_id:
            is_continuously_violated = await check_duration_continuously_violated(
                redis, service.host_id, rule, float(current_value)
            )
            if not is_continuously_violated:
                # 未达到持续时间要求，不处理
                return

        # 检查是否已有活跃告警
        existing_alert_result = await db.execute(
            select(Alert)
            .where(
                and_(
                    Alert.rule_id == rule.id,
                    Alert.service_id == service.id,
                    Alert.status.in_(["firing", "acknowledged"]),
                )
            )
            .order_by(Alert.fired_at.desc())
            .limit(1)
        )
        existing_alert = existing_alert_result.scalar_one_or_none()

        if existing_alert:
            # 已有活跃告警，检查是否需要发送持续告警通知
            if result["should_send_notification"] and result["notification_type"] == "continuous":
                # 检查是否屏蔽通知
                if await _check_suppression_for_service(db, service.id, service.host_id, rule.id, check_type="notifications"):
                    logger.debug(f"Service {service.id} notifications are suppressed for rule {rule.id}")
                    return

                # 更新告警记录的当前指标值和消息
                existing_alert.metric_value = float(current_value)
                duration_seconds = result["duration_seconds"]
                existing_alert.message = f"Service {service.name} is {service.status} (已持续 {duration_seconds}秒)"
                await db.flush()

                logger.info(f"Sending continuous alert notification for existing service alert: {existing_alert.title}")

                from app.services.notifier import send_alert_notification
                await send_alert_notification(
                    db, existing_alert,
                    notification_type=result["notification_type"],
                    duration_seconds=duration_seconds
                )
            return

        if result["should_send_notification"]:
            # 检查是否屏蔽告警创建
            if await _check_suppression_for_service(db, service.id, service.host_id, rule.id, check_type="alerts"):
                logger.debug(f"Service {service.id} alert creation is suppressed for rule {rule.id}")
                return

            notification_type = result["notification_type"]
            duration_seconds = result["duration_seconds"]

            # 创建告警
            rule_name_en = rule.name_en or rule.name
            alert_title = f"{rule.name} - {service.name}"
            alert_title_en = f"{rule_name_en} - {service.name}"

            if notification_type == "first":
                message = f"Service {service.name} is {service.status}"
            else:
                message = f"Service {service.name} is {service.status} (已持续 {duration_seconds}秒)"

            alert = Alert(
                rule_id=rule.id,
                host_id=service.host_id,
                service_id=service.id,
                severity=rule.severity,
                status="firing",
                title=alert_title,
                title_en=alert_title_en,
                message=message,
                metric_value=float(current_value),
                threshold=rule.threshold,
            )
            db.add(alert)
            await db.flush()
            logger.info(f"Service alert fired ({notification_type}): {alert.title}")

            from app.services.notifier import send_alert_notification
            await send_alert_notification(
                db, alert,
                notification_type=notification_type,
                duration_seconds=duration_seconds
            )

            await redis.publish("nightmend:alert:new", json.dumps({
                "alert_id": alert.id,
                "rule_id": rule.id,
                "host_id": service.host_id,
                "service_id": service.id,
                "severity": rule.severity,
                "metric": rule.metric,
                "metric_value": float(current_value),
                "threshold": rule.threshold,
                "title": alert.title,
                "notification_type": notification_type,
                "duration_seconds": duration_seconds,
            }))
    else:
        # === 恢复处理 ===
        # 检查是否去重服务允许发送恢复通知
        if not result.get("should_send_notification"):
            # 去重记录不存在或未触发过告警，不发送通知
            return

        existing_alert_result = await db.execute(
            select(Alert)
            .where(
                and_(
                    Alert.rule_id == rule.id,
                    Alert.service_id == service.id,
                    Alert.status.in_(["firing", "acknowledged"]),
                )
            )
            .order_by(Alert.fired_at.desc())
            .limit(1)
        )
        existing_alert = existing_alert_result.scalar_one_or_none()

        if existing_alert:
            existing_alert.status = "resolved"
            existing_alert.resolved_at = datetime.now(timezone.utc)

            duration_seconds = result.get("duration_seconds", 0)
            logger.info(f"Service alert resolved: {existing_alert.title} (持续 {duration_seconds}秒)")

            # 检查是否屏蔽恢复通知
            if not await _check_suppression_for_service(db, service.id, service.host_id, rule.id, check_type="notifications"):
                # 发送恢复通知
                from app.services.notifier import send_alert_notification
                await send_alert_notification(
                    db, existing_alert,
                    notification_type="recovery",
                    duration_seconds=duration_seconds
                )


async def cleanup_orphaned_alerts():
    """清理孤立的 firing 告警（对应的主机或服务已删除）。"""
    async with async_session() as db:
        # 查找 service_id 不存在的 firing 告警
        result = await db.execute(
            select(Alert).where(
                and_(
                    Alert.status == "firing",
                    Alert.service_id.isnot(None)
                )
            )
        )
        service_alerts = result.scalars().all()

        orphaned_count = 0
        for alert in service_alerts:
            service_result = await db.execute(
                select(Service).where(Service.id == alert.service_id)
            )
            if service_result.scalar_one_or_none() is None:
                alert.status = "resolved"
                alert.resolved_at = datetime.now(timezone.utc)
                orphaned_count += 1
                logger.warning(f"Resolved orphaned service alert: {alert.title}")

        # 查找 host_id 不存在的 firing 告警
        result = await db.execute(
            select(Alert).where(
                and_(
                    Alert.status == "firing",
                    Alert.host_id.isnot(None)
                )
            )
        )
        host_alerts = result.scalars().all()

        for alert in host_alerts:
            host_result = await db.execute(
                select(Host).where(Host.id == alert.host_id)
            )
            if host_result.scalar_one_or_none() is None:
                alert.status = "resolved"
                alert.resolved_at = datetime.now(timezone.utc)
                orphaned_count += 1
                logger.warning(f"Resolved orphaned host alert: {alert.title}")

        if orphaned_count > 0:
            await db.commit()
            logger.info(f"Cleaned up {orphaned_count} orphaned firing alerts")
        else:
            logger.info("No orphaned alerts found")


async def alert_engine_loop():
    """告警引擎后台循环，定期执行告警规则评估。"""
    logger.info("Alert engine started (refactored)")
    await cleanup_orphaned_alerts()
    iteration_count = 0
    while True:
        try:
            await evaluate_host_rules()
            await evaluate_service_rules()
        except Exception:
            logger.exception("Error in alert engine")
        iteration_count += 1
        # 每 10 个周期（约 10 分钟）清理一次孤立告警
        if iteration_count % 10 == 0:
            try:
                await cleanup_orphaned_alerts()
            except Exception:
                logger.exception("Error in orphaned alert cleanup")
        await asyncio.sleep(CHECK_INTERVAL)
