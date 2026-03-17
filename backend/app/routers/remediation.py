"""
自动修复路由模块 (Automatic Remediation Router)

功能说明：提供智能自动修复系统的管理和审计接口
核心职责：
  - 修复操作日志查询（支持多维度筛选）
  - 修复操作审批流程（审批、拒绝机制）
  - 手动触发修复任务执行
  - 修复成功率和效果统计分析
  - 集成6个内置Runbook（磁盘清理、内存释放、服务重启等）
依赖关系：依赖SQLAlchemy、JWT认证、审计服务、修复引擎
API端点：GET /remediations, POST /remediations/{id}/approve, POST /remediations/{id}/reject, POST /remediations/trigger, GET /remediations/stats

Author: VigilOps Team
"""

from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select, func, and_, extract
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.remediation_log import RemediationLog
from app.models.alert import Alert
from app.models.host import Host
from app.models.user import User
from app.schemas.remediation import (
    RemediationLogResponse,
    RemediationStatsResponse,
    RemediationApproveRequest,
)
from app.services.audit import log_audit

router = APIRouter(prefix="/api/v1/remediations", tags=["remediations"])


@router.get("", response_model=dict)
async def list_remediations(
    status: Optional[str] = None,
    host: Optional[str] = None,
    triggered_by: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """获取修复日志列表，支持按状态、主机和触发方式筛选，分页返回。"""
    base_q = (
        select(RemediationLog, Alert.title.label("alert_name"), Host.hostname.label("host_name"))
        .outerjoin(Alert, RemediationLog.alert_id == Alert.id)
        .outerjoin(Host, RemediationLog.host_id == Host.id)
    )
    count_q = (
        select(func.count())
        .select_from(RemediationLog)
        .outerjoin(Alert, RemediationLog.alert_id == Alert.id)
        .outerjoin(Host, RemediationLog.host_id == Host.id)
    )

    filters = []
    if status:
        filters.append(RemediationLog.status == status)
    if host:
        filters.append(Host.hostname == host)
    if triggered_by:
        filters.append(RemediationLog.triggered_by == triggered_by)

    if filters:
        base_q = base_q.where(and_(*filters))
        count_q = count_q.where(and_(*filters))

    total = (await db.execute(count_q)).scalar()
    base_q = base_q.order_by(RemediationLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(base_q)
    rows = result.all()

    items = []
    for row in rows:
        log, alert_name, host_name = row[0], row[1], row[2]
        data = RemediationLogResponse.model_validate(log).model_dump(mode="json")
        data["alert_name"] = alert_name
        data["host"] = host_name
        items.append(data)

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/stats", response_model=RemediationStatsResponse)
async def remediation_stats(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """获取修复统计信息：成功率、平均修复时间、今日/本周数量。"""
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=today_start.weekday())

    total = (await db.execute(select(func.count(RemediationLog.id)))).scalar() or 0
    success = (await db.execute(
        select(func.count(RemediationLog.id)).where(RemediationLog.status == "success")
    )).scalar() or 0
    failed = (await db.execute(
        select(func.count(RemediationLog.id)).where(RemediationLog.status == "failed")
    )).scalar() or 0
    pending = (await db.execute(
        select(func.count(RemediationLog.id)).where(
            RemediationLog.status.in_(["pending", "pending_approval", "diagnosing", "executing", "verifying"])
        )
    )).scalar() or 0

    success_rate = round(success / total * 100, 1) if total > 0 else 0.0

    # 平均修复时间（仅已完成的）
    avg_q = select(
        func.avg(
            extract("epoch", RemediationLog.completed_at) - extract("epoch", RemediationLog.started_at)
        )
    ).where(RemediationLog.completed_at.isnot(None))
    avg_duration = (await db.execute(avg_q)).scalar()

    today_count = (await db.execute(
        select(func.count(RemediationLog.id)).where(RemediationLog.created_at >= today_start)
    )).scalar() or 0
    week_count = (await db.execute(
        select(func.count(RemediationLog.id)).where(RemediationLog.created_at >= week_start)
    )).scalar() or 0

    return RemediationStatsResponse(
        total=total,
        success=success,
        failed=failed,
        pending=pending,
        success_rate=success_rate,
        avg_duration_seconds=round(avg_duration, 1) if avg_duration else None,
        today_count=today_count,
        week_count=week_count,
    )


@router.get("/{remediation_id}", response_model=RemediationLogResponse)
async def get_remediation(
    remediation_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """根据 ID 获取单条修复日志详情。"""
    result = await db.execute(
        select(RemediationLog, Alert.title.label("alert_name"), Host.hostname.label("host_name"))
        .outerjoin(Alert, RemediationLog.alert_id == Alert.id)
        .outerjoin(Host, RemediationLog.host_id == Host.id)
        .where(RemediationLog.id == remediation_id)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Remediation log not found")
    log, alert_name, host_name = row[0], row[1], row[2]
    data = RemediationLogResponse.model_validate(log).model_dump(mode="json")
    data["alert_name"] = alert_name
    data["host"] = host_name
    return data


@router.post("/{remediation_id}/approve", response_model=RemediationLogResponse)
async def approve_remediation(
    remediation_id: int,
    body: RemediationApproveRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """审批修复操作，将状态从 pending_approval 改为 approved。"""
    result = await db.execute(select(RemediationLog).where(RemediationLog.id == remediation_id))
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Remediation log not found")
    if log.status != "pending_approval":
        raise HTTPException(status_code=400, detail=f"Cannot approve remediation in status: {log.status}")

    log.status = "approved"
    log.approved_by = user.id
    log.approved_at = datetime.now(timezone.utc)
    await log_audit(db, user.id, "approve_remediation", "remediation_log", remediation_id,
                    {"comment": body.comment} if body.comment else None,
                    request.client.host if request.client else None)
    await db.commit()
    await db.refresh(log)
    return log


@router.post("/{remediation_id}/reject", response_model=RemediationLogResponse)
async def reject_remediation(
    remediation_id: int,
    body: RemediationApproveRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """拒绝修复操作，将状态从 pending_approval 改为 rejected。"""
    result = await db.execute(select(RemediationLog).where(RemediationLog.id == remediation_id))
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Remediation log not found")
    if log.status != "pending_approval":
        raise HTTPException(status_code=400, detail=f"Cannot reject remediation in status: {log.status}")

    log.status = "rejected"
    log.blocked_reason = body.comment or "Rejected by operator"
    log.completed_at = datetime.now(timezone.utc)
    await log_audit(db, user.id, "reject_remediation", "remediation_log", remediation_id,
                    {"comment": body.comment} if body.comment else None,
                    request.client.host if request.client else None)
    await db.commit()
    await db.refresh(log)
    return log


# 手动触发修复 — 挂在 alerts 前缀下
trigger_router = APIRouter(prefix="/api/v1/alerts", tags=["remediations"])


@trigger_router.post("/{alert_id}/remediate", response_model=RemediationLogResponse)
async def trigger_remediation(
    alert_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """手动触发对指定告警的修复流程。"""
    # 验证告警存在
    alert_result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert = alert_result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    # 检查是否已有进行中的修复
    existing = await db.execute(
        select(RemediationLog).where(and_(
            RemediationLog.alert_id == alert_id,
            RemediationLog.status.in_(["pending", "diagnosing", "executing", "verifying", "pending_approval"]),
        ))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="A remediation is already in progress for this alert")

    # 创建修复日志记录
    log = RemediationLog(
        alert_id=alert_id,
        host_id=alert.host_id,
        status="pending",
        triggered_by="manual",
    )
    db.add(log)
    await log_audit(db, user.id, "trigger_remediation", "alert", alert_id,
                    None, request.client.host if request.client else None)
    await db.commit()
    await db.refresh(log)

    # 异步启动实际修复流程（通过 remediation agent），不阻塞当前请求
    import asyncio
    from app.remediation.agent import RemediationAgent
    from app.remediation.ai_client import RemediationAIClient
    from app.remediation.command_executor import CommandExecutor
    from app.remediation.models import RemediationAlert
    from app.core.config import settings
    from app.core.database import async_session

    async def _run_remediation(alert_id: int, log_id: int) -> None:
        async with async_session() as bg_db:
            try:
                alert_res = await bg_db.execute(select(Alert).where(Alert.id == alert_id))
                bg_alert = alert_res.scalar_one_or_none()
                if not bg_alert:
                    return
                rem_alert = RemediationAlert(
                    alert_id=bg_alert.id,
                    alert_type=getattr(bg_alert, "metric", "unknown"),
                    severity=bg_alert.severity,
                    host=str(bg_alert.host_id or "unknown"),
                    host_id=bg_alert.host_id,
                    message=bg_alert.title or "",
                )
                ai_client = RemediationAIClient()
                executor = CommandExecutor(dry_run=settings.agent_dry_run)
                agent = RemediationAgent(ai_client=ai_client, executor=executor)
                await agent.handle_alert(rem_alert, bg_db, triggered_by="manual")
            except Exception:
                import logging
                logging.getLogger(__name__).exception(
                    "Background remediation failed for alert %s", alert_id
                )

    asyncio.create_task(_run_remediation(alert_id, log.id))

    return log
