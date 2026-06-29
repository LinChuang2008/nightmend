"""
告警去重和聚合清理任务 (Alert Deduplication and Aggregation Cleanup Task)

定期清理过期的去重记录和聚合组，防止数据无限增长。
每小时执行一次，清理过期的记录和统计。

Periodic cleanup task for expired deduplication records and aggregation groups
to prevent unlimited data growth. Runs every hour to clean up expired records and statistics.
"""
import asyncio
import logging
from datetime import datetime

from app.core.database import SessionLocal
from app.services.alert_deduplication import AlertDeduplicationService

logger = logging.getLogger(__name__)

# 清理间隔（秒）- 每小时执行一次
CLEANUP_INTERVAL = 3600


async def alert_deduplication_cleanup_loop():
    """
    告警去重和聚合清理主循环
    
    每小时执行一次清理任务，清理过期的去重记录和聚合组。
    """
    logger.info("Alert deduplication cleanup task started")
    
    while True:
        try:
            # 等待到下次清理时间
            await asyncio.sleep(CLEANUP_INTERVAL)
            
            # 执行清理
            await _perform_cleanup()
            
        except asyncio.CancelledError:
            logger.info("Alert deduplication cleanup task cancelled")
            break
        except Exception as e:
            logger.error(f"Alert deduplication cleanup error: {e}", exc_info=True)
            # 发生错误后等待 10 分钟再重试
            await asyncio.sleep(600)
    
    logger.info("Alert deduplication cleanup task stopped")


async def _perform_cleanup():
    """执行清理操作"""
    logger.info("Starting alert deduplication cleanup")
    
    start_time = datetime.now()
    
    try:
        # 使用同步 Session，因为 AlertDeduplicationService 使用同步 ORM API
        db = SessionLocal()
        try:
            service = AlertDeduplicationService(db)
            cleanup_stats = service.cleanup_expired_records()
            db.commit()
        finally:
            db.close()
        
        # 记录清理结果
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        logger.info(
            f"Alert deduplication cleanup completed successfully. "
            f"Duration: {duration:.2f}s, "
            f"Cleaned up {cleanup_stats.get('expired_dedup_records', 0)} dedup records, "
            f"{cleanup_stats.get('expired_alert_groups', 0)} alert groups"
        )
        
    except Exception as e:
        logger.error(f"Alert deduplication cleanup failed: {e}", exc_info=True)
        raise


# 立即执行清理的辅助函数（用于手动触发）
async def execute_immediate_deduplication_cleanup() -> dict:
    """
    立即执行告警去重清理（手动触发）
    
    Returns:
        dict: 清理统计结果
    """
    logger.info("Starting immediate alert deduplication cleanup")
    
    try:
        db = SessionLocal()
        try:
            service = AlertDeduplicationService(db)
            cleanup_stats = service.cleanup_expired_records()
            db.commit()
        finally:
            db.close()
        
        logger.info(f"Immediate alert deduplication cleanup completed: {cleanup_stats}")
        return cleanup_stats
        
    except Exception as e:
        logger.error(f"Immediate alert deduplication cleanup failed: {e}", exc_info=True)
        raise


def is_deduplication_cleanup_running() -> bool:
    """检查告警去重清理任务是否正在运行"""
    # 这个函数可以通过全局状态变量来实现，暂时返回 True
    return True