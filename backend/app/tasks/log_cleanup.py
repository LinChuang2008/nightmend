"""
日志清理任务模块。

定期删除超过保留期限的日志条目，防止日志数据无限增长。
默认保留 7 天，可通过环境变量 LOG_RETENTION_DAYS 配置。
支持多种日志后端的统一清理。
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from app.core.database import async_session
from app.core.config import settings
from app.services.log_service import get_log_service

logger = logging.getLogger(__name__)


async def log_cleanup_loop(retention_days: Optional[int] = None):
    """
    日志清理后台循环，每小时执行一次过期日志删除。
    
    支持所有配置的日志后端的统一清理。
    
    Args:
        retention_days: 日志保留天数，为None时使用配置值
    """
    if retention_days is None:
        retention_days = settings.log_retention_days
        
    logger.info(f"Starting log cleanup loop with {retention_days} days retention")
    
    while True:
        try:
            async with async_session() as db:
                # 使用统一的日志服务进行清理
                log_service = await get_log_service(db)
                deleted = await log_service.cleanup_logs(retention_days)
                
                if deleted > 0:
                    logger.info(f"Log cleanup: deleted {deleted} entries older than {retention_days} days")
                else:
                    logger.debug(f"Log cleanup: no entries older than {retention_days} days found")
                    
        except Exception as e:
            logger.exception(f"Log cleanup error: {e}")
            
        # 每小时执行一次
        await asyncio.sleep(3600)


async def manual_cleanup(retention_days: Optional[int] = None) -> Dict[str, Any]:
    """
    手动执行日志清理
    
    Args:
        retention_days: 日志保留天数，为None时使用配置值
        
    Returns:
        Dict: 清理结果统计
    """
    if retention_days is None:
        retention_days = settings.log_retention_days
        
    try:
        async with async_session() as db:
            log_service = await get_log_service(db)
            deleted = await log_service.cleanup_logs(retention_days)
            
            # 获取后端健康状态
            health = await log_service.health_check()
            
            return {
                "deleted_count": deleted,
                "retention_days": retention_days,
                "timestamp": datetime.now(timezone.utc),
                "backend_health": health
            }
            
    except Exception as e:
        logger.exception(f"Manual cleanup failed: {e}")
        return {
            "error": str(e),
            "timestamp": datetime.now(timezone.utc)
        }
