"""Alertmanager Silence 管理端点。

反向路由（M7）：NightMend → Alertmanager /api/v2/silences
让用户/Runbook 直接在 NightMend UI 上管理 Alertmanager silences，
不需要切到 AM Web UI 也不会丢失审计链路。
"""
from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, get_operator_user
from app.models.user import User
from app.services import alertmanager_client as am
from app.services.audit import log_audit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/alertmanager", tags=["alertmanager"])


class Matcher(BaseModel):
    name: str
    value: str
    isRegex: bool = False
    isEqual: bool = True


class CreateSilenceRequest(BaseModel):
    matchers: list[Matcher] = Field(..., min_length=1, max_length=20)
    duration_seconds: int = Field(..., ge=60, le=7 * 24 * 3600, description="60s ~ 7d")
    comment: str = Field(..., min_length=1, max_length=500)


@router.post("/silences")
async def create_silence(
    payload: CreateSilenceRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_operator_user),
):
    try:
        silence_id = await am.create_silence(
            matchers=[m.model_dump() for m in payload.matchers],
            duration=timedelta(seconds=payload.duration_seconds),
            created_by=f"nightmend-user:{user.id}",
            comment=payload.comment,
        )
    except am.AlertmanagerUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    await log_audit(
        db, user.id, "create_silence", "alertmanager", 0,
        json.dumps({"silence_id": silence_id, **payload.model_dump()}),
        request.client.host if request.client else None,
    )
    await db.commit()
    return {"silence_id": silence_id}


@router.delete("/silences/{silence_id}", status_code=204)
async def delete_silence(
    silence_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_operator_user),
):
    try:
        await am.delete_silence(silence_id)
    except am.AlertmanagerUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    await log_audit(
        db, user.id, "delete_silence", "alertmanager", 0,
        json.dumps({"silence_id": silence_id}),
        request.client.host if request.client else None,
    )
    await db.commit()


@router.get("/silences")
async def list_silences(
    active_only: bool = True,
    _user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    try:
        return await am.list_silences(active_only=active_only)
    except am.AlertmanagerUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/health")
async def alertmanager_health(_user: User = Depends(get_current_user)):
    """UI 展示 Alertmanager 可达性。"""
    return {"healthy": await am.is_healthy()}
