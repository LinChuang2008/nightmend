"""
运维报告生成服务 (Operations Report Generation Service)

功能描述 (Description):
    VigilOps 智能报告生成引擎，自动化产出专业运维报告。
    通过数据汇总分析、AI驱动内容生成，为运维团队提供洞察和决策支持。
    
核心功能 (Core Features):
    1. 多维数据收集 (Multi-dimensional Data Collection) - 汇总主机、服务、告警、日志、数据库等指标
    2. AI驱动生成 (AI-powered Generation) - 基于结构化数据生成专业Markdown报告
    3. 灵活报告周期 (Flexible Report Periods) - 支持日报、周报等不同时间维度
    4. 状态跟踪 (Status Tracking) - 完整的生成流程状态管理
    
报告结构 (Report Structure):
    1. 概述 (Overview) - 整体运行状况
    2. 主机资源 (Host Resources) - CPU、内存、磁盘使用情况
    3. 服务可用性 (Service Availability) - 服务状态和可用率
    4. 告警分析 (Alert Analysis) - 告警趋势和分布统计
    5. 日志分析 (Log Analysis) - 错误日志热点服务Top10
    6. 数据库状态 (Database Status) - 数据库健康状况
    7. 总结与建议 (Summary & Recommendations) - AI生成的改进建议
    
技术特性 (Technical Features):
    - 数据汇总优化：使用SQL聚合函数提高查询效率
    - 异步处理：支持大数据量的非阻塞处理
    - 状态管理：generating -> completed/failed 的完整流程跟踪
    - 格式化输出：标准Markdown格式，支持图表和样式
"""
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.host import Host
from app.models.host_metric import HostMetric
from app.models.service import Service
from app.models.alert import Alert
from app.models.log_entry import LogEntry
from app.models.db_metric import MonitoredDatabase, DbMetric
from app.models.report import Report
from app.services.llm_client import chat_completion

logger = logging.getLogger(__name__)

# 报告生成AI系统提示词 (Report Generation AI System Prompt)
# Prompt工程：专业运维报告生成器角色定义，确保输出格式和内容质量
REPORT_SYSTEM_PROMPT = """你是 VigilOps 运维报告生成器。根据提供的监控数据，生成专业的运维报告。

报告格式要求：
1. 使用 Markdown 格式
2. 包含以下章节：概述、主机资源、服务可用性、告警分析、日志分析、数据库状态、总结与建议
3. 用数据说话，包含具体数字
4. 风险和异常用 ⚠️ 标注
5. 最后给出改进建议"""


async def _collect_host_summary(db: AsyncSession, start: datetime, end: datetime) -> str:
    """
    主机状态汇总数据收集器 (Host Status Summary Data Collector)
    
    功能描述:
        收集指定时间段内的主机状态分布和资源使用统计，
        为报告生成提供主机资源章节的数据基础。
        
    Args:
        db: 数据库会话
        start: 统计开始时间
        end: 统计结束时间
        
    Returns:
        str: 格式化的主机状态汇总文本
        
    数据维度:
        - 主机数量和状态分布（在线/离线）
        - CPU、内存、磁盘的平均值和峰值
        - 时间段内的资源使用趋势
    """
    # 1. 主机状态分布统计 (Host Status Distribution Statistics)
    # 按状态分组统计主机数量，了解基础设施健康度
    host_result = await db.execute(
        select(Host.status, func.count(Host.id)).group_by(Host.status)
    )
    host_stats = {row[0]: row[1] for row in host_result.all()}
    total_hosts = sum(host_stats.values())

    # 2. 时间段内资源使用指标汇总 (Resource Usage Metrics Summary)
    # 同时计算平均值和峰值，了解资源压力情况
    metric_result = await db.execute(
        select(
            func.avg(HostMetric.cpu_percent),      # CPU平均使用率
            func.avg(HostMetric.memory_percent),   # 内存平均使用率
            func.avg(HostMetric.disk_percent),     # 磁盘平均使用率
            func.max(HostMetric.cpu_percent),      # CPU峰值使用率
            func.max(HostMetric.memory_percent),   # 内存峰值使用率
            func.max(HostMetric.disk_percent),     # 磁盘峰值使用率
        ).where(and_(
            HostMetric.recorded_at >= start, 
            HostMetric.recorded_at < end
        ))
    )
    row = metric_result.one_or_none()

    # 3. 格式化输出汇总信息 (Format Summary Information)
    lines = [
        f"主机总数: {total_hosts}",
        f"在线: {host_stats.get('online', 0)}, 离线: {host_stats.get('offline', 0)}",
    ]
    
    # 3.1 有指标数据时显示详细资源统计
    if row and row[0] is not None:
        lines.extend([
            f"平均 CPU: {row[0]:.1f}%, 峰值: {row[3]:.1f}%",
            f"平均内存: {row[1]:.1f}%, 峰值: {row[4]:.1f}%",
            f"平均磁盘: {row[2]:.1f}%, 峰值: {row[5]:.1f}%",
        ])
    else:
        # 3.2 无指标数据时的友好提示
        lines.append("该时段无指标数据")

    return "\n".join(lines)


async def _collect_service_summary(db: AsyncSession) -> str:
    """
    服务可用性汇总收集器 (Service Availability Summary Collector)
    
    功能描述:
        统计当前所有监控服务的状态分布和整体可用率，
        为报告提供服务可用性章节数据。
        
    Args:
        db: 数据库会话
        
    Returns:
        str: 格式化的服务可用性统计文本
        
    统计指标:
        - 服务总数
        - 正常服务数和异常服务数
        - 整体可用率百分比
    """
    # 按服务状态分组统计 (Group Statistics by Service Status)
    result = await db.execute(
        select(Service.status, func.count(Service.id)).group_by(Service.status)
    )
    stats = {row[0]: row[1] for row in result.all()}
    
    # 计算可用性指标 (Calculate Availability Metrics)
    total = sum(stats.values())                        # 服务总数
    up = stats.get("up", 0)                           # 正常服务数
    rate = (up / total * 100) if total > 0 else 0    # 可用率百分比
    
    return f"服务总数: {total}, 正常: {up}, 异常: {total - up}, 可用率: {rate:.1f}%"


async def _collect_alert_summary(db: AsyncSession, start: datetime, end: datetime) -> str:
    """
    告警统计汇总收集器 (Alert Statistics Summary Collector)
    
    功能描述:
        收集指定时间段内的告警统计数据，按严重级别和状态维度分组。
        为报告提供告警分析章节的基础数据。
        
    Args:
        db: 数据库会话
        start: 统计开始时间
        end: 统计结束时间
        
    Returns:
        str: 格式化的告警统计文本
        
    统计维度:
        - 告警总数
        - 按严重级别分布（critical/warning/info）
        - 按处理状态分布（firing/resolved等）
    """
    # 1. 按严重级别分组统计 (Group by Severity Level)
    sev_result = await db.execute(
        select(Alert.severity, func.count(Alert.id))
        .where(and_(Alert.fired_at >= start, Alert.fired_at < end))
        .group_by(Alert.severity)
    )
    sev_stats = {row[0]: row[1] for row in sev_result.all()}

    # 2. 按告警状态分组统计 (Group by Alert Status)
    status_result = await db.execute(
        select(Alert.status, func.count(Alert.id))
        .where(and_(Alert.fired_at >= start, Alert.fired_at < end))
        .group_by(Alert.status)
    )
    status_stats = {row[0]: row[1] for row in status_result.all()}

    # 3. 格式化统计结果 (Format Statistics Result)
    total = sum(sev_stats.values())
    lines = [f"告警总数: {total}"]
    
    # 3.1 严重级别分布（了解告警影响程度）
    if sev_stats:
        lines.append("按级别: " + ", ".join(f"{k}={v}" for k, v in sev_stats.items()))
    
    # 3.2 处理状态分布（了解响应和恢复情况）
    if status_stats:
        lines.append("按状态: " + ", ".join(f"{k}={v}" for k, v in status_stats.items()))
    
    return "\n".join(lines)


async def _collect_log_summary(db: AsyncSession, start: datetime, end: datetime) -> str:
    """
    错误日志统计收集器 (Error Log Statistics Collector)
    
    功能描述:
        收集指定时间段内的错误日志统计，按服务维度分组并排序。
        识别错误热点服务，为问题排查提供方向。
        
    Args:
        db: 数据库会话
        start: 统计开始时间
        end: 统计结束时间
        
    Returns:
        str: 格式化的错误日志统计文本（Top 10服务）
        
    统计策略:
        - 仅统计ERROR和CRITICAL级别日志
        - 按服务分组聚合错误数量
        - 降序排列，展示Top 10热点服务
        - 计算总错误数，了解整体错误水平
    """
    # 按服务分组统计错误日志数量，降序排列取Top 10
    result = await db.execute(
        select(LogEntry.service, func.count(LogEntry.id).label("cnt"))
        .where(and_(
            LogEntry.timestamp >= start,
            LogEntry.timestamp < end,
            # 仅统计严重级别日志，聚焦关键问题
            LogEntry.level.in_(["ERROR", "CRITICAL", "error", "critical"]),
        ))
        .group_by(LogEntry.service)
        .order_by(func.count(LogEntry.id).desc())  # 错误数量降序，热点服务在前
        .limit(10)  # Top 10 热点服务，避免信息过载
    )
    rows = result.all()
    
    # 无错误日志时的友好提示
    if not rows:
        return "该时段无错误日志"
    
    # 格式化输出错误热点分析
    total_errors = sum(r[1] for r in rows)  # 计算总错误数
    lines = [f"错误日志总数: {total_errors} (Top 10 服务):"]
    for svc, cnt in rows:
        # 服务名处理：空值显示为"未知"
        lines.append(f"  {svc or '未知'}: {cnt} 条")
    return "\n".join(lines)


async def _collect_db_summary(db: AsyncSession) -> str:
    """
    数据库健康状况收集器 (Database Health Status Collector)
    
    功能描述:
        收集当前所有监控数据库的状态信息，
        为报告提供数据库状态章节数据。
        
    Args:
        db: 数据库会话
        
    Returns:
        str: 格式化的数据库状态文本
        
    监控信息:
        - 监控数据库总数
        - 每个数据库的名称、类型和当前状态
        - 支持多种数据库类型（PostgreSQL/MySQL/Oracle等）
    """
    # 查询所有监控数据库配置
    result = await db.execute(select(MonitoredDatabase))
    dbs = result.scalars().all()
    
    # 未配置数据库监控时的提示
    if not dbs:
        return "未配置监控数据库"
    
    # 格式化数据库状态列表
    lines = [f"监控数据库数量: {len(dbs)}"]
    for d in dbs:
        # 显示数据库名称、类型和当前状态
        lines.append(f"  {d.name} ({d.db_type}): {d.status}")
    return "\n".join(lines)


async def generate_report(
    db: AsyncSession,
    report_type: str,
    period_start: datetime,
    period_end: datetime,
    generated_by: Optional[int] = None,
) -> Report:
    """
    运维报告生成核心引擎 (Operations Report Generation Core Engine)
    
    功能描述:
        VigilOps运维报告生成的主控函数，协调数据收集、AI分析和报告输出。
        实现端到端的报告生成流程，支持多种报告类型和周期。
        
    Args:
        db: 数据库会话，用于数据查询和报告存储
        report_type: 报告类型 ("daily"日报 / "weekly"周报)
        period_start: 报告统计起始时间
        period_end: 报告统计结束时间  
        generated_by: 触发用户ID（手动生成），定时任务时为None
        
    Returns:
        Report: 生成完成的报告对象，包含完整内容和状态
        
    生成流程 (Generation Process):
        1. 创建报告记录，状态为generating
        2. 多维度数据收集（主机、服务、告警、日志、数据库）
        3. 构建AI分析请求，调用AI引擎生成内容
        4. 解析AI响应，分离正文和摘要
        5. 更新报告状态为completed/failed
        
    容错机制 (Error Handling):
        - 生成过程中任何异常都不会丢失报告记录
        - 失败时更新状态为failed，记录错误信息
        - 确保数据库一致性和用户体验
    """
    # 1. 报告标题生成 (Report Title Generation)
    # 根据报告类型生成标准化标题格式
    if report_type == "daily":
        title = f"日报 {period_start.strftime('%Y-%m-%d')}"
    else:
        title = f"周报 {period_start.strftime('%Y-%m-%d')}~{period_end.strftime('%Y-%m-%d')}"

    # 2. 创建报告记录 (Create Report Record)
    # 先创建数据库记录，状态为generating，确保流程可追踪
    report = Report(
        title=title,
        report_type=report_type,
        period_start=period_start,
        period_end=period_end,
        content="",              # 初始化为空，生成完成后填充
        summary="",              # 初始化为空，生成完成后填充
        status="generating",     # 生成中状态，标识正在处理
        generated_by=generated_by,
    )
    db.add(report)
    await db.commit()      # 立即提交，确保记录存在
    await db.refresh(report)  # 刷新获取ID等自动生成字段

    try:
        # 3. 多维度数据收集阶段 (Multi-dimensional Data Collection Phase)
        # 并发收集各个维度的监控数据，构建完整的系统运行画像
        host_summary = await _collect_host_summary(db, period_start, period_end)      # 主机资源统计
        service_summary = await _collect_service_summary(db)                          # 服务可用性统计
        alert_summary = await _collect_alert_summary(db, period_start, period_end)    # 告警趋势统计
        log_summary = await _collect_log_summary(db, period_start, period_end)        # 错误日志统计
        db_summary = await _collect_db_summary(db)                                    # 数据库状态统计

        # 4. AI提示词构建 (AI Prompt Construction)
        # 将结构化数据转换为AI理解的自然语言描述
        type_label = "日报" if report_type == "daily" else "周报"
        user_prompt = (
            f"请生成 {period_start.strftime('%Y-%m-%d')} 至 {period_end.strftime('%Y-%m-%d')} 的运维{type_label}。\n\n"
            f"【主机资源】\n{host_summary}\n\n"
            f"【服务可用性】\n{service_summary}\n\n"
            f"【告警统计】\n{alert_summary}\n\n"
            f"【错误日志】\n{log_summary}\n\n"
            f"【数据库状态】\n{db_summary}\n\n"
            f"请生成完整的 Markdown 格式运维报告，并在最后给出一段不超过 100 字的摘要（用【摘要】标记）。"
        )

        # 5. 构建AI对话消息 (Build AI Conversation Messages)
        messages = [
            {"role": "system", "content": REPORT_SYSTEM_PROMPT},  # 系统角色：专业报告生成器
            {"role": "user", "content": user_prompt},             # 用户输入：数据和生成要求
        ]

        # 6. 调用AI引擎生成报告内容 (Call AI Engine to Generate Report Content)
        result_text = await chat_completion(messages, max_tokens=1800, temperature=0.3, feature_key="ops_report")

        # 7. AI响应内容解析 (AI Response Content Parsing)
        # 将AI生成的内容分离为正文和摘要两部分
        content = result_text
        summary = ""
        
        # 7.1 按标记分离摘要和正文内容
        if "【摘要】" in result_text:
            parts = result_text.split("【摘要】", 1)
            content = parts[0].strip()    # 正文部分
            summary = parts[1].strip()    # 摘要部分
        else:
            # 7.2 AI未提供摘要标记时的降级处理
            summary = result_text[:100].replace("\n", " ") + "..."  # 截取前100字作为摘要

        # 8. 更新报告记录为完成状态 (Update Report Record to Completed Status)
        report.content = content         # 完整的Markdown报告内容
        report.summary = summary         # 简短摘要，用于列表展示
        report.status = "completed"      # 成功完成状态
        await db.commit()
        await db.refresh(report)
        logger.info("报告生成成功: %s (id=%d)", title, report.id)

    except Exception as e:
        # 9. 异常处理和失败状态记录 (Exception Handling and Failure Status Recording)
        # 确保任何生成失败都有完整的错误记录，便于问题排查
        logger.error("报告生成失败: %s", str(e))
        report.status = "failed"                    # 失败状态
        report.content = f"生成失败: {str(e)}"        # 错误信息作为内容
        report.summary = f"生成失败: {str(e)}"        # 错误信息作为摘要
        await db.commit()
        await db.refresh(report)

    return report  # 返回完整的报告对象（成功或失败状态）
