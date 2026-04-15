"""
SLA 管理路由 (Service Level Agreement Management Router)

功能说明：提供完整的 SLA 管理功能，包括规则配置、实时监控、违规检测和可用性报告
核心职责：
  - SLA 规则的创建、查询和删除管理
  - 实时 SLA 状态看板（可用率计算、错误预算跟踪）
  - SLA 违规事件的记录和查询
  - 可用性报告生成（日趋势、违规统计、总结分析）
  - 多时间窗口支持（日/周/月级别的 SLA 计算）
依赖关系：依赖 SLARule、SLAViolation、Service、ServiceCheck 数据模型
API端点：GET/POST/DELETE /api/v1/sla/rules, GET /api/v1/sla/status, GET /api/v1/sla/violations, GET /api/v1/sla/report

Author: NightMend Team
"""
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, get_operator_user
from app.models.sla import SLARule, SLAViolation
from app.models.service import Service, ServiceCheck
from app.models.user import User
from app.schemas.sla import (
    SLARuleCreate, SLARuleResponse, SLAStatusResponse,
    SLAViolationResponse, SLAReportResponse, DailyAvailability,
)

router = APIRouter(prefix="/api/v1/sla", tags=["sla"])


def _get_window_start(window: str) -> datetime:
    """
    计算 SLA 时间窗口的起始时间 (Calculate SLA Time Window Start)
    
    根据不同的计算窗口类型（daily/weekly/monthly）计算对应的起始时间点。
    用于确定 SLA 可用率统计的时间范围。
    
    Args:
        window: 时间窗口类型，支持 "daily", "weekly", "monthly"
        
    Returns:
        datetime: 时间窗口的起始时间（UTC时区）
        
    Examples:
        daily: 今天 00:00:00
        weekly: 本周一 00:00:00
        monthly: 本月 1 日 00:00:00
    """
    now = datetime.now(timezone.utc)
    if window == "daily":
        # 今天的开始时间（当天 00:00:00）
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif window == "weekly":
        # 本周的开始时间（周一 00:00:00），weekday() 返回0-6，0是周一
        return (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    else:  # monthly
        # 本月的开始时间（本月1日 00:00:00）
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _get_window_days(window: str) -> int:
    """
    获取时间窗口的天数 (Get Time Window Duration in Days)
    
    计算指定时间窗口包含的天数，用于错误预算（Error Budget）计算。
    错误预算 = 总时间 × (1 - SLA目标百分比)
    
    Args:
        window: 时间窗口类型，支持 "daily", "weekly", "monthly"
        
    Returns:
        int: 时间窗口包含的天数
        
    Examples:
        daily: 1 天
        weekly: 7 天  
        monthly: 28-31 天（根据当前月份）
    """
    now = datetime.now(timezone.utc)
    if window == "daily":
        return 1
    elif window == "weekly":
        return 7
    else:  # monthly
        # 使用 calendar 模块获取当前月份的准确天数
        import calendar
        return calendar.monthrange(now.year, now.month)[1]


# ========== SLA 规则管理 (SLA Rules Management) ==========

@router.get("/rules", response_model=list)
async def list_sla_rules(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    获取所有 SLA 规则列表 (Get All SLA Rules List)
    
    查询系统中配置的所有 SLA 规则，包含规则详情和关联的服务信息。
    用于 SLA 管理页面的规则列表展示。
    
    Args:
        user: 当前认证用户
        db: 数据库会话
        
    Returns:
        list[SLARuleResponse]: SLA 规则列表，包含服务名称
        
    Note:
        返回的规则按 ID 升序排列，便于管理员查看
    """
    # 查询所有 SLA 规则，按 ID 排序
    result = await db.execute(select(SLARule).order_by(SLARule.id))
    rules = result.scalars().all()
    
    items = []
    for r in rules:
        # 查询关联的服务名称，用于前端显示
        svc = (await db.execute(select(Service.name).where(Service.id == r.service_id))).scalar()
        items.append(SLARuleResponse(
            id=r.id, 
            service_id=r.service_id, 
            name=r.name,
            target_percent=float(r.target_percent),          # 目标可用率百分比
            calculation_window=r.calculation_window,         # 计算窗口：daily/weekly/monthly
            created_at=r.created_at, 
            updated_at=r.updated_at,
            service_name=svc,                               # 服务名称，便于前端展示
        ))
    return items


@router.post("/rules", response_model=SLARuleResponse)
async def create_sla_rule(
    body: SLARuleCreate,
    user: User = Depends(get_operator_user),
    db: AsyncSession = Depends(get_db),
):
    """
    创建 SLA 规则 (Create SLA Rule)
    
    为指定服务创建 SLA 规则，设定目标可用率和计算窗口。
    每个服务只能有一个 SLA 规则，避免配置冲突。
    
    Args:
        body: SLA 规则创建请求，包含服务ID、目标百分比、计算窗口等
        user: 当前认证用户
        db: 数据库会话
        
    Returns:
        SLARuleResponse: 创建成功的 SLA 规则详情
        
    Raises:
        HTTPException: 404 - 服务不存在
        HTTPException: 400 - 该服务已有 SLA 规则
        
    Examples:
        POST /api/v1/sla/rules
        {
            "service_id": 1,
            "name": "Web服务可用性",
            "target_percent": 99.9,
            "calculation_window": "monthly"
        }
    """
    # 检查关联的服务是否存在
    svc = (await db.execute(select(Service).where(Service.id == body.service_id))).scalar_one_or_none()
    if not svc:
        raise HTTPException(status_code=404, detail="服务不存在")
        
    # 检查该服务是否已有 SLA 规则（业务约束：每服务一规则）
    existing = (await db.execute(
        select(SLARule).where(SLARule.service_id == body.service_id)
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="该服务已有 SLA 规则")

    # 创建新的 SLA 规则
    rule = SLARule(
        service_id=body.service_id, 
        name=body.name,
        target_percent=body.target_percent,         # 目标可用率，如 99.9%
        calculation_window=body.calculation_window, # 计算窗口：daily/weekly/monthly
    )
    db.add(rule)
    await db.commit()           # 提交事务保存到数据库
    await db.refresh(rule)      # 刷新对象获取数据库生成的字段（如ID、时间戳）
    
    # 返回创建成功的规则详情
    return SLARuleResponse(
        id=rule.id, 
        service_id=rule.service_id, 
        name=rule.name,
        target_percent=float(rule.target_percent),
        calculation_window=rule.calculation_window,
        created_at=rule.created_at, 
        updated_at=rule.updated_at,
        service_name=svc.name,  # 包含服务名称便于前端展示
    )


@router.delete("/rules/{rule_id}")
async def delete_sla_rule(
    rule_id: int,
    user: User = Depends(get_operator_user),
    db: AsyncSession = Depends(get_db),
):
    """
    删除 SLA 规则 (Delete SLA Rule)
    
    删除指定的 SLA 规则。删除后该服务将不再进行 SLA 监控和违规检测。
    注意：删除规则不会删除历史的违规记录。
    
    Args:
        rule_id: 要删除的 SLA 规则 ID
        user: 当前认证用户
        db: 数据库会话
        
    Returns:
        dict: 删除成功的确认消息
        
    Raises:
        HTTPException: 404 - SLA 规则不存在
        
    Note:
        删除是硬删除，无法恢复。历史违规记录会保留。
    """
    # 查询要删除的 SLA 规则是否存在
    rule = (await db.execute(select(SLARule).where(SLARule.id == rule_id))).scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")
        
    # 执行删除操作并提交事务
    await db.delete(rule)
    await db.commit()
    return {"detail": "已删除"}


# ========== SLA 状态看板 (SLA Status Dashboard) ==========

@router.get("/status", response_model=list)
async def sla_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    SLA 状态看板 (SLA Status Dashboard)
    
    计算所有 SLA 规则的实时状态，包括当前可用率、目标达成情况和剩余错误预算。
    这是 SLA 监控的核心功能，为运维团队提供服务健康状况的实时视图。
    
    算法说明：
    1. 可用率 = (总检查数 - 故障检查数) / 总检查数 × 100%
    2. 错误预算 = 时间窗口总分钟数 × (1 - 目标可用率) - 已用停机时间
    3. SLA 达成 = 实际可用率 >= 目标可用率
    
    Args:
        user: 当前认证用户
        db: 数据库会话
        
    Returns:
        list[SLAStatusResponse]: 所有 SLA 规则的状态列表
        
    Note:
        无数据的服务将显示为 null 状态，便于识别监控缺失
    """
    # 获取所有 SLA 规则
    result = await db.execute(select(SLARule).order_by(SLARule.id))
    rules = result.scalars().all()
    
    items = []
    for r in rules:
        # 查询关联的服务信息
        svc = (await db.execute(select(Service).where(Service.id == r.service_id))).scalar_one_or_none()
        if not svc:  # 服务不存在，跳过该规则
            continue
            
        # 计算当前时间窗口的起始时间
        window_start = _get_window_start(r.calculation_window)

        # 统计时间窗口内的总检查次数
        total = (await db.execute(
            select(func.count()).select_from(ServiceCheck).where(
                ServiceCheck.service_id == r.service_id,
                ServiceCheck.checked_at >= window_start,
            )
        )).scalar() or 0

        # 统计时间窗口内的故障检查次数（status = "down"）
        down = (await db.execute(
            select(func.count()).select_from(ServiceCheck).where(
                ServiceCheck.service_id == r.service_id,
                ServiceCheck.checked_at >= window_start,
                ServiceCheck.status == "down",
            )
        )).scalar() or 0

        # 如果没有检查数据，返回 null 状态
        if total == 0:
            items.append(SLAStatusResponse(
                rule_id=r.id, service_id=r.service_id,
                service_name=svc.name,
                target_percent=float(r.target_percent),
                actual_percent=None, is_met=None,
                error_budget_remaining_minutes=None,
                calculation_window=r.calculation_window,
                total_checks=0, down_checks=0,
            ))
            continue

        # 计算实际可用率（保留4位小数精度）
        actual = round((total - down) / total * 100, 4)
        target = float(r.target_percent)
        is_met = actual >= target  # 判断是否达到 SLA 目标

        # 错误预算计算 (Error Budget Calculation)
        window_days = _get_window_days(r.calculation_window)    # 获取时间窗口天数
        total_minutes = window_days * 24 * 60                  # 总时间（分钟）
        allowed_downtime = total_minutes * (1 - target / 100)  # 允许的停机时间
        used_downtime = down * svc.check_interval / 60         # 已使用的停机时间
        remaining = round(allowed_downtime - used_downtime, 2) # 剩余错误预算

        items.append(SLAStatusResponse(
            rule_id=r.id, service_id=r.service_id,
            service_name=svc.name,
            target_percent=target, 
            actual_percent=actual,
            is_met=is_met,
            error_budget_remaining_minutes=remaining,          # 剩余错误预算（分钟）
            calculation_window=r.calculation_window,
            total_checks=total,    # 总检查次数
            down_checks=down,      # 故障检查次数
        ))
    return items


# ========== 违规事件 (SLA Violations) ==========

@router.get("/violations", response_model=list)
async def list_violations(
    start_date: str = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: str = Query(None, description="结束日期 YYYY-MM-DD"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    查询 SLA 违规事件列表 (Get SLA Violations List)
    
    查询系统记录的 SLA 违规事件，支持日期范围筛选。
    违规事件是指服务可用率低于 SLA 目标的时间段。
    
    Args:
        start_date: 可选的开始日期，格式 YYYY-MM-DD
        end_date: 可选的结束日期，格式 YYYY-MM-DD
        user: 当前认证用户
        db: 数据库会话
        
    Returns:
        list[SLAViolationResponse]: 违规事件列表，按开始时间倒序排列
        
    Examples:
        GET /api/v1/sla/violations?start_date=2024-01-01&end_date=2024-01-31
        
    Note:
        违规事件由后台任务自动检测和记录，包含持续时间和影响描述
    """
    # 构建基础查询，按违规开始时间倒序排列（最新的在前）
    query = select(SLAViolation).order_by(SLAViolation.started_at.desc())
    
    # 如果指定了开始日期，添加筛选条件
    if start_date:
        query = query.where(SLAViolation.started_at >= datetime.fromisoformat(start_date))
        
    # 如果指定了结束日期，添加筛选条件（包含当天全部时间）
    if end_date:
        end_dt = datetime.fromisoformat(end_date) + timedelta(days=1)  # 结束日期的次日00:00
        query = query.where(SLAViolation.started_at < end_dt)

    # 使用 JOIN 一次查询获取违规事件及关联服务名称，消除 N+1 查询
    joined_query = (
        query
        .add_columns(Service.name.label("service_name"))
        .join(Service, SLAViolation.service_id == Service.id, isouter=True)
    )
    result = await db.execute(joined_query)
    rows = result.all()

    # 构建响应数据，附加服务名称信息
    items = []
    for row in rows:
        v = row[0]
        svc_name = row[1]
        items.append(SLAViolationResponse(
            id=v.id,
            sla_rule_id=v.sla_rule_id,
            service_id=v.service_id,
            service_name=svc_name,                   # 服务名称，便于展示
            started_at=v.started_at,                 # 违规开始时间
            ended_at=v.ended_at,                     # 违规结束时间（可能为空，表示持续中）
            duration_seconds=v.duration_seconds,     # 违规持续时间（秒）
            description=v.description,               # 违规描述信息
            created_at=v.created_at,                 # 记录创建时间
        ))
    return items


# ========== 可用性报告 (Availability Report) ==========

@router.get("/report", response_model=SLAReportResponse)
async def sla_report(
    service_id: Optional[int] = Query(None, description="服务 ID"),
    period: str = Query("monthly", description="报告周期"),
    start_date: str = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: str = Query(None, description="结束日期 YYYY-MM-DD"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    生成 SLA 可用性报告 (Generate SLA Availability Report)
    
    为指定服务生成详细的可用性报告，包括：
    1. 每日可用率趋势图数据
    2. 报告期间内的所有违规事件
    3. 总体可用率统计和目标达成评估
    4. 累计停机时间统计
    5. 智能生成的报告总结
    
    Args:
        service_id: 必需的服务ID
        period: 报告周期类型（暂未使用，保留扩展）
        start_date: 可选的报告开始日期，格式 YYYY-MM-DD
        end_date: 可选的报告结束日期，格式 YYYY-MM-DD
        user: 当前认证用户
        db: 数据库会话
        
    Returns:
        SLAReportResponse: 完整的可用性报告数据
        
    Raises:
        HTTPException: 404 - 服务不存在
        
    Note:
        如果未指定日期范围，默认生成过去30天的报告
    """
    # 如果未指定 service_id，使用第一个有 SLA 规则的服务
    if service_id is None:
        first_rule = (await db.execute(select(SLARule).order_by(SLARule.id).limit(1))).scalar_one_or_none()
        if first_rule:
            service_id = first_rule.service_id
        else:
            raise HTTPException(status_code=400, detail="未指定 service_id 且无可用的 SLA 规则")

    # 确定报告的时间范围
    if start_date and end_date:
        # 使用用户指定的日期范围
        dt_start = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
        dt_end = datetime.fromisoformat(end_date).replace(tzinfo=timezone.utc) + timedelta(days=1)
    else:
        # 默认使用过去30天
        dt_end = datetime.now(timezone.utc)
        dt_start = dt_end - timedelta(days=30)

    # 查询服务信息和关联的 SLA 规则
    svc = (await db.execute(select(Service).where(Service.id == service_id))).scalar_one_or_none()
    if not svc:
        raise HTTPException(status_code=404, detail="服务不存在")
        
    # 查询该服务的 SLA 规则，如果没有则使用默认目标 99.9%
    rule = (await db.execute(
        select(SLARule).where(SLARule.service_id == service_id)
    )).scalar_one_or_none()
    target = float(rule.target_percent) if rule else 99.9

    # 计算每日可用率趋势数据
    daily_trend = []
    current = dt_start.replace(hour=0, minute=0, second=0, microsecond=0)  # 从开始日期的00:00:00开始
    total_all = 0  # 整个报告期间的总检查数
    down_all = 0   # 整个报告期间的故障检查数
    
    while current < dt_end:
        next_day = current + timedelta(days=1)  # 当天的结束时间（次日00:00:00）
        
        # 查询当天的总检查数
        total = (await db.execute(
            select(func.count()).select_from(ServiceCheck).where(
                ServiceCheck.service_id == service_id,
                ServiceCheck.checked_at >= current,
                ServiceCheck.checked_at < next_day,
            )
        )).scalar() or 0
        
        # 查询当天的故障检查数
        down = (await db.execute(
            select(func.count()).select_from(ServiceCheck).where(
                ServiceCheck.service_id == service_id,
                ServiceCheck.checked_at >= current,
                ServiceCheck.checked_at < next_day,
                ServiceCheck.status == "down",
            )
        )).scalar() or 0
        
        # 累计统计
        total_all += total
        down_all += down
        
        # 计算当天的可用率
        avail = round((total - down) / total * 100, 4) if total > 0 else None
        daily_trend.append(DailyAvailability(
            date=current.strftime("%Y-%m-%d"), 
            availability=avail,
        ))
        current = next_day

    # 查询报告期间内的违规事件
    viol_result = await db.execute(
        select(SLAViolation).where(
            SLAViolation.service_id == service_id,
            SLAViolation.started_at >= dt_start,
            SLAViolation.started_at < dt_end,
        ).order_by(SLAViolation.started_at.desc())  # 按时间倒序
    )
    violations = [
        SLAViolationResponse(
            id=v.id, sla_rule_id=v.sla_rule_id, service_id=v.service_id,
            started_at=v.started_at, ended_at=v.ended_at,
            duration_seconds=v.duration_seconds,
            description=v.description, created_at=v.created_at,
        )
        for v in viol_result.scalars().all()
    ]

    # 计算整个报告期间的总体可用率和累计停机时间
    overall = round((total_all - down_all) / total_all * 100, 4) if total_all > 0 else None
    total_downtime = round(down_all * svc.check_interval / 60, 2)  # 转换为分钟

    # 智能生成报告总结
    if overall is None:
        summary = "该服务在报告期间内无检查数据。"
    elif overall >= target:
        summary = f"服务 {svc.name} 在报告期间内可用率 {overall}%，达到 SLA 目标 {target}%。"
    else:
        summary = f"服务 {svc.name} 在报告期间内可用率 {overall}%，未达到 SLA 目标 {target}%，累计停机 {total_downtime} 分钟。"

    # 构建完整的报告响应
    return SLAReportResponse(
        service_id=service_id, 
        service_name=svc.name,
        target_percent=target,                                              # SLA 目标可用率
        period_start=dt_start.strftime("%Y-%m-%d"),                       # 报告开始日期
        period_end=(dt_end - timedelta(days=1)).strftime("%Y-%m-%d"),      # 报告结束日期
        overall_availability=overall,                                       # 总体可用率
        daily_trend=daily_trend,                                           # 每日可用率趋势
        violations=violations,                                              # 违规事件列表
        total_downtime_minutes=total_downtime,                             # 累计停机时间（分钟）
        summary=summary,                                                   # 报告总结
    )
