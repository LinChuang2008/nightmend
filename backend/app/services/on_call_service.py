"""
值班排期服务 (On-Call Schedule Service)

提供值班排期的核心业务逻辑，包括值班人员查找、排期冲突检测、通知路由等功能。
与告警系统集成，实现基于值班排期的智能通知分发。

Provides core business logic for on-call schedules, including on-call personnel lookup,
schedule conflict detection, and notification routing.
"""
from datetime import date, datetime
from typing import Optional, List

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.on_call import OnCallGroup, OnCallSchedule
from app.models.user import User


class OnCallService:
    """值班排期业务服务类 (On-Call Schedule Business Service)"""

    @staticmethod
    async def get_current_on_call_user(db: AsyncSession, group_id: Optional[int] = None) -> Optional[dict]:
        """
        获取当前值班人员 (Get Current On-Call User)
        
        查找指定值班组或所有值班组中当前正在值班的人员信息。
        
        Args:
            db: 数据库会话
            group_id: 值班组ID，None表示查找所有组
        Returns:
            dict: 当前值班人员信息，包含用户和组信息
        """
        today = date.today()
        
        query = select(
            OnCallSchedule,
            OnCallGroup.name.label('group_name'),
            User.email
        ).select_from(
            OnCallSchedule
        ).join(
            OnCallGroup, OnCallSchedule.group_id == OnCallGroup.id
        ).join(
            User, OnCallSchedule.user_id == User.id
        ).where(
            and_(
                OnCallSchedule.start_date <= today,
                OnCallSchedule.end_date >= today,
                OnCallSchedule.is_active == True,
                OnCallGroup.is_active == True
            )
        )
        
        if group_id:
            query = query.where(OnCallSchedule.group_id == group_id)
            
        query = query.order_by(OnCallSchedule.start_date.desc())
        result = await db.execute(query)
        row = result.first()
        
        if row:
            schedule, group_name, email = row
            return {
                "user_id": schedule.user_id,
                "email": email,
                "group_id": schedule.group_id,
                "group_name": group_name,
                "schedule_id": schedule.id,
                "start_date": schedule.start_date,
                "end_date": schedule.end_date
            }
        return None

    @staticmethod
    async def get_on_call_users_for_alert(db: AsyncSession, severity: str) -> List[dict]:
        """
        获取告警对应的值班人员 (Get On-Call Users for Alert)
        
        根据告警严重程度确定需要通知的值班人员列表。
        
        Args:
            db: 数据库会话
            severity: 告警严重程度
        Returns:
            List[dict]: 值班人员列表
        """
        # 根据严重程度确定需要通知的值班组
        group_filter = None
        if severity in ['critical', 'high']:
            # 高严重程度通知所有值班组
            group_filter = None
        else:
            # 低严重程度只通知主要值班组（ID=1）
            group_filter = 1
            
        current_user = await OnCallService.get_current_on_call_user(db, group_filter)
        return [current_user] if current_user else []

    @staticmethod
    async def check_schedule_conflicts(
        db: AsyncSession, 
        user_id: int, 
        start_date: date, 
        end_date: date,
        exclude_schedule_id: Optional[int] = None
    ) -> List[OnCallSchedule]:
        """
        检查值班排期冲突 (Check Schedule Conflicts)
        
        检查指定用户在给定时间段内是否已有其他值班安排。
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            start_date: 开始日期
            end_date: 结束日期
            exclude_schedule_id: 排除的排期ID（用于更新时检查）
        Returns:
            List[OnCallSchedule]: 冲突的排期列表
        """
        query = select(OnCallSchedule).where(
            and_(
                OnCallSchedule.user_id == user_id,
                OnCallSchedule.is_active == True,
                # 时间段重叠检查：新排期与现有排期有交集
                or_(
                    and_(OnCallSchedule.start_date <= start_date, OnCallSchedule.end_date >= start_date),
                    and_(OnCallSchedule.start_date <= end_date, OnCallSchedule.end_date >= end_date),
                    and_(OnCallSchedule.start_date >= start_date, OnCallSchedule.end_date <= end_date)
                )
            )
        )
        
        if exclude_schedule_id:
            query = query.where(OnCallSchedule.id != exclude_schedule_id)
            
        result = await db.execute(query)
        return result.scalars().all()

    @staticmethod
    async def get_schedule_coverage(db: AsyncSession, start_date: date, end_date: date) -> dict:
        """
        获取指定时间段的值班覆盖情况 (Get Schedule Coverage)
        
        分析指定时间段内的值班安排，找出覆盖空档。
        
        Args:
            db: 数据库会话
            start_date: 开始日期
            end_date: 结束日期
        Returns:
            dict: 覆盖情况统计
        """
        query = select(OnCallSchedule, OnCallGroup.name, User.email).select_from(
            OnCallSchedule
        ).join(
            OnCallGroup, OnCallSchedule.group_id == OnCallGroup.id
        ).join(
            User, OnCallSchedule.user_id == User.id
        ).where(
            and_(
                OnCallSchedule.is_active == True,
                OnCallGroup.is_active == True,
                # 排期与查询时间段有交集
                or_(
                    and_(OnCallSchedule.start_date <= start_date, OnCallSchedule.end_date >= start_date),
                    and_(OnCallSchedule.start_date <= end_date, OnCallSchedule.end_date >= end_date),
                    and_(OnCallSchedule.start_date >= start_date, OnCallSchedule.end_date <= end_date)
                )
            )
        ).order_by(OnCallSchedule.start_date)
        
        result = await db.execute(query)
        schedules = []
        
        for schedule, group_name, email in result:
            schedules.append({
                "schedule_id": schedule.id,
                "user_id": schedule.user_id,
                "email": email,
                "group_id": schedule.group_id,
                "group_name": group_name,
                "start_date": schedule.start_date,
                "end_date": schedule.end_date
            })
        
        return {
            "total_schedules": len(schedules),
            "schedules": schedules,
            "coverage_analysis": OnCallService._analyze_coverage_gaps(schedules, start_date, end_date)
        }

    @staticmethod
    def _analyze_coverage_gaps(schedules: List[dict], start_date: date, end_date: date) -> dict:
        """
        分析值班覆盖空档 (Analyze Coverage Gaps)
        
        内部方法，用于分析值班排期的覆盖空档。
        
        Args:
            schedules: 值班排期列表
            start_date: 分析开始日期
            end_date: 分析结束日期
        Returns:
            dict: 覆盖空档分析结果
        """
        # 简单实现：检查是否有完全无人值班的日期
        covered_dates = set()
        for schedule in schedules:
            current_date = max(schedule["start_date"], start_date)
            end_coverage = min(schedule["end_date"], end_date)
            
            while current_date <= end_coverage:
                covered_dates.add(current_date)
                current_date = date.fromordinal(current_date.toordinal() + 1)
        
        total_days = (end_date - start_date).days + 1
        coverage_rate = len(covered_dates) / total_days if total_days > 0 else 0
        
        return {
            "coverage_rate": coverage_rate,
            "covered_days": len(covered_dates),
            "total_days": total_days,
            "has_gaps": coverage_rate < 1.0
        }