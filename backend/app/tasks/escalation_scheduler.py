"""
告警升级调度任务 (Alert Escalation Scheduler Task)

定时执行告警升级扫描的后台任务，定期检查需要升级的告警并自动执行升级操作。
与现有的任务调度系统集成，保证升级引擎的持续运行。

Scheduled task for alert escalation scanning, periodically checks alerts
that need escalation and automatically executes escalation operations.
"""
import asyncio
import logging
from datetime import datetime, timezone


from app.core.database import async_session as get_async_session
from app.services.escalation_engine import EscalationEngine

logger = logging.getLogger(__name__)


async def run_escalation_scan():
    """
    执行告警升级扫描 (Execute Alert Escalation Scan)
    
    定时任务的主要执行函数，扫描并处理需要升级的告警。
    设计为每分钟执行一次，确保告警能够及时升级。
    
    该函数会：
    1. 获取数据库会话
    2. 调用升级引擎执行扫描
    3. 记录执行结果和异常情况
    4. 确保资源正确释放
    """
    logger.info("开始执行告警升级扫描任务")
    start_time = datetime.now(timezone.utc)
    
    async with get_async_session() as db:
        try:
            # 执行升级扫描
            scan_result = await EscalationEngine.scan_and_escalate_alerts(db)
            
            # 计算执行时间
            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            
            # 记录执行结果
            logger.info(
                f"告警升级扫描完成 - 扫描告警数: {scan_result['scanned_alerts']}, "
                f"升级成功数: {scan_result['escalated_count']}, "
                f"升级失败数: {scan_result['failed_count']}, "
                f"执行时间: {execution_time:.2f}秒"
            )
            
            # 如果有升级操作或失败，记录详细信息
            if scan_result['escalated_count'] > 0:
                logger.info(f"成功升级 {scan_result['escalated_count']} 个告警")
            
            if scan_result['failed_count'] > 0:
                logger.warning(f"升级失败 {scan_result['failed_count']} 个告警，请检查日志")
                
        except Exception as e:
            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            logger.error(f"告警升级扫描任务执行失败: {str(e)}, 执行时间: {execution_time:.2f}秒")
            raise


async def escalation_scheduler_main():
    """
    升级调度器主循环 (Escalation Scheduler Main Loop)
    
    可选的独立调度器进程，用于在需要时独立运行升级任务。
    通常情况下，升级任务会通过系统的定时任务调度器（如 cron 或 APScheduler）来执行。
    
    这个函数提供了一个简单的循环调度实现，每 60 秒执行一次扫描。
    """
    logger.info("启动告警升级调度器")
    
    while True:
        try:
            await run_escalation_scan()
            
            # 等待60秒后执行下一次扫描
            await asyncio.sleep(60)
            
        except KeyboardInterrupt:
            logger.info("收到中断信号，停止升级调度器")
            break
        except Exception as e:
            logger.error(f"升级调度器发生未处理的异常: {str(e)}")
            # 出现异常时等待 30 秒后重试，避免快速失败循环
            await asyncio.sleep(30)


if __name__ == "__main__":
    """
    独立运行升级调度器 (Run Escalation Scheduler Standalone)
    
    允许将升级调度器作为独立进程运行：
    python -m app.tasks.escalation_scheduler
    """
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # 启动调度器
    try:
        asyncio.run(escalation_scheduler_main())
    except KeyboardInterrupt:
        logger.info("升级调度器已停止")