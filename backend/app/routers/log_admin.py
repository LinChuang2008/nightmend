"""
日志管理 API (Log Administration API)

提供日志后端管理、数据迁移、健康检查等管理功能。
仅限管理员访问，用于系统维护和故障排除。

功能：
1. 后端健康检查
2. 数据迁移工具
3. 手动清理日志
4. 配置管理
"""

from datetime import datetime, timezone
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_admin
from app.core.config import settings
from app.models.user import User
from app.services.log_service import get_log_service
from app.tasks.log_cleanup import manual_cleanup

router = APIRouter(prefix="/api/v1/admin/logs", tags=["log-admin"])


@router.get("/health")
async def log_backend_health(
    _user: User = Depends(require_admin),  # 仅管理员可访问
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    检查日志后端健康状态
    
    返回所有配置的日志后端的健康状态，包括连接性、性能指标等。
    用于监控和故障排除。
    
    Returns:
        Dict: 健康检查结果
    """
    log_service = await get_log_service(db)
    health = await log_service.health_check()
    
    # 添加配置信息
    health["config"] = {
        "backend_type": settings.log_backend_type,
        "retention_days": settings.log_retention_days,
        "clickhouse_url": settings.clickhouse_url if hasattr(settings, 'clickhouse_url') else None,
        "loki_url": settings.loki_url if hasattr(settings, 'loki_url') else None,
    }
    
    return health


@router.post("/migrate")
async def migrate_logs(
    source: str = Query(..., description="源后端类型: postgresql/clickhouse/loki"),
    target: Optional[str] = Query(None, description="目标后端类型，默认为当前配置"),
    batch_size: int = Query(1000, ge=100, le=10000, description="批处理大小"),
    _user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    数据迁移工具
    
    将日志数据从一个后端迁移到另一个后端。常用于：
    - PostgreSQL → ClickHouse 性能升级
    - ClickHouse → PostgreSQL 兼容性回退
    - 数据备份和恢复
    
    Args:
        source: 源后端类型
        target: 目标后端类型，默认为当前配置
        batch_size: 每批处理的记录数，影响内存使用和性能
        
    Returns:
        Dict: 迁移统计信息
    """
    valid_backends = ["postgresql", "clickhouse", "loki"]
    if source not in valid_backends:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid source backend: {source}. Valid options: {valid_backends}"
        )
        
    if target and target not in valid_backends:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid target backend: {target}. Valid options: {valid_backends}"
        )
    
    log_service = await get_log_service(db)
    
    try:
        result = await log_service.migrate_data(
            source=source,
            target=target,
            batch_size=batch_size
        )
        
        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])
            
        return {
            "success": True,
            "migration_stats": result,
            "timestamp": datetime.now(timezone.utc)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Migration failed: {str(e)}")


@router.post("/cleanup")
async def cleanup_logs(
    retention_days: Optional[int] = Query(None, ge=1, le=365, description="保留天数，默认使用配置值"),
    _user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    手动清理日志
    
    立即执行日志清理，删除超过保留期的日志条目。
    通常用于紧急清理磁盘空间或测试清理逻辑。
    
    Args:
        retention_days: 保留天数，为空时使用全局配置
        
    Returns:
        Dict: 清理结果统计
    """
    try:
        result = await manual_cleanup(retention_days)
        
        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])
            
        return {
            "success": True,
            "cleanup_stats": result
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cleanup failed: {str(e)}")


@router.get("/config")
async def get_log_config(
    _user: User = Depends(require_admin),
) -> Dict[str, Any]:
    """
    获取日志配置信息
    
    返回当前的日志系统配置，用于管理和调试。
    不包含敏感信息如密码等。
    
    Returns:
        Dict: 配置信息
    """
    return {
        "backend_type": settings.log_backend_type,
        "retention_days": settings.log_retention_days,
        "clickhouse": {
            "host": settings.clickhouse_host,
            "port": settings.clickhouse_port,
            "user": settings.clickhouse_user,
            "database": settings.clickhouse_database,
            "url": settings.clickhouse_url,
        },
        "loki": {
            "url": settings.loki_url,
            "username": settings.loki_username,
        },
        "postgresql": {
            "host": settings.postgres_host,
            "port": settings.postgres_port,
            "database": settings.postgres_db,
            "user": settings.postgres_user,
        }
    }


@router.get("/stats")
async def get_backend_stats(
    backend: Optional[str] = Query(None, description="后端类型，默认为主要后端"),
    _user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    获取日志后端统计信息
    
    返回各后端的存储统计、性能指标等信息。
    用于容量规划和性能监控。
    
    Args:
        backend: 指定后端类型，为空时返回所有后端的统计
        
    Returns:
        Dict: 统计信息
    """
    log_service = await get_log_service(db)
    
    # 获取基本统计信息
    stats = await log_service.get_stats()
    
    # 添加配置信息
    stats["config"] = {
        "current_backend": settings.log_backend_type,
        "retention_days": settings.log_retention_days,
    }
    
    # 添加健康状态
    health = await log_service.health_check()
    stats["health"] = health
    
    return stats


@router.post("/test-store")
async def test_store_logs(
    count: int = Query(10, ge=1, le=1000, description="测试日志条数"),
    _user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    测试日志存储
    
    生成测试日志并存储到当前后端，用于验证存储功能和性能。
    
    Args:
        count: 生成的测试日志条数
        
    Returns:
        Dict: 存储测试结果
    """
    from datetime import timezone
    import time
    
    log_service = await get_log_service(db)
    
    # 生成测试日志
    test_logs = []
    base_time = datetime.now(timezone.utc)
    
    for i in range(count):
        test_log = {
            "host_id": 1,  # 假设存在host_id=1
            "service": "test-service",
            "source": "/var/log/test.log",
            "level": "INFO" if i % 3 == 0 else ("WARN" if i % 3 == 1 else "ERROR"),
            "message": f"Test log message {i+1} - timestamp {base_time}",
            "timestamp": base_time,
        }
        test_logs.append(test_log)
    
    # 测试存储性能
    start_time = time.time()
    
    try:
        success = await log_service.store_logs(test_logs, broadcast=False)
        
        end_time = time.time()
        duration = end_time - start_time
        
        if success:
            return {
                "success": True,
                "test_logs_count": count,
                "storage_duration_seconds": duration,
                "logs_per_second": count / duration if duration > 0 else 0,
                "backend_type": settings.log_backend_type,
                "timestamp": datetime.now(timezone.utc)
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to store test logs")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Test storage failed: {str(e)}")


@router.get("/performance")
async def get_performance_metrics(
    hours: int = Query(24, ge=1, le=168, description="统计时间范围（小时）"),
    _user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    获取日志系统性能指标
    
    返回指定时间范围内的日志系统性能统计。
    
    Args:
        hours: 统计时间范围（小时）
        
    Returns:
        Dict: 性能指标
    """
    from datetime import timedelta
    
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=hours)
    
    try:
        log_service = await get_log_service(db)
        
        # 获取时间范围内的统计
        stats = await log_service.get_stats(
            start_time=start_time,
            end_time=end_time,
            period="1h"
        )
    except Exception:
        stats = {"by_time": [], "by_level": []}
    
    # 计算性能指标
    total_logs = sum(item.get("count", 0) for item in stats.get("by_time", []))
    avg_logs_per_hour = total_logs / hours if hours > 0 else 0
    
    # 获取错误率
    by_level = stats.get("by_level", [])
    total_by_level = sum(item.get("count", 0) for item in by_level)
    error_count = sum(item.get("count", 0) for item in by_level 
                     if item.get("level", "").upper() in ["ERROR", "FATAL", "CRITICAL"])
    error_rate = error_count / total_by_level if total_by_level > 0 else 0
    
    return {
        "time_range": {
            "start_time": start_time,
            "end_time": end_time,
            "hours": hours
        },
        "performance_metrics": {
            "total_logs": total_logs,
            "avg_logs_per_hour": avg_logs_per_hour,
            "peak_hour_logs": max((item.get("count", 0) for item in stats.get("by_time", [])), default=0),
            "error_rate": error_rate,
            "error_count": error_count
        },
        "backend_type": settings.log_backend_type,
        "raw_stats": stats
    }