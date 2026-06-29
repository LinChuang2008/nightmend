"""
数据保留策略 API (Data Retention Policy API)

提供数据保留策略的配置和管理接口，包括：
- 查看/设置各类型数据的保留天数
- 手动触发数据清理
- 查看数据统计和清理历史

Provides configuration and management APIs for data retention policies, including:
- View/set retention days for different data types
- Manually trigger data cleanup
- View data statistics and cleanup history
"""
from datetime import datetime, timedelta
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.setting import Setting
from app.models.host_metric import HostMetric
from app.models.db_metric import DbMetric
from app.models.log_entry import LogEntry
from app.models.ai_insight import AIInsight
from app.models.audit_log import AuditLog

router = APIRouter()


class RetentionSettingsRequest(BaseModel):
    """数据保留设置请求模型"""
    host_metrics: int = Field(ge=1, le=3650, description="主机指标保留天数 (1-3650天)")
    db_metrics: int = Field(ge=1, le=3650, description="数据库指标保留天数 (1-3650天)")
    log_entries: int = Field(ge=1, le=365, description="日志条目保留天数 (1-365天)")
    ai_insights: int = Field(ge=1, le=3650, description="AI洞察保留天数 (1-3650天)")
    audit_logs: int = Field(ge=1, le=3650, description="审计日志保留天数 (1-3650天)")


class RetentionSettingsResponse(BaseModel):
    """数据保留设置响应模型"""
    host_metrics: int
    db_metrics: int
    log_entries: int
    ai_insights: int
    audit_logs: int


class CleanupStatsResponse(BaseModel):
    """数据清理统计响应模型"""
    host_metrics: int = Field(description="清理的主机指标记录数")
    db_metrics: int = Field(description="清理的数据库指标记录数")
    log_entries: int = Field(description="清理的日志条目记录数")
    ai_insights: int = Field(description="清理的AI洞察记录数")
    audit_logs: int = Field(description="清理的审计日志记录数")
    total: int = Field(description="总清理记录数")


class DataStatsResponse(BaseModel):
    """数据统计响应模型"""
    host_metrics: Dict[str, int] = Field(description="主机指标统计")
    db_metrics: Dict[str, int] = Field(description="数据库指标统计")
    log_entries: Dict[str, int] = Field(description="日志条目统计")
    ai_insights: Dict[str, int] = Field(description="AI洞察统计")
    audit_logs: Dict[str, int] = Field(description="审计日志统计")


DEFAULT_RETENTION = {
    "host_metrics": 30, "db_metrics": 30, "log_entries": 7, "ai_insights": 90, "audit_logs": 180
}


async def _get_retention_days(db: AsyncSession, data_type: str) -> int:
    key = f"retention_days_{data_type}"
    result = await db.execute(select(Setting).where(Setting.key == key))
    setting = result.scalar_one_or_none()
    if setting:
        try:
            return int(setting.value)
        except (ValueError, TypeError):
            pass
    return DEFAULT_RETENTION.get(data_type, 30)


async def _set_retention_days(db: AsyncSession, data_type: str, days: int) -> None:
    key = f"retention_days_{data_type}"
    result = await db.execute(select(Setting).where(Setting.key == key))
    setting = result.scalar_one_or_none()
    if setting:
        setting.value = str(days)
    else:
        setting = Setting(key=key, value=str(days), description=f"{data_type} 保留天数")
        db.add(setting)


@router.get("/settings", response_model=RetentionSettingsResponse)
async def get_retention_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取当前数据保留策略设置"""
    try:
        ret = {}
        for dt in DEFAULT_RETENTION:
            ret[dt] = await _get_retention_days(db, dt)
        return RetentionSettingsResponse(**ret)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取保留策略设置失败: {str(e)}")


@router.put("/settings", response_model=RetentionSettingsResponse)
async def update_retention_settings(
    settings_req: RetentionSettingsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """更新数据保留策略设置"""
    try:
        if current_user.role not in ["admin", "super_admin"]:
            raise HTTPException(status_code=403, detail="只有管理员可以修改数据保留策略")
        
        await _set_retention_days(db, "host_metrics", settings_req.host_metrics)
        await _set_retention_days(db, "db_metrics", settings_req.db_metrics)
        await _set_retention_days(db, "log_entries", settings_req.log_entries)
        await _set_retention_days(db, "ai_insights", settings_req.ai_insights)
        await _set_retention_days(db, "audit_logs", settings_req.audit_logs)
        await db.commit()
        
        return RetentionSettingsResponse(
            host_metrics=settings_req.host_metrics,
            db_metrics=settings_req.db_metrics,
            log_entries=settings_req.log_entries,
            ai_insights=settings_req.ai_insights,
            audit_logs=settings_req.audit_logs
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新保留策略设置失败: {str(e)}")


@router.post("/cleanup", response_model=CleanupStatsResponse)
async def trigger_data_cleanup(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """手动触发数据清理"""
    try:
        if current_user.role not in ["admin", "super_admin"]:
            raise HTTPException(status_code=403, detail="只有管理员可以触发数据清理")
        
        cleanup_stats = {}
        model_map = {
            "host_metrics": (HostMetric, HostMetric.recorded_at),
            "db_metrics": (DbMetric, DbMetric.recorded_at),
            "log_entries": (LogEntry, LogEntry.timestamp),
            "ai_insights": (AIInsight, AIInsight.created_at),
            "audit_logs": (AuditLog, AuditLog.created_at),
        }
        
        for data_type, (model, time_col) in model_map.items():
            days = await _get_retention_days(db, data_type)
            cutoff = datetime.utcnow() - timedelta(days=days)
            count_result = await db.execute(
                select(func.count()).select_from(model).where(time_col < cutoff)
            )
            count = count_result.scalar() or 0
            if count > 0:
                await db.execute(delete(model).where(time_col < cutoff))
            cleanup_stats[data_type] = count
        
        await db.commit()
        total = sum(cleanup_stats.values())
        
        return CleanupStatsResponse(
            host_metrics=cleanup_stats.get("host_metrics", 0),
            db_metrics=cleanup_stats.get("db_metrics", 0),
            log_entries=cleanup_stats.get("log_entries", 0),
            ai_insights=cleanup_stats.get("ai_insights", 0),
            audit_logs=cleanup_stats.get("audit_logs", 0),
            total=total
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"数据清理失败: {str(e)}")


@router.get("/statistics", response_model=DataStatsResponse)
async def get_data_statistics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取数据统计信息"""
    try:
        model_map = {
            "host_metrics": (HostMetric, HostMetric.recorded_at),
            "db_metrics": (DbMetric, DbMetric.recorded_at),
            "log_entries": (LogEntry, LogEntry.timestamp),
            "ai_insights": (AIInsight, AIInsight.created_at),
            "audit_logs": (AuditLog, AuditLog.created_at),
        }
        
        stats = {}
        for data_type, (model, time_col) in model_map.items():
            total = (await db.execute(select(func.count()).select_from(model))).scalar() or 0
            days = await _get_retention_days(db, data_type)
            cutoff = datetime.utcnow() - timedelta(days=days)
            expired = (await db.execute(
                select(func.count()).select_from(model).where(time_col < cutoff)
            )).scalar() or 0
            stats[data_type] = {"total": total, "expired": expired, "retention_days": days}
        
        return DataStatsResponse(**stats)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取数据统计失败: {str(e)}")


# 健康检查接口
@router.get("/health")
def health_check():
    """数据保留策略服务健康检查"""
    return {"status": "healthy", "service": "data_retention"}