"""
数据保留策略定时任务 (Data Retention Policy Scheduled Task)

每日定时执行数据清理，根据配置的保留天数自动清理过期数据。
支持优雅停机、错误恢复和统计日志记录。

Daily scheduled task to clean up data based on configured retention days.
Supports graceful shutdown, error recovery, and statistics logging.
"""
import asyncio
import logging
from datetime import datetime, time
from typing import Optional


from app.core.database import async_session
from app.services.data_retention import DataRetentionService

logger = logging.getLogger(__name__)

# 全局任务控制标志
_cleanup_task_running = False
_cleanup_task_stop_event: Optional[asyncio.Event] = None


async def data_retention_task():
    """
    数据保留策略后台任务
    
    每日凌晨 2:00 执行数据清理，清理过期的监控数据。
    在清理过程中会分批次处理，避免长时间占用数据库资源。
    """
    global _cleanup_task_running, _cleanup_task_stop_event
    
    _cleanup_task_running = True
    _cleanup_task_stop_event = asyncio.Event()
    
    logger.info("Data retention task started")
    
    while not _cleanup_task_stop_event.is_set():
        try:
            # 等待到每日凌晨 2:00 或停止事件
            await _wait_for_cleanup_time()
            
            if _cleanup_task_stop_event.is_set():
                break
                
            # 执行数据清理
            await _execute_data_cleanup()
            
        except asyncio.CancelledError:
            logger.info("Data retention task cancelled")
            break
        except Exception as e:
            logger.error(f"Data retention task error: {e}", exc_info=True)
            # 发生错误后等待 1 小时再重试
            try:
                await asyncio.wait_for(_cleanup_task_stop_event.wait(), timeout=3600)
            except asyncio.TimeoutError:
                pass
    
    _cleanup_task_running = False
    logger.info("Data retention task stopped")


async def _wait_for_cleanup_time():
    """等待到清理时间（每日凌晨 2:00）"""
    now = datetime.now()
    
    # 计算下一次凌晨 2:00 的时间
    cleanup_time = datetime.combine(now.date(), time(2, 0))  # 凌晨 2:00
    
    # 如果已经过了今天的 2:00，则计算明天的 2:00
    if now > cleanup_time:
        from datetime import timedelta
        cleanup_time += timedelta(days=1)
    
    # 计算等待时间（秒）
    wait_seconds = (cleanup_time - now).total_seconds()
    
    logger.info(f"Next data cleanup scheduled at {cleanup_time} (in {wait_seconds:.0f} seconds)")
    
    # 等待到清理时间或接收到停止信号
    try:
        await asyncio.wait_for(_cleanup_task_stop_event.wait(), timeout=wait_seconds)
    except asyncio.TimeoutError:
        pass  # 时间到达，正常进行清理


async def _execute_data_cleanup():
    """执行数据清理操作"""
    logger.info("Starting scheduled data cleanup")
    
    start_time = datetime.now()
    
    try:
        # 获取异步数据库会话
        async with async_session() as db:
            # 创建数据保留服务实例
            service = DataRetentionService(db)
            
            # 执行数据清理
            cleanup_stats = service.cleanup_expired_data()
            
            # 记录清理结果
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            total_cleaned = sum(cleanup_stats.values())
            
            logger.info(
                f"Data cleanup completed successfully. "
                f"Duration: {duration:.2f}s, Total records cleaned: {total_cleaned}, "
                f"Details: {cleanup_stats}"
            )
        
    except Exception as e:
        logger.error(f"Data cleanup failed: {e}", exc_info=True)
        raise


async def stop_data_retention_task():
    """
    停止数据保留策略任务
    
    优雅地停止后台清理任务，等待当前清理操作完成。
    """
    global _cleanup_task_stop_event
    
    if _cleanup_task_stop_event and not _cleanup_task_stop_event.is_set():
        logger.info("Stopping data retention task...")
        _cleanup_task_stop_event.set()
        
        # 等待任务实际停止，最多等待 30 秒
        max_wait = 30
        waited = 0
        while _cleanup_task_running and waited < max_wait:
            await asyncio.sleep(1)
            waited += 1
        
        if _cleanup_task_running:
            logger.warning(f"Data retention task did not stop within {max_wait} seconds")
        else:
            logger.info("Data retention task stopped successfully")


def is_data_retention_task_running() -> bool:
    """检查数据保留策略任务是否正在运行"""
    return _cleanup_task_running


# 立即执行数据清理的辅助函数（用于手动触发）
async def execute_immediate_cleanup() -> dict:
    """
    立即执行数据清理（手动触发）
    
    Returns:
        dict: 清理统计结果
    """
    logger.info("Starting immediate data cleanup")
    
    try:
        async with async_session() as db:
            service = DataRetentionService(db)
            cleanup_stats = service.cleanup_expired_data()
            
            logger.info(f"Immediate data cleanup completed: {cleanup_stats}")
            return cleanup_stats
        
    except Exception as e:
        logger.error(f"Immediate data cleanup failed: {e}", exc_info=True)
        raise