"""
通知模板路由模块 (Notification Template Router)

功能说明：提供通知模板的完整生命周期管理，支持模板化通知内容
核心职责：
  - 通知模板CRUD操作（创建、查询、更新、删除）
  - 支持动态变量替换的模板系统
  - 管理员权限保护的模板配置
  - 为不同通知渠道提供统一模板管理
依赖关系：依赖SQLAlchemy、管理员权限验证
API端点：GET /notification-templates, POST /notification-templates, GET /notification-templates/{id}, PUT /notification-templates/{id}, DELETE /notification-templates/{id}

Author: NightMend Team
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_role
from app.models.notification_template import NotificationTemplate
from app.schemas.notification_template import (
    NotificationTemplateCreate,
    NotificationTemplateUpdate,
    NotificationTemplateResponse,
)

router = APIRouter(
    prefix="/api/v1/notification-templates",
    tags=["notification-templates"],
    dependencies=[Depends(require_role("admin"))],
)


@router.get("", response_model=List[NotificationTemplateResponse])
async def list_templates(db: AsyncSession = Depends(get_db)):
    """获取所有通知模板列表。"""
    result = await db.execute(
        select(NotificationTemplate).order_by(NotificationTemplate.id.desc())
    )
    return result.scalars().all()


@router.post("", response_model=NotificationTemplateResponse)
async def create_template(
    data: NotificationTemplateCreate, db: AsyncSession = Depends(get_db)
):
    """创建通知模板。如果标记为默认，则取消同类型其他默认模板。"""
    # 如果设为默认，先取消同类型的其他默认模板
    if data.is_default:
        await _clear_default(db, data.channel_type)

    template = NotificationTemplate(**data.model_dump())
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return template


@router.put("/{template_id}", response_model=NotificationTemplateResponse)
async def update_template(
    template_id: int,
    data: NotificationTemplateUpdate,
    db: AsyncSession = Depends(get_db),
):
    """更新通知模板。"""
    result = await db.execute(
        select(NotificationTemplate).where(NotificationTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")

    update_data = data.model_dump(exclude_unset=True)

    # 如果设为默认，先取消同类型的其他默认模板
    if update_data.get("is_default"):
        channel_type = update_data.get("channel_type", template.channel_type)
        await _clear_default(db, channel_type, exclude_id=template_id)

    for key, value in update_data.items():
        setattr(template, key, value)

    await db.commit()
    await db.refresh(template)
    return template


@router.delete("/{template_id}")
async def delete_template(template_id: int, db: AsyncSession = Depends(get_db)):
    """删除通知模板。"""
    result = await db.execute(
        select(NotificationTemplate).where(NotificationTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")

    await db.delete(template)
    await db.commit()
    return {"detail": "已删除"}


async def _clear_default(
    db: AsyncSession, channel_type: str, exclude_id: int | None = None
):
    """取消指定渠道类型的其他默认模板标记。"""
    stmt = select(NotificationTemplate).where(
        NotificationTemplate.channel_type == channel_type,
        NotificationTemplate.is_default == True,  # noqa: E712
    )
    if exclude_id:
        stmt = stmt.where(NotificationTemplate.id != exclude_id)
    result = await db.execute(stmt)
    for t in result.scalars().all():
        t.is_default = False
