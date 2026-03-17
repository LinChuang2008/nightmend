"""
屏蔽规则 API 路由 (Suppression Rules API Router)

提供屏蔽规则的 CRUD 接口，支持创建、查询、更新、删除屏蔽规则。
提供快速屏蔽接口，用于前端"忽略"按钮。

Provides CRUD API endpoints for suppression rules, including create, read, update, delete.
Provides quick suppress endpoint for frontend "ignore" button.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.suppression_rule import (
    SuppressionRuleCreate,
    SuppressionRuleUpdate,
    SuppressionRuleResponse,
    SuppressionRuleListResponse,
    QuickSuppressRequest
)
from app.services.suppression_service import SuppressionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/suppression-rules", tags=["suppression-rules"])


@router.post("", response_model=SuppressionRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_suppression_rule(
    data: SuppressionRuleCreate,
    db: AsyncSession = Depends(get_db)
):
    """创建屏蔽规则 (Create Suppression Rule)

    创建一个新的屏蔽规则，用于控制告警和通知的发送。

    Args:
        data: 屏蔽规则创建请求
        db: 数据库会话

    Returns:
        SuppressionRuleResponse: 创建的屏蔽规则
    """
    service = SuppressionService(db)

    # 获取当前用户（简化处理，实际应从 JWT token 获取）
    created_by = "system"  # TODO: 从认证上下文获取用户名

    rule = await service.create_rule(
        resource_type=data.resource_type,
        resource_id=data.resource_id,
        resource_pattern=data.resource_pattern,
        alert_rule_id=data.alert_rule_id,
        start_time=data.start_time,
        end_time=data.end_time,
        suppress_alerts=data.suppress_alerts,
        suppress_notifications=data.suppress_notifications,
        suppress_ai_analysis=data.suppress_ai_analysis,
        suppress_log_scan=data.suppress_log_scan,
        reason=data.reason,
        created_by=created_by
    )

    logger.info(f"Created suppression rule {rule.id} by {created_by}")
    return rule


@router.post("/quick-suppress", response_model=SuppressionRuleResponse, status_code=status.HTTP_201_CREATED)
async def quick_suppress(
    data: QuickSuppressRequest,
    db: AsyncSession = Depends(get_db)
):
    """快速屏蔽 (Quick Suppress)

    快速创建屏蔽规则，用于前端"忽略"按钮。

    Args:
        data: 快速屏蔽请求
        db: 数据库会话

    Returns:
        SuppressionRuleResponse: 创建的屏蔽规则
    """
    service = SuppressionService(db)

    # 获取当前用户
    created_by = "system"  # TODO: 从认证上下文获取用户名

    rule = await service.quick_suppress(
        resource_type=data.resource_type,
        resource_id=data.resource_id,
        created_by=created_by,
        reason=data.reason,
        duration_hours=data.duration_hours
    )

    logger.info(f"Quick suppress created rule {rule.id} by {created_by}")
    return rule


@router.get("", response_model=SuppressionRuleListResponse)
async def list_suppression_rules(
    resource_type: Optional[str] = Query(None, description="资源类型过滤"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_db)
):
    """获取屏蔽规则列表 (List Suppression Rules)

    查询屏蔽规则列表，支持按资源类型过滤和分页。

    Args:
        resource_type: 资源类型过滤
        page: 页码
        page_size: 每页数量
        db: 数据库会话

    Returns:
        SuppressionRuleListResponse: 屏蔽规则列表
    """
    service = SuppressionService(db)
    result = await service.get_active_rules(
        resource_type=resource_type,
        page=page,
        page_size=page_size
    )

    return SuppressionRuleListResponse(
        items=result["items"],
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"]
    )


@router.get("/check", response_model=dict)
async def check_suppression(
    resource_type: str = Query(..., description="资源类型"),
    resource_id: Optional[int] = Query(None, description="资源 ID"),
    alert_rule_id: Optional[int] = Query(None, description="告警规则 ID"),
    db: AsyncSession = Depends(get_db)
):
    """检查屏蔽状态 (Check Suppression Status)

    检查指定资源是否被屏蔽。

    Args:
        resource_type: 资源类型
        resource_id: 资源 ID
        alert_rule_id: 告警规则 ID
        db: 数据库会话

    Returns:
        dict: {"suppressed": bool, "rules": list}
    """
    from app.models.suppression_rule import SuppressionRule
    from sqlalchemy import select, and_
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)

    # 构建查询条件
    conditions = [
        SuppressionRule.is_active == True,
        SuppressionRule.resource_type == resource_type,
    ]

    # 时间范围检查：开始时间为空或已到，结束时间为空或未到
    from sqlalchemy import or_
    conditions.append(
        or_(
            SuppressionRule.start_time == None,
            SuppressionRule.start_time <= now
        )
    )
    conditions.append(
        or_(
            SuppressionRule.end_time == None,
            SuppressionRule.end_time >= now
        )
    )

    # 资源 ID 匹配
    if resource_id is not None:
        conditions.append(
            SuppressionRule.resource_id == resource_id
        )

    # 告警规则 ID 匹配
    if alert_rule_id is not None:
        conditions.append(
            SuppressionRule.alert_rule_id == alert_rule_id
        )

    # 执行查询
    result = await db.execute(
        select(SuppressionRule).where(and_(*conditions))
    )
    rules = result.scalars().all()

    return {
        "suppressed": len(rules) > 0,
        "rules": [
            {
                "id": r.id,
                "reason": r.reason,
                "end_time": r.end_time.isoformat() if r.end_time else None
            }
            for r in rules
        ]
    }


@router.get("/{rule_id}", response_model=SuppressionRuleResponse)
async def get_suppression_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db)
):
    """获取单个屏蔽规则 (Get Suppression Rule)

    根据 ID 查询屏蔽规则详情。

    Args:
        rule_id: 规则 ID
        db: 数据库会话

    Returns:
        SuppressionRuleResponse: 屏蔽规则详情
    """
    from app.models.suppression_rule import SuppressionRule
    from sqlalchemy import select

    result = await db.execute(
        select(SuppressionRule).where(SuppressionRule.id == rule_id)
    )
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Suppression rule {rule_id} not found"
        )

    return rule


@router.put("/{rule_id}", response_model=SuppressionRuleResponse)
async def update_suppression_rule(
    rule_id: int,
    data: SuppressionRuleUpdate,
    db: AsyncSession = Depends(get_db)
):
    """更新屏蔽规则 (Update Suppression Rule)

    更新屏蔽规则的配置。

    Args:
        rule_id: 规则 ID
        data: 更新请求
        db: 数据库会话

    Returns:
        SuppressionRuleResponse: 更新后的屏蔽规则
    """
    service = SuppressionService(db)

    rule = await service.update_rule(
        rule_id=rule_id,
        **data.model_dump(exclude_unset=True)
    )

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Suppression rule {rule_id} not found"
        )

    logger.info(f"Updated suppression rule {rule_id}")
    return rule


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_suppression_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db)
):
    """删除屏蔽规则（软删除） (Delete Suppression Rule)

    软删除屏蔽规则（设置 is_active=False）。

    Args:
        rule_id: 规则 ID
        db: 数据库会话
    """
    service = SuppressionService(db)

    success = await service.delete_rule(rule_id=rule_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Suppression rule {rule_id} not found"
        )

    logger.info(f"Deactivated suppression rule {rule_id}")
    return None
