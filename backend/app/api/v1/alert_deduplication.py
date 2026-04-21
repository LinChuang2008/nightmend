"""
告警去重和聚合 API (Alert Deduplication and Aggregation API)

提供告警去重和聚合的配置管理和统计查看接口，包括：
- 查看/设置去重和聚合配置参数
- 查看去重和聚合统计信息
- 管理告警聚合组
- 清理过期记录

Provides configuration management and statistics APIs for alert deduplication and aggregation.
"""
from datetime import datetime, timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.alert_group import AlertGroup, AlertDeduplication
from app.models.setting import Setting

router = APIRouter()


class DeduplicationConfigRequest(BaseModel):
    """去重配置请求模型"""
    deduplication_window_seconds: int = Field(ge=60, le=3600, description="去重时间窗口（秒，60-3600）")
    aggregation_window_seconds: int = Field(ge=300, le=7200, description="聚合时间窗口（秒，300-7200）")
    max_alerts_per_group: int = Field(ge=5, le=200, description="每个聚合组最大告警数（5-200）")


class DeduplicationConfigResponse(BaseModel):
    """去重配置响应模型"""
    deduplication_window_seconds: int
    aggregation_window_seconds: int
    max_alerts_per_group: int


class DeduplicationStatsResponse(BaseModel):
    """去重统计响应模型"""
    active_dedup_records: int = Field(description="活跃去重记录数")
    active_alert_groups: int = Field(description="活跃告警组数")
    deduplication_rate_24h: float = Field(description="24小时去重率（%）")
    suppressed_alerts_24h: int = Field(description="24小时抑制告警数")
    total_alert_occurrences_24h: int = Field(description="24小时总告警次数")


class AlertGroupSummary(BaseModel):
    """告警组摘要模型"""
    id: int
    title: str
    severity: str
    status: str
    alert_count: int
    rule_count: int = Field(description="涉及规则数")
    host_count: int = Field(description="涉及主机数")
    service_count: int = Field(description="涉及服务数")
    last_occurrence: str
    window_end: str


class AlertGroupListResponse(BaseModel):
    """告警组列表响应模型"""
    groups: List[AlertGroupSummary]
    total: int


async def _get_setting(db: AsyncSession, key: str, default: int) -> int:
    """异步获取配置值"""
    result = await db.execute(select(Setting).where(Setting.key == key))
    setting = result.scalar_one_or_none()
    if setting:
        try:
            return int(setting.value)
        except (ValueError, TypeError):
            pass
    return default


async def _set_setting(db: AsyncSession, key: str, value: int, description: str) -> None:
    """异步设置配置值"""
    result = await db.execute(select(Setting).where(Setting.key == key))
    setting = result.scalar_one_or_none()
    if setting:
        setting.value = str(value)
    else:
        setting = Setting(key=key, value=str(value), description=description)
        db.add(setting)
    await db.commit()


@router.get("/config", response_model=DeduplicationConfigResponse)
async def get_deduplication_config(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取告警去重和聚合配置"""
    try:
        config = {
            "deduplication_window_seconds": await _get_setting(db, "alert_deduplication_window_seconds", 300),
            "aggregation_window_seconds": await _get_setting(db, "alert_aggregation_window_seconds", 600),
            "max_alerts_per_group": await _get_setting(db, "alert_max_alerts_per_group", 50)
        }
        return DeduplicationConfigResponse(**config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取去重配置失败: {str(e)}")


@router.put("/config", response_model=DeduplicationConfigResponse)
async def update_deduplication_config(
    config: DeduplicationConfigRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """更新告警去重和聚合配置"""
    try:
        if current_user.role not in ["admin", "super_admin"]:
            raise HTTPException(status_code=403, detail="只有管理员可以修改告警去重配置")
        
        await _set_setting(db, "alert_deduplication_window_seconds", config.deduplication_window_seconds, "告警去重时间窗口（秒）")
        await _set_setting(db, "alert_aggregation_window_seconds", config.aggregation_window_seconds, "告警聚合时间窗口（秒）")
        await _set_setting(db, "alert_max_alerts_per_group", config.max_alerts_per_group, "每个聚合组最大告警数")
        
        return DeduplicationConfigResponse(
            deduplication_window_seconds=config.deduplication_window_seconds,
            aggregation_window_seconds=config.aggregation_window_seconds,
            max_alerts_per_group=config.max_alerts_per_group
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新去重配置失败: {str(e)}")


@router.get("/statistics", response_model=DeduplicationStatsResponse)
async def get_deduplication_statistics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取告警去重和聚合统计信息"""
    try:
        yesterday = datetime.utcnow() - timedelta(hours=24)
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)

        active_dedup_count = (await db.execute(
            select(func.count(AlertDeduplication.id)).where(AlertDeduplication.last_check_time > one_hour_ago)
        )).scalar() or 0

        active_group_count = (await db.execute(
            select(func.count(AlertGroup.id)).where(AlertGroup.status.in_(["firing", "acknowledged"]))
        )).scalar() or 0

        # Get total occurrences (sum of all occurrence_count) and suppressed count
        dedup_result = await db.execute(
            select(AlertDeduplication.occurrence_count).where(AlertDeduplication.last_check_time > yesterday)
        )
        rows = [row[0] for row in dedup_result]
        total_occurrences = sum(rows)
        suppressed_occurrences = sum(max(0, count - 1) for count in rows)

        dedup_rate = (suppressed_occurrences / total_occurrences * 100) if total_occurrences > 0 else 0

        return DeduplicationStatsResponse(
            active_dedup_records=active_dedup_count,
            active_alert_groups=active_group_count,
            deduplication_rate_24h=round(dedup_rate, 2),
            suppressed_alerts_24h=suppressed_occurrences,
            total_alert_occurrences_24h=total_occurrences
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取去重统计失败: {str(e)}")


@router.get("/groups", response_model=AlertGroupListResponse)
async def list_alert_groups(
    status: str = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取告警聚合组列表"""
    try:
        query = select(AlertGroup)
        count_query = select(func.count(AlertGroup.id))

        if status:
            query = query.where(AlertGroup.status == status)
            count_query = count_query.where(AlertGroup.status == status)

        query = query.order_by(AlertGroup.last_occurrence.desc()).offset(offset).limit(limit)

        total = (await db.execute(count_query)).scalar() or 0
        result = await db.execute(query)
        groups = result.scalars().all()

        group_summaries = []
        for group in groups:
            summary = AlertGroupSummary(
                id=group.id,
                title=group.title,
                severity=group.severity,
                status=group.status,
                alert_count=group.alert_count,
                rule_count=len(group.rule_ids or []),
                host_count=len(group.host_ids or []),
                service_count=len(group.service_ids or []),
                last_occurrence=group.last_occurrence.isoformat(),
                window_end=group.window_end.isoformat()
            )
            group_summaries.append(summary)

        return AlertGroupListResponse(groups=group_summaries, total=total)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取告警组列表失败: {str(e)}")


@router.post("/cleanup")
async def cleanup_expired_records(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """清理过期的去重和聚合记录"""
    try:
        if current_user.role not in ["admin", "super_admin"]:
            raise HTTPException(status_code=403, detail="只有管理员可以清理过期记录")
        
        # Cleanup expired dedup records (older than 24h)
        cutoff = datetime.utcnow() - timedelta(hours=24)
        expired_dedup = await db.execute(
            select(AlertDeduplication).where(AlertDeduplication.last_check_time < cutoff)
        )
        dedup_count = 0
        for record in expired_dedup.scalars().all():
            await db.delete(record)
            dedup_count += 1
        
        # Cleanup resolved groups older than 7 days
        group_cutoff = datetime.utcnow() - timedelta(days=7)
        expired_groups = await db.execute(
            select(AlertGroup).where(AlertGroup.status == "resolved", AlertGroup.last_occurrence < group_cutoff)
        )
        group_count = 0
        for group in expired_groups.scalars().all():
            await db.delete(group)
            group_count += 1
        
        await db.commit()
        
        return {
            "success": True,
            "message": "过期记录清理完成",
            "statistics": {"dedup_records_cleaned": dedup_count, "groups_cleaned": group_count}
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"清理过期记录失败: {str(e)}")


@router.patch("/groups/{group_id}/status")
async def update_alert_group_status(
    group_id: int,
    status: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """更新告警组状态"""
    try:
        if status not in ["firing", "resolved", "acknowledged"]:
            raise HTTPException(status_code=400, detail="无效的状态值")
        
        result = await db.execute(select(AlertGroup).where(AlertGroup.id == group_id))
        group = result.scalar_one_or_none()
        if not group:
            raise HTTPException(status_code=404, detail="告警组不存在")
        
        group.status = status
        await db.commit()
        
        return {
            "success": True,
            "message": f"告警组状态已更新为 {status}",
            "group_id": group_id
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新告警组状态失败: {str(e)}")


# 健康检查接口
@router.get("/health")
def health_check():
    """告警去重服务健康检查"""
    return {"status": "healthy", "service": "alert_deduplication"}