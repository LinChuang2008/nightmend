"""
AI异常扫描服务 (AI Anomaly Scanning Service)

功能描述 (Description):
    VigilOps 智能异常检测服务，实现主动式运维监控。
    定期自动扫描系统日志，识别潜在问题，提前预警异常情况。
    
核心功能 (Core Features):
    1. 定时日志扫描 (Scheduled Log Scanning) - 按配置间隔扫描WARN/ERROR级别日志
    2. AI驱动分析 (AI-driven Analysis) - 调用AI引擎进行日志异常模式识别
    3. 洞察记录保存 (Insight Recording) - 将分析结果结构化存储
    4. 自动运维预警 (Proactive Operations Alert) - 主动发现问题，减少被动响应
    
工作流程 (Workflow):
    1. 后台定时器触发扫描任务
    2. 查询指定时间范围内的异常级别日志
    3. 调用AI引擎进行日志模式分析
    4. 将有价值的分析结果保存为AI洞察
    5. 供前端界面展示和运维人员参考
    
技术特性 (Technical Features):
    - 时间窗口控制：可配置扫描时间范围，平衡性能和覆盖面
    - 日志级别过滤：专注于WARN/ERROR/CRITICAL等异常级别
    - 数量限制：防止大量日志影响AI分析性能
    - 可配置开关：支持动态启用/禁用自动扫描
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import List

from sqlalchemy import select, and_

from app.core.config import settings
from app.core.database import async_session
from app.models.log_entry import LogEntry
from app.models.ai_insight import AIInsight
from app.services.llm_client import analyze_logs_brief
from app.services.suppression_service import SuppressionService

logger = logging.getLogger(__name__)


async def _get_suppressed_host_ids(db) -> set:
    """获取被屏蔽日志扫描的主机 ID 列表 (Get Suppressed Host IDs for Log Scanning)

    Args:
        db: 异步数据库会话

    Returns:
        set: 被屏蔽的主机 ID 集合
    """
    try:
        from sqlalchemy import select, and_, or_
        from app.models.suppression_rule import SuppressionRule
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)

        # 查询屏蔽日志扫描的规则
        result = await db.execute(
            select(SuppressionRule.resource_id)
            .where(
                and_(
                    SuppressionRule.is_active == True,
                    SuppressionRule.resource_type == SuppressionService.RESOURCE_HOST,
                    SuppressionRule.suppress_log_scan == True,
                    SuppressionRule.resource_id != None,
                    # 时间范围检查：开始时间为空或已过
                    or_(
                        SuppressionRule.start_time == None,
                        SuppressionRule.start_time <= now
                    ),
                    # 时间范围检查：结束时间为空或未到
                    or_(
                        SuppressionRule.end_time == None,
                        SuppressionRule.end_time >= now
                    )
                )
            )
        )
        return set(row[0] for row in result.all())
    except Exception as e:
        logger.warning(f"Failed to get suppressed host IDs: {e}")
        return set()


async def scan_recent_logs(hours: int = 1) -> None:
    """
    近期日志异常扫描器 (Recent Log Anomaly Scanner)
    
    功能描述:
        扫描指定时间范围内的异常级别日志，通过AI引擎进行模式分析，
        识别潜在的系统问题、安全威胁或性能异常。
        
    Args:
        hours: 扫描时间窗口，向前追溯的小时数（默认1小时）
        
    执行流程:
        1. 计算扫描时间范围（当前时间向前推hours小时）
        2. 查询异常级别日志（WARN/ERROR/CRITICAL等）
        3. 数据预处理（ORM转字典，限制数量）
        4. 调用AI引擎进行异常模式分析
        5. 保存有价值的分析结果为AI洞察记录
        
    性能优化:
        - 日志数量限制：最多500条，避免AI分析超时
        - 级别过滤：只关注异常级别，忽略INFO/DEBUG
        - 时间倒序：优先分析最新的日志条目
        
    异常处理:
        - 无日志时跳过分析
        - AI分析失败时记录警告
        - 数据库异常时记录错误
    """
    try:
        # 1. 计算扫描时间窗口 (Calculate Scan Time Window)
        since = datetime.now(timezone.utc) - timedelta(hours=hours)

        async with async_session() as db:
            # 2. 构建异常日志查询 (Build Anomaly Log Query)
            # 查询指定时间范围内的异常级别日志，性能优化：最多500条
            q = (
                select(LogEntry)
                .where(
                    and_(
                        LogEntry.timestamp >= since,  # 时间范围过滤
                        # 异常级别过滤：关注可能有问题的日志
                        LogEntry.level.in_(["WARN", "WARNING", "ERROR", "FATAL", "CRITICAL"]),
                    )
                )
                .order_by(LogEntry.timestamp.desc())  # 时间倒序，优先最新日志
                .limit(500)  # 数量限制，避免AI分析超时
            )
            result = await db.execute(q)
            entries = result.scalars().all()

            # 2.1 过滤被屏蔽的主机 (Filter Suppressed Hosts)
            suppressed_host_ids = await _get_suppressed_host_ids(db)
            if suppressed_host_ids:
                original_count = len(entries)
                entries = [e for e in entries if e.host_id not in suppressed_host_ids]
                if len(entries) < original_count:
                    logger.info(f"Filtered out {original_count - len(entries)} log entries from suppressed hosts")

            # 3. 空数据检查 (Empty Data Check)
            if not entries:
                logger.info("Anomaly scan: no WARN/ERROR logs in last %d hour(s)", hours)
                return  # 无异常日志时直接返回

            # 4. 数据格式转换 (Data Format Conversion)
            # 将SQLAlchemy ORM对象转换为AI引擎需要的字典格式
            logs_data: List[dict] = [
                {
                    "timestamp": str(e.timestamp),    # 时间戳字符串化
                    "level": e.level,                 # 日志级别
                    "host_id": e.host_id,             # 来源主机ID
                    "service": e.service,             # 服务名称
                    "message": e.message,             # 日志内容
                }
                for e in entries
            ]

            # 5. AI异常分析 (AI Anomaly Analysis)
            logger.info("Anomaly scan: analyzing %d log entries", len(logs_data))
            analysis = await analyze_logs_brief(logs_data, feature_key="ai_insight")  # 调用 LLM 分析

            # 6. 分析结果处理 (Analysis Result Processing)
            if not analysis.get("error"):
                # 6.1 成功分析：创建AI洞察记录
                insight = AIInsight(
                    insight_type="anomaly",                           # 洞察类型：异常检测
                    severity=analysis.get("severity", "info"),       # 严重程度
                    title=analysis.get("title", "定时扫描结果"),       # 洞察标题
                    summary=analysis.get("summary", ""),             # 摘要描述
                    details=analysis,                                # 完整分析结果（JSON）
                    status="new",                                    # 状态：新发现
                )
                db.add(insight)
                await db.commit()
                logger.info("Anomaly scan: saved insight - %s", analysis.get("title"))
            else:
                # 6.2 分析失败：记录警告，不中断服务
                logger.warning("Anomaly scan: AI analysis returned error")

    except Exception as e:
        # 7. 异常容错处理 (Exception Tolerance Handling)
        # 扫描失败不应该影响其他服务，只记录错误
        logger.error("Anomaly scan failed: %s", str(e))


async def anomaly_scanner_loop(interval_minutes: int = 30) -> None:
    """
    异常扫描后台守护循环 (Anomaly Scanner Background Daemon Loop)
    
    功能描述:
        异常扫描服务的主控循环，按配置间隔定期触发日志异常检测任务。
        实现持续的主动式运维监控，及时发现系统潜在问题。
        
    Args:
        interval_minutes: 扫描间隔时间（分钟），默认30分钟
        
    工作机制:
        1. 无限循环运行，直到进程终止
        2. 按间隔时间周期性睡眠
        3. 检查全局配置开关，动态控制扫描启用状态
        4. 调用日志扫描函数执行实际检测
        
    配置控制:
        - settings.ai_auto_scan: 全局开关，支持动态启用/禁用
        - interval_minutes: 扫描频率，平衡及时性和资源消耗
        - 固定1小时扫描窗口：覆盖最近的异常日志
        
    运维考虑:
        - 适中的扫描间隔：避免过于频繁影响性能
        - 动态开关控制：支持运行时调整扫描策略  
        - 详细日志记录：便于监控服务运行状态
    """
    # 启动日志记录，显示配置参数
    logger.info("Anomaly scanner started (interval=%dm, enabled=%s)", 
                interval_minutes, settings.ai_auto_scan)
    
    # 主守护循环 (Main Daemon Loop)
    while True:
        # 1. 周期性睡眠等待 (Periodic Sleep Wait)
        await asyncio.sleep(interval_minutes * 60)  # 分钟转秒
        
        # 2. 动态配置检查 (Dynamic Configuration Check)
        if settings.ai_auto_scan:
            # 2.1 配置启用时执行扫描
            await scan_recent_logs(hours=1)  # 固定扫描最近1小时日志
        else:
            # 2.2 配置禁用时跳过扫描，记录调试信息
            logger.debug("Anomaly auto-scan is disabled, skipping")
