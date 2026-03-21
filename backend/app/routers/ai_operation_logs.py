"""AI 操作日志查询路由。"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.ai_operation_log import AIOperationLog
from app.models.user import User

router = APIRouter(prefix="/api/v1/ai-operation-logs", tags=["ai-operation-logs"])


@router.get("")
async def list_ai_operation_logs(
    user_id: Optional[int] = None,
    host_id: Optional[int] = None,
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    filters = []
    if user_id is not None:
        filters.append(AIOperationLog.user_id == user_id)
    if host_id is not None:
        filters.append(AIOperationLog.host_id == host_id)
    if status:
        filters.append(AIOperationLog.status == status)
    where = and_(*filters) if filters else True

    total = (await db.execute(select(func.count(AIOperationLog.id)).where(where))).scalar() or 0

    result = await db.execute(
        select(AIOperationLog, User.name)
        .join(User, User.id == AIOperationLog.user_id)
        .where(where)
        .order_by(AIOperationLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    rows = result.all()
    return {
        "items": [
            {
                "id": log.id,
                "user_id": log.user_id,
                "user_name": user_name,
                "session_id": log.session_id,
                "request_id": log.request_id,
                "host_id": log.host_id,
                "host_name": log.host_name,
                "command": log.command,
                "reason": log.reason,
                "exit_code": log.exit_code,
                "duration_ms": log.duration_ms,
                "status": log.status,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log, user_name in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }

