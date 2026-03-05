"""
告警规则管理路由模块 (Alert Rules Management Router)

功能说明：提供告警规则的完整生命周期管理，支持多种告警规则类型
核心职责：
  - 告警规则CRUD操作（创建、查询、更新、删除）
  - 支持三种规则类型（指标告警、日志关键字、数据库指标）
  - 内置规则保护机制（禁止删除系统预设规则）
  - 规则启用状态管理和筛选
  - 完整的审计日志记录
依赖关系：依赖SQLAlchemy、JWT认证、审计服务
API端点：GET /alert-rules, POST /alert-rules, GET /alert-rules/{id}, PUT /alert-rules/{id}, DELETE /alert-rules/{id}

Author: VigilOps Team
"""

from typing import Optional, List

import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, get_operator_user
from app.models.alert import AlertRule
from app.models.user import User
from app.schemas.alert import AlertRuleCreate, AlertRuleUpdate, AlertRuleResponse
from app.services.audit import log_audit

router = APIRouter(prefix="/api/v1/alert-rules", tags=["alert-rules"])


@router.get("", response_model=List[AlertRuleResponse])
async def list_alert_rules(
    is_enabled: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """
    告警规则列表查询接口 (Alert Rules List Query)
    
    获取所有告警规则列表，支持按启用状态筛选。
    
    Args:
        is_enabled: 是否启用状态筛选（True/False，None返回全部）
        db: 数据库会话依赖注入
        _user: 当前登录用户（JWT认证）
    Returns:
        List[AlertRuleResponse]: 告警规则列表
    流程：
        1. 构建基础查询，按ID升序排列
        2. 根据is_enabled参数过滤启用状态
        3. 返回包含内置规则和自定义规则的完整列表
    """
    q = select(AlertRule).order_by(AlertRule.id)
    if is_enabled is not None:
        q = q.where(AlertRule.is_enabled == is_enabled)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("", response_model=AlertRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_alert_rule(
    data: AlertRuleCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_operator_user),
):
    """
    创建告警规则接口 (Create Alert Rule)
    
    创建新的自定义告警规则，支持指标、日志关键字、数据库指标三种类型。
    
    Args:
        data: 告警规则创建数据（规则名称、类型、条件、阈值等）
        request: HTTP请求对象（用于获取客户端IP）
        db: 数据库会话依赖注入
        _user: 当前登录用户（创建者）
    Returns:
        AlertRuleResponse: 创建成功的告警规则详情
    流程：
        1. 基于输入数据创建AlertRule对象
        2. 标记为非内置规则（is_builtin=False）
        3. 保存到数据库并获取规则ID
        4. 记录创建操作的审计日志
        5. 返回完整的规则信息
    """
    # 创建告警规则对象，标记为用户自定义规则 (Create alert rule object, mark as user-defined rule)
    rule = AlertRule(**data.model_dump(), is_builtin=False)
    db.add(rule)
    await db.flush()  # 获取自动生成的规则ID
    
    # 记录创建操作的审计日志，包含完整的规则配置 (Log creation audit with complete rule configuration)
    await log_audit(db, _user.id, "create_alert_rule", "alert_rule", rule.id,
                    json.dumps(data.model_dump()),  # 序列化规则配置用于审计
                    request.client.host if request.client else None)
    await db.commit()
    await db.refresh(rule)
    return rule


@router.get("/{rule_id}", response_model=AlertRuleResponse)
async def get_alert_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """
    单个告警规则详情查询接口 (Single Alert Rule Detail Query)
    
    根据规则ID获取告警规则的完整详细信息。
    
    Args:
        rule_id: 告警规则记录ID
        db: 数据库会话依赖注入
        _user: 当前登录用户（JWT认证）
    Returns:
        AlertRuleResponse: 告警规则详情响应
    Raises:
        HTTPException 404: 告警规则不存在
    流程：
        1. 根据rule_id查询告警规则记录
        2. 检查规则是否存在
        3. 返回规则的完整配置信息
    """
    result = await db.execute(select(AlertRule).where(AlertRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    return rule


@router.put("/{rule_id}", response_model=AlertRuleResponse)
async def update_alert_rule(
    rule_id: int,
    data: AlertRuleUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_operator_user),
):
    """
    更新告警规则接口 (Update Alert Rule)
    
    更新指定的告警规则配置，支持部分字段更新。
    
    Args:
        rule_id: 告警规则记录ID
        data: 告警规则更新数据（仅包含需要更新的字段）
        request: HTTP请求对象（用于获取客户端IP）
        db: 数据库会话依赖注入
        _user: 当前登录用户（更新操作者）
    Returns:
        AlertRuleResponse: 更新后的告警规则详情
    Raises:
        HTTPException 404: 告警规则不存在
    流程：
        1. 根据rule_id查询现有告警规则
        2. 获取请求中包含的更新字段（exclude_unset=True）
        3. 逐个字段更新规则属性
        4. 记录更新操作的审计日志
        5. 提交更改并返回更新后的规则
    """
    result = await db.execute(select(AlertRule).where(AlertRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Alert rule not found")

    # 获取请求中包含的更新字段，忽略未设置的字段 (Get only updated fields from request, ignore unset fields)
    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(rule, field, value)  # 动态更新规则属性

    # 记录更新操作的审计日志，仅包含变更的字段 (Log update audit with only changed fields)
    await log_audit(db, _user.id, "update_alert_rule", "alert_rule", rule_id,
                    json.dumps(updates),  # 仅记录变更内容，不是全量配置
                    request.client.host if request.client else None)
    await db.commit()
    await db.refresh(rule)
    return rule


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert_rule(
    rule_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_operator_user),
):
    """
    删除告警规则接口 (Delete Alert Rule)
    
    删除指定的告警规则，内置规则受保护禁止删除。
    
    Args:
        rule_id: 告警规则记录ID
        request: HTTP请求对象（用于获取客户端IP）
        db: 数据库会话依赖注入
        _user: 当前登录用户（删除操作者）
    Raises:
        HTTPException 404: 告警规则不存在
        HTTPException 400: 尝试删除内置规则
    流程：
        1. 根据rule_id查询告警规则记录
        2. 检查规则是否存在
        3. 检查规则是否为内置规则（is_builtin=True）
        4. 内置规则禁止删除，抛出400错误
        5. 记录删除操作的审计日志
        6. 从数据库中删除规则记录
    """
    result = await db.execute(select(AlertRule).where(AlertRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    # 保护内置规则不被删除，确保系统核心规则完整性 (Protect built-in rules from deletion to ensure system integrity)
    if rule.is_builtin:
        raise HTTPException(status_code=400, detail="Cannot delete built-in rule")

    # 记录删除操作的审计日志 (Log deletion audit)
    await log_audit(db, _user.id, "delete_alert_rule", "alert_rule", rule_id,
                    None,  # 删除操作不需要记录具体内容
                    request.client.host if request.client else None)
    await db.delete(rule)  # 从数据库中物理删除规则
    await db.commit()
