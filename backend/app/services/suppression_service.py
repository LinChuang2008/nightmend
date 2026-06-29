"""
屏蔽规则服务 (Suppression Rule Service)

提供统一的告警屏蔽/忽略功能，支持各种监控维度的告警控制。
核心功能：检查屏蔽状态、创建屏蔽规则、管理屏蔽规则。

Provides unified alert suppression/ignore functionality across various monitoring dimensions.
Core functions: Check suppression status, create suppression rules, manage suppression rules.
"""
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.suppression_rule import SuppressionRule

logger = logging.getLogger(__name__)


class SuppressionService:
    """屏蔽规则服务类 (Suppression Rule Service Class)

    提供屏蔽规则的创建、查询、检查和管理功能。
    用于在告警引擎、通知服务、AI分析等模块中检查是否需要屏蔽某个操作。
    """

    # 资源类型常量 (Resource Type Constants)
    RESOURCE_HOST = "host"
    RESOURCE_SERVICE = "service"
    RESOURCE_ALERT_RULE = "alert_rule"
    RESOURCE_LOG_KEYWORD = "log_keyword"
    RESOURCE_GENERAL = "general"

    def __init__(self, db: AsyncSession):
        """初始化服务 (Initialize Service)

        Args:
            db: SQLAlchemy 异步数据库会话 (Async database session)
        """
        self.db = db

    async def is_suppressed(
        self,
        resource_type: str,
        resource_id: Optional[int] = None,
        resource_pattern: Optional[str] = None,
        alert_rule_id: Optional[int] = None,
        check_type: str = "all"
    ) -> bool:
        """检查是否被屏蔽 (Check if Suppressed)

        检查指定的资源是否被屏蔽规则覆盖。

        Args:
            resource_type: 资源类型（host/service/alert_rule/log_keyword/general）
            resource_id: 资源 ID（如 host_id, service_id）
            resource_pattern: 资源匹配模式（如日志关键词）
            alert_rule_id: 告警规则 ID
            check_type: 检查类型（all/alerts/notification/ai_analysis/log_scan）

        Returns:
            bool: True 表示被屏蔽，False 表示未被屏蔽
        """
        now = datetime.now(timezone.utc)

        # 构建查询条件
        conditions = [
            SuppressionRule.is_active == True,
            SuppressionRule.resource_type == resource_type,
        ]

        # 时间范围检查
        conditions.append(
            or_(
                SuppressionRule.start_time == None,
                SuppressionRule.start_time <= now
            )
        )
        conditions.append(
            or_(
                SuppressionRule.end_time == None,
                SuppressionRule.end_time >= now
            )
        )

        # 资源 ID 匹配
        if resource_id is not None:
            conditions.append(
                or_(
                    SuppressionRule.resource_id == None,
                    SuppressionRule.resource_id == resource_id
                )
            )
        else:
            conditions.append(SuppressionRule.resource_id == None)

        # 告警规则 ID 匹配
        if alert_rule_id is not None:
            conditions.append(
                or_(
                    SuppressionRule.alert_rule_id == None,
                    SuppressionRule.alert_rule_id == alert_rule_id
                )
            )
        else:
            conditions.append(SuppressionRule.alert_rule_id == None)

        # 检查类型过滤
        if check_type == "alerts":
            conditions.append(SuppressionRule.suppress_alerts == True)
        elif check_type == "notifications":
            conditions.append(SuppressionRule.suppress_notifications == True)
        elif check_type == "ai_analysis":
            conditions.append(SuppressionRule.suppress_ai_analysis == True)
        elif check_type == "log_scan":
            conditions.append(SuppressionRule.suppress_log_scan == True)

        # 执行查询
        result = await self.db.execute(
            select(SuppressionRule).where(and_(*conditions))
        )
        rules = result.scalars().all()

        if rules:
            # 更新匹配计数
            for rule in rules:
                rule.match_count += 1
            await self.db.commit()

            logger.debug(
                f"Resource {resource_type}:{resource_id} is suppressed by {len(rules)} rule(s)"
            )
            return True

        return False

    async def create_rule(
        self,
        resource_type: str,
        created_by: Optional[str] = None,
        resource_id: Optional[int] = None,
        resource_pattern: Optional[str] = None,
        alert_rule_id: Optional[int] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        suppress_alerts: bool = True,
        suppress_notifications: bool = True,
        suppress_ai_analysis: bool = True,
        suppress_log_scan: bool = False,
        reason: Optional[str] = None
    ) -> SuppressionRule:
        """创建屏蔽规则 (Create Suppression Rule)

        Args:
            resource_type: 资源类型
            created_by: 创建人
            resource_id: 资源 ID
            resource_pattern: 资源匹配模式
            alert_rule_id: 告警规则 ID
            start_time: 开始时间
            end_time: 结束时间
            suppress_alerts: 是否屏蔽告警
            suppress_notifications: 是否屏蔽通知
            suppress_ai_analysis: 是否屏蔽 AI 分析
            suppress_log_scan: 是否屏蔽日志扫描
            reason: 屏蔽原因

        Returns:
            SuppressionRule: 创建的屏蔽规则
        """
        rule = SuppressionRule(
            resource_type=resource_type,
            resource_id=resource_id,
            resource_pattern=resource_pattern,
            alert_rule_id=alert_rule_id,
            start_time=start_time,
            end_time=end_time,
            suppress_alerts=suppress_alerts,
            suppress_notifications=suppress_notifications,
            suppress_ai_analysis=suppress_ai_analysis,
            suppress_log_scan=suppress_log_scan,
            reason=reason,
            created_by=created_by,
            is_active=True,
            match_count=0
        )
        self.db.add(rule)
        await self.db.commit()
        await self.db.refresh(rule)

        logger.info(
            f"Created suppression rule {rule.id} for {resource_type}:{resource_id} "
            f"by {created_by or 'unknown'} - {reason or 'no reason'}"
        )
        return rule

    async def get_active_rules(
        self,
        resource_type: Optional[str] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Dict[str, Any]:
        """获取活跃的屏蔽规则列表 (Get Active Suppression Rules)

        Args:
            resource_type: 资源类型过滤（可选）
            page: 页码
            page_size: 每页数量

        Returns:
            Dict: 包含 items, total, page, page_size
        """
        conditions = [SuppressionRule.is_active == True]

        if resource_type:
            conditions.append(SuppressionRule.resource_type == resource_type)

        # 查询总数
        count_result = await self.db.execute(
            select(SuppressionRule.id).where(and_(*conditions))
        )
        total = len(count_result.all())

        # 查询数据
        result = await self.db.execute(
            select(SuppressionRule)
            .where(and_(*conditions))
            .order_by(SuppressionRule.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = result.scalars().all()

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size
        }

    async def update_rule(
        self,
        rule_id: int,
        **kwargs
    ) -> Optional[SuppressionRule]:
        """更新屏蔽规则 (Update Suppression Rule)

        Args:
            rule_id: 规则 ID
            **kwargs: 要更新的字段

        Returns:
            SuppressionRule: 更新后的规则，不存在则返回 None
        """
        result = await self.db.execute(
            select(SuppressionRule).where(SuppressionRule.id == rule_id)
        )
        rule = result.scalar_one_or_none()

        if not rule:
            return None

        for key, value in kwargs.items():
            if hasattr(rule, key) and value is not None:
                setattr(rule, key, value)

        await self.db.commit()
        await self.db.refresh(rule)

        logger.info(f"Updated suppression rule {rule_id}")
        return rule

    async def delete_rule(self, rule_id: int) -> bool:
        """删除屏蔽规则（软删除，设置 is_active=False） (Delete Suppression Rule)

        Args:
            rule_id: 规则 ID

        Returns:
            bool: 删除成功返回 True，规则不存在返回 False
        """
        result = await self.db.execute(
            select(SuppressionRule).where(SuppressionRule.id == rule_id)
        )
        rule = result.scalar_one_or_none()

        if not rule:
            return False

        rule.is_active = False
        await self.db.commit()

        logger.info(f"Deactivated suppression rule {rule_id}")
        return True

    async def quick_suppress(
        self,
        resource_type: str,
        resource_id: int,
        created_by: Optional[str] = None,
        reason: Optional[str] = None,
        duration_hours: Optional[float] = None
    ) -> SuppressionRule:
        """快速创建屏蔽规则 (Quick Create Suppression Rule)

        用于前端"忽略"按钮快速屏蔽，简化参数。

        Args:
            resource_type: 资源类型（host/service）
            resource_id: 资源 ID
            created_by: 创建人
            reason: 屏蔽原因
            duration_hours: 屏蔽时长（小时），为空则永久屏蔽

        Returns:
            SuppressionRule: 创建的屏蔽规则
        """
        start_time = datetime.now(timezone.utc)
        end_time = None

        if duration_hours is not None:
            from datetime import timedelta
            end_time = start_time.replace(
                microsecond=0
            ) + timedelta(hours=duration_hours)

        return await self.create_rule(
            resource_type=resource_type,
            resource_id=resource_id,
            created_by=created_by,
            reason=reason,
            start_time=start_time,
            end_time=end_time,
            suppress_alerts=True,
            suppress_notifications=True,
            suppress_ai_analysis=True,
            suppress_log_scan=True
        )

    @staticmethod
    async def get_suppressed_host_ids_for_logs(db: AsyncSession) -> set:
        """获取日志统计/扫描应排除的 host_id 集合

        包含两类：
        1. 直接屏蔽主机（resource_type=host）
        2. 通过服务屏蔽（resource_type=service），取该服务所属的 host_id

        Args:
            db: 异步数据库会话

        Returns:
            set: 应被排除的 host_id 集合
        """
        from app.models.service import Service

        now = datetime.now(timezone.utc)
        time_conditions = [
            SuppressionRule.is_active == True,
            or_(SuppressionRule.start_time == None, SuppressionRule.start_time <= now),
            or_(SuppressionRule.end_time == None, SuppressionRule.end_time >= now),
        ]

        # 1. 直接屏蔽的主机
        host_result = await db.execute(
            select(SuppressionRule.resource_id).where(
                and_(
                    *time_conditions,
                    SuppressionRule.resource_type == SuppressionService.RESOURCE_HOST,
                    SuppressionRule.resource_id != None,
                )
            )
        )
        host_ids = set(row[0] for row in host_result.all())

        # 2. 通过服务屏蔽 -> 查出对应 host_id
        svc_result = await db.execute(
            select(SuppressionRule.resource_id).where(
                and_(
                    *time_conditions,
                    SuppressionRule.resource_type == SuppressionService.RESOURCE_SERVICE,
                    SuppressionRule.resource_id != None,
                )
            )
        )
        suppressed_service_ids = [row[0] for row in svc_result.all()]

        if suppressed_service_ids:
            svc_host_result = await db.execute(
                select(Service.host_id).where(
                    Service.id.in_(suppressed_service_ids),
                    Service.host_id != None,
                )
            )
            host_ids.update(row[0] for row in svc_host_result.all())

        return host_ids
