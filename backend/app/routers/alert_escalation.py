"""
告警升级管理路由模块 (Alert Escalation Management Router)

功能说明：提供告警升级的完整管理接口，包括升级规则配置、手动升级、升级历史查询
核心职责：
  - 升级规则的创建、查询、更新、删除操作
  - 手动告警升级操作和升级历史追踪
  - 升级统计分析和引擎状态管理
  - 与告警系统集成的升级流程控制
依赖关系：依赖SQLAlchemy、JWT认证、审计服务、升级引擎服务
API端点：CRUD for escalation rules + manual escalation + statistics

Author: NightMend Team
"""

from datetime import datetime, date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select, func, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.escalation import EscalationRule, AlertEscalation
from app.models.user import User
from app.schemas.escalation import (
    EscalationRuleCreate, EscalationRuleUpdate, EscalationRuleResponse,
    AlertEscalationResponse, ManualEscalationRequest, EscalationStatsResponse
)
from app.services.escalation_engine import EscalationEngine
from app.services.audit import log_audit

router = APIRouter(prefix="/api/v1/alert-escalation", tags=["alert-escalation"])


# ===== 升级规则管理 (Escalation Rule Management) =====

@router.get("/rules", response_model=dict)
async def list_escalation_rules(
    alert_rule_id: Optional[int] = None,
    is_enabled: Optional[bool] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """
    升级规则列表查询接口 (Escalation Rule List Query)
    
    分页查询升级规则，支持按告警规则和启用状态筛选。
    
    Args:
        alert_rule_id: 告警规则ID筛选
        is_enabled: 是否启用状态筛选
        page: 页码，从1开始
        page_size: 每页数量，限制1-100之间
        db: 数据库会话依赖注入
        _user: 当前登录用户（JWT认证）
    Returns:
        dict: 包含升级规则列表、总数、分页信息的响应
    """
    # 构建查询条件
    q = select(EscalationRule)
    count_q = select(func.count(EscalationRule.id))
    
    filters = []
    if alert_rule_id:
        filters.append(EscalationRule.alert_rule_id == alert_rule_id)
    if is_enabled is not None:
        filters.append(EscalationRule.is_enabled == is_enabled)
    
    if filters:
        q = q.where(and_(*filters))
        count_q = count_q.where(and_(*filters))
    
    # 执行查询
    total = (await db.execute(count_q)).scalar()
    q = q.order_by(EscalationRule.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(q)
    rules = result.scalars().all()
    
    return {
        "items": [EscalationRuleResponse.model_validate(r).model_dump(mode="json") for r in rules],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/rules", response_model=EscalationRuleResponse)
async def create_escalation_rule(
    rule_data: EscalationRuleCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    创建升级规则接口 (Create Escalation Rule)
    
    创建新的告警升级规则配置。
    
    Args:
        rule_data: 升级规则创建数据
        request: HTTP请求对象
        db: 数据库会话依赖注入
        user: 当前登录用户
    Returns:
        EscalationRuleResponse: 创建的升级规则信息
    Raises:
        HTTPException 400: 数据验证失败
    """
    # 验证升级级别配置
    levels = rule_data.escalation_levels
    if not levels:
        raise HTTPException(status_code=400, detail="At least one escalation level is required")
    
    # 检查级别连续性
    level_numbers = sorted([level.level for level in levels])
    if level_numbers != list(range(1, len(level_numbers) + 1)):
        raise HTTPException(status_code=400, detail="Escalation levels must be consecutive starting from 1")
    
    # 创建升级规则
    rule_dict = rule_data.model_dump()
    rule_dict["escalation_levels"] = [level.model_dump() for level in levels]
    
    db_rule = EscalationRule(**rule_dict)
    db.add(db_rule)
    await db.commit()
    await db.refresh(db_rule)
    
    # 记录审计日志
    await log_audit(db, user.id, "create_escalation_rule", "escalation_rule", db_rule.id,
                    None, request.client.host if request.client else None)
    
    return db_rule


@router.get("/rules/{rule_id}", response_model=EscalationRuleResponse)
async def get_escalation_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """获取单个升级规则详情 (Get Single Escalation Rule Detail)"""
    result = await db.execute(select(EscalationRule).where(EscalationRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Escalation rule not found")
    return rule


@router.put("/rules/{rule_id}", response_model=EscalationRuleResponse)
async def update_escalation_rule(
    rule_id: int,
    rule_data: EscalationRuleUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    更新升级规则接口 (Update Escalation Rule)
    
    更新指定升级规则的配置信息。
    
    Args:
        rule_id: 升级规则ID
        rule_data: 更新数据
        request: HTTP请求对象
        db: 数据库会话依赖注入
        user: 当前登录用户
    Returns:
        EscalationRuleResponse: 更新后的升级规则信息
    """
    result = await db.execute(select(EscalationRule).where(EscalationRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Escalation rule not found")
    
    # 更新字段
    update_data = rule_data.model_dump(exclude_unset=True)
    
    # 如果更新升级级别，需要验证
    if "escalation_levels" in update_data:
        levels = update_data["escalation_levels"]
        if levels:
            level_numbers = sorted([level.level for level in levels])
            if level_numbers != list(range(1, len(level_numbers) + 1)):
                raise HTTPException(status_code=400, detail="Escalation levels must be consecutive starting from 1")
        # 转换为字典格式
        update_data["escalation_levels"] = [level.model_dump() for level in levels]
    
    for field, value in update_data.items():
        setattr(rule, field, value)
    
    await db.commit()
    await db.refresh(rule)
    
    # 记录审计日志
    await log_audit(db, user.id, "update_escalation_rule", "escalation_rule", rule_id,
                    update_data, request.client.host if request.client else None)
    
    return rule


@router.delete("/rules/{rule_id}")
async def delete_escalation_rule(
    rule_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    删除升级规则接口 (Delete Escalation Rule)
    
    删除指定的升级规则（软删除，设置为禁用状态）。
    
    Args:
        rule_id: 升级规则ID
        request: HTTP请求对象
        db: 数据库会话依赖注入
        user: 当前登录用户
    Returns:
        dict: 删除结果
    """
    result = await db.execute(select(EscalationRule).where(EscalationRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Escalation rule not found")
    
    # 软删除：设置为禁用状态
    rule.is_enabled = False
    await db.commit()
    
    # 记录审计日志
    await log_audit(db, user.id, "delete_escalation_rule", "escalation_rule", rule_id,
                    None, request.client.host if request.client else None)
    
    return {"message": "Escalation rule deleted successfully"}


# ===== 手动升级操作 (Manual Escalation Operations) =====

@router.post("/alerts/{alert_id}/escalate", response_model=AlertEscalationResponse)
async def manual_escalate_alert(
    alert_id: int,
    escalation_data: ManualEscalationRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    手动升级告警接口 (Manual Alert Escalation)
    
    手动执行告警升级操作。
    
    Args:
        alert_id: 告警ID
        escalation_data: 升级请求数据
        request: HTTP请求对象
        db: 数据库会话依赖注入
        user: 当前登录用户
    Returns:
        AlertEscalationResponse: 升级记录信息
    Raises:
        HTTPException 400: 告警状态不允许升级
        HTTPException 404: 告警不存在
    """
    try:
        escalation_record = await EscalationEngine.manual_escalate_alert(
            db, alert_id, escalation_data.to_severity, user.id, escalation_data.message
        )
        
        # 记录审计日志
        await log_audit(db, user.id, "manual_escalate_alert", "alert", alert_id,
                        escalation_data.model_dump(), request.client.host if request.client else None)
        
        return escalation_record
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ===== 升级历史查询 (Escalation History Query) =====

@router.get("/history", response_model=dict)
async def list_escalation_history(
    alert_id: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """
    升级历史列表查询接口 (Escalation History List Query)
    
    分页查询告警升级历史记录，支持多维度筛选。
    
    Args:
        alert_id: 告警ID筛选
        start_date: 开始日期筛选
        end_date: 结束日期筛选
        page: 页码
        page_size: 每页数量
        db: 数据库会话依赖注入
        _user: 当前登录用户
    Returns:
        dict: 分页的升级历史列表
    """
    # 构建查询条件
    q = select(AlertEscalation)
    count_q = select(func.count(AlertEscalation.id))
    
    filters = []
    if alert_id:
        filters.append(AlertEscalation.alert_id == alert_id)
    if start_date:
        filters.append(AlertEscalation.escalated_at >= datetime.combine(start_date, datetime.min.time()))
    if end_date:
        filters.append(AlertEscalation.escalated_at <= datetime.combine(end_date, datetime.max.time()))
    
    if filters:
        q = q.where(and_(*filters))
        count_q = count_q.where(and_(*filters))
    
    # 执行查询
    total = (await db.execute(count_q)).scalar()
    q = q.order_by(desc(AlertEscalation.escalated_at)).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(q)
    escalations = result.scalars().all()
    
    return {
        "items": [AlertEscalationResponse.model_validate(e).model_dump(mode="json") for e in escalations],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/alerts/{alert_id}/escalations", response_model=list[AlertEscalationResponse])
async def get_alert_escalations(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """
    获取单个告警的升级历史 (Get Escalation History for Single Alert)
    
    查询指定告警的所有升级记录。
    
    Args:
        alert_id: 告警ID
        db: 数据库会话依赖注入
        _user: 当前登录用户
    Returns:
        list[AlertEscalationResponse]: 升级历史列表
    """
    query = select(AlertEscalation).where(
        AlertEscalation.alert_id == alert_id
    ).order_by(desc(AlertEscalation.escalated_at))
    
    result = await db.execute(query)
    escalations = result.scalars().all()
    
    return [AlertEscalationResponse.model_validate(e).model_dump(mode="json") for e in escalations]


# ===== 升级统计和引擎管理 (Escalation Statistics and Engine Management) =====

@router.get("/stats", response_model=EscalationStatsResponse)
async def get_escalation_stats(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """
    获取升级统计信息接口 (Get Escalation Statistics)
    
    统计指定时间段内的告警升级情况。
    
    Args:
        start_date: 统计开始日期，默认为当月1日
        end_date: 统计结束日期，默认为今天
        db: 数据库会话依赖注入
        _user: 当前登录用户
    Returns:
        EscalationStatsResponse: 升级统计信息
    """
    # 设置默认日期范围
    if not end_date:
        end_date = date.today()
    if not start_date:
        start_date = date(end_date.year, end_date.month, 1)
    
    # 基础查询条件
    date_filter = and_(
        AlertEscalation.escalated_at >= datetime.combine(start_date, datetime.min.time()),
        AlertEscalation.escalated_at <= datetime.combine(end_date, datetime.max.time())
    )
    
    # 总升级次数
    total_query = select(func.count(AlertEscalation.id)).where(date_filter)
    total_escalations = (await db.execute(total_query)).scalar()
    
    # 今日升级次数
    today = date.today()
    today_filter = and_(
        AlertEscalation.escalated_at >= datetime.combine(today, datetime.min.time()),
        AlertEscalation.escalated_at <= datetime.combine(today, datetime.max.time())
    )
    today_query = select(func.count(AlertEscalation.id)).where(today_filter)
    today_escalations = (await db.execute(today_query)).scalar()
    
    # 按严重程度统计
    severity_query = select(
        AlertEscalation.to_severity,
        func.count(AlertEscalation.id).label('count')
    ).where(date_filter).group_by(AlertEscalation.to_severity)
    
    severity_result = await db.execute(severity_query)
    escalations_by_severity = {row.to_severity: row.count for row in severity_result}
    
    # 按升级级别统计
    level_query = select(
        AlertEscalation.escalation_level,
        func.count(AlertEscalation.id).label('count')
    ).where(date_filter).group_by(AlertEscalation.escalation_level)
    
    level_result = await db.execute(level_query)
    escalations_by_level = {str(row.escalation_level): row.count for row in level_result}
    
    return EscalationStatsResponse(
        total_escalations=total_escalations,
        today_escalations=today_escalations,
        escalations_by_severity=escalations_by_severity,
        escalations_by_level=escalations_by_level
    )


@router.post("/engine/scan")
async def trigger_escalation_scan(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    触发升级引擎扫描接口 (Trigger Escalation Engine Scan)
    
    手动触发告警升级引擎的扫描和执行过程。
    
    Args:
        request: HTTP请求对象
        db: 数据库会话依赖注入
        user: 当前登录用户
    Returns:
        dict: 扫描执行结果
    """
    try:
        scan_result = await EscalationEngine.scan_and_escalate_alerts(db)
        
        # 记录审计日志
        await log_audit(db, user.id, "trigger_escalation_scan", "system", None,
                        scan_result, request.client.host if request.client else None)
        
        return {
            "message": "Escalation scan completed",
            "result": scan_result
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Escalation scan failed: {str(e)}")