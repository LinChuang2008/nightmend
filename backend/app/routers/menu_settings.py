"""全局菜单设置路由。"""
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.menu_setting import MenuSetting
from app.models.user import User
from app.schemas.menu_setting import MenuSettingResponse, MenuSettingUpdate
from app.services.audit import log_audit

router = APIRouter(prefix="/api/v1/menu-settings", tags=["menu-settings"])


@router.get("", response_model=MenuSettingResponse)
async def get_menu_settings(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(select(MenuSetting).order_by(MenuSetting.id.asc()).limit(1))
    setting = result.scalar_one_or_none()
    if not setting:
        return MenuSettingResponse(hidden_keys=[])
    return MenuSettingResponse(hidden_keys=setting.hidden_keys or [])


@router.put("", response_model=MenuSettingResponse)
async def update_menu_settings(
    payload: MenuSettingUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    result = await db.execute(select(MenuSetting).order_by(MenuSetting.id.asc()).limit(1))
    setting = result.scalar_one_or_none()
    hidden_keys = [k for k in payload.hidden_keys if isinstance(k, str) and k.startswith("/")]

    if not setting:
        setting = MenuSetting(hidden_keys=hidden_keys, updated_by=user.id)
        db.add(setting)
    else:
        setting.hidden_keys = hidden_keys
        setting.updated_by = user.id

    await log_audit(
        db,
        user.id,
        "update_menu_settings",
        "menu_settings",
        setting.id if setting.id else None,
        json.dumps({"hidden_keys": hidden_keys}, ensure_ascii=False),
        request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(setting)
    return MenuSettingResponse(hidden_keys=setting.hidden_keys or [])

