"""
告警去重服务 (Alert Deduplication Service)

实现智能告警去重逻辑，支持：
- 基于冷却期的告警控制（使用规则自身的 cooldown_seconds）
- 分离聚合记录与通知发送
- 持续告警模式：每冷却期发送一次通知
- 静默聚合模式：只在恢复时发送通知

Implements intelligent alert deduplication logic.
Supports:
- Cooldown-based alert control (using rule's own cooldown_seconds)
- Separated aggregation records from notification sending
- Continuous alert mode: send notification every cooldown period
- Silent aggregation mode: send notification only on recovery
"""
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models.alert import AlertRule
from app.models.alert_group import AlertDeduplication

logger = logging.getLogger(__name__)


class AlertDeduplicationService:
    """告警去重服务类"""

    def __init__(self, db: Session):
        self.db = db

    def generate_alert_fingerprint(self, rule_id: int, host_id: Optional[int],
                                   service_id: Optional[int], metric: str) -> str:
        """
        生成告警指纹，        用于唯一标识一条告警（规则 + 主机/服务 + 指标）

        Args:
            rule_id: 告警规则 ID
            host_id: 主机 ID
            service_id: 服务 ID
            metric: 监控指标名

        Returns:
            str: 告警指纹哈希值
        """
        identifier = f"{rule_id}:{host_id or 'none'}:{service_id or 'none'}:{metric}"
        return hashlib.md5(identifier.encode()).hexdigest()

    def get_or_create_dedup_record(self, rule: AlertRule, host_id: Optional[int],
                                   service_id: Optional[int]) -> Tuple[AlertDeduplication, bool]:
        """
        获取或创建去重记录

        Returns:
            Tuple[AlertDeduplication, bool]: (去重记录, 是否新建)
        """
        fingerprint = self.generate_alert_fingerprint(rule.id, host_id, service_id, rule.metric)

        existing = self.db.query(AlertDeduplication).filter(
            AlertDeduplication.fingerprint == fingerprint
        ).first()

        if existing:
            return existing, False

        # 创建新的去重记录
        now = datetime.now(timezone.utc)
        new_record = AlertDeduplication(
            fingerprint=fingerprint,
            rule_id=rule.id,
            host_id=host_id,
            service_id=service_id,
            first_violation_time=now,
            first_alert_time=None,  # 尚未触发告警
            last_alert_time=None,
            last_check_time=now,
            occurrence_count=1,
            alert_sent_count=0,
            alert_triggered=False,
            suppressed=False,
            recovery_start_time=None
        )
        self.db.add(new_record)

        try:
            self.db.commit()
            logger.info(f"Created new dedup record for rule {rule.id}")
            return new_record, True
        except IntegrityError:
            # 并发插入冲突：其他请求已创建记录，回滚并重新查询
            self.db.rollback()
            logger.warning(f"Concurrent insert conflict for fingerprint {fingerprint}, retrying...")

            existing = self.db.query(AlertDeduplication).filter(
                AlertDeduplication.fingerprint == fingerprint
            ).first()

            if existing:
                return existing, False

            # 如果仍然不存在（极罕见），再次尝试创建
            self.db.add(new_record)
            self.db.commit()
            logger.info(f"Retry: Created new dedup record for rule {rule.id}")
            return new_record, True

    def process_alert_evaluation(self, rule: AlertRule, host_id: Optional[int],
                                service_id: Optional[int], metric_value: float,
                                alert_title: str) -> Dict:
        """
        处理告警评估结果

        核心逻辑：
        1. 持续时间判断由 alert_engine 通过 Redis 历史数据完成
        2. 此方法只负责去重记录的更新和通知决策

        Args:
            rule: 告警规则
            host_id: 主机 ID
            service_id: 服务 ID
            metric_value: 当前指标值
            alert_title: 告警标题

        Returns:
            Dict: {
                "should_send_notification": bool,  # 是否发送通知
                "notification_type": str,        # first/continuous/recovery
                "dedup_record": AlertDeduplication,
                "duration_seconds": int,         # 持续时长（秒）
                "message": str                   # 处理信息
            }
        """
        now = datetime.now(timezone.utc)
        cooldown_seconds = rule.cooldown_seconds or 300  # 默认 5 分钟

        # 获取或创建去重记录
        dedup_record, is_new = self.get_or_create_dedup_record(rule, host_id, service_id)

        # 更新检查时间和违规计数
        dedup_record.last_check_time = now
        dedup_record.occurrence_count += 1

        result = {
            "should_send_notification": False,
            "notification_type": None,
            "dedup_record": dedup_record,
            "duration_seconds": 0,
            "message": ""
        }

        # 检查是否首次告警
        if not dedup_record.alert_triggered:
            # 首次告警触发
            dedup_record.first_alert_time = now
            dedup_record.last_alert_time = now
            dedup_record.alert_triggered = True
            dedup_record.alert_sent_count = 1
            dedup_record.recovery_start_time = None  # 清除恢复计时

            result["should_send_notification"] = True
            result["notification_type"] = "first"
            result["message"] = "首次告警，发送通知"

            self.db.commit()
            logger.info(f"First alert triggered: {alert_title}")
            return result

        # 已有告警，计算持续时长
        if dedup_record.first_alert_time:
            # 确保 first_alert_time 是带时区的
            first_alert_time = dedup_record.first_alert_time
            if first_alert_time.tzinfo is None:
                first_alert_time = first_alert_time.replace(tzinfo=timezone.utc)
            duration = (now - first_alert_time).total_seconds()
            result["duration_seconds"] = int(duration)

        # 检查冷却期
        last_alert_time = dedup_record.last_alert_time or now
        if last_alert_time.tzinfo is None:
            last_alert_time = last_alert_time.replace(tzinfo=timezone.utc)
        time_since_last_alert = (now - last_alert_time).total_seconds()

        # 判断是否需要发送持续告警
        if rule.continuous_alert:
            # 持续告警模式：检查冷却期是否已过
            if time_since_last_alert >= cooldown_seconds:
                # 冷却期已过，发送持续告警
                dedup_record.last_alert_time = now
                dedup_record.alert_sent_count += 1

                result["should_send_notification"] = True
                result["notification_type"] = "continuous"
                result["message"] = f"持续告警，已持续 {result['duration_seconds']}秒，发送通知"

                self.db.commit()
                logger.info(f"Continuous alert: {alert_title}, duration: {result['duration_seconds']}s")
                return result
            else:
                # 冷却期内，抑制
                remaining = cooldown_seconds - time_since_last_alert
                result["message"] = f"冷却期内，剩余 {int(remaining)}秒"

                self.db.commit()
                return result
        else:
            # 静默聚合模式：不发送通知，只更新聚合
            result["message"] = f"静默聚合模式，累计违规 {dedup_record.occurrence_count} 次"

            self.db.commit()
            return result

    def process_recovery(self, rule: AlertRule, host_id: Optional[int],
                        service_id: Optional[int]) -> Dict:
        """
        处理告警恢复

        Args:
            rule: 告警规则
            host_id: 主机 ID
            service_id: 服务 ID

        Returns:
            Dict: {
                "should_send_notification": bool,  # 是否发送恢复通知
                "dedup_record": AlertDeduplication,
                "duration_seconds": int,         # 持续时长
                "message": str
            }
        """
        fingerprint = self.generate_alert_fingerprint(rule.id, host_id, service_id, rule.metric)

        dedup_record = self.db.query(AlertDeduplication).filter(
            AlertDeduplication.fingerprint == fingerprint
        ).first()

        result = {
            "should_send_notification": False,
            "dedup_record": dedup_record,
            "duration_seconds": 0,
            "message": "无去重记录"
        }

        if not dedup_record:
            return result

        now = datetime.now(timezone.utc)

        # 计算持续时长
        if dedup_record.first_alert_time:
            # 确保 first_alert_time 是带时区的
            first_alert_time = dedup_record.first_alert_time
            if first_alert_time.tzinfo is None:
                first_alert_time = first_alert_time.replace(tzinfo=timezone.utc)
            duration = (now - first_alert_time).total_seconds()
            result["duration_seconds"] = int(duration)

        # 只有触发过告警才发送恢复通知
        if dedup_record.alert_triggered:
            result["should_send_notification"] = True
            result["message"] = f"告警恢复，持续时长 {result['duration_seconds']}秒"

            logger.info(f"Alert recovery: rule {rule.id}, duration: {result['duration_seconds']}s")

        # 删除去重记录（恢复后允许立即重新触发）
        self.db.delete(dedup_record)
        self.db.commit()

        return result

    def cleanup_expired_records(self, max_age_hours: int = 24) -> int:
        """
        清理过期的去重记录

        Args:
            max_age_hours: 最大保留时间（小时）

        Returns:
            int: 清理的记录数
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)

        count = self.db.query(AlertDeduplication).filter(
            AlertDeduplication.last_check_time < cutoff
        ).delete()

        self.db.commit()

        if count > 0:
            logger.info(f"Cleaned up {count} expired dedup records")

        return count
