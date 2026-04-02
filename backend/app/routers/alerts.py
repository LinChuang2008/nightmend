"""
告警管理路由模块 (Alert Management Router)

功能说明：提供告警生命周期管理接口，支持告警查询、详情获取、确认操作
核心职责：
  - 分页查询告警列表（支持状态、严重级别、主机过滤）
  - 获取单个告警的详细信息
  - 告警确认操作（更新状态和确认信息）
  - 记录告警操作的审计日志
依赖关系：依赖SQLAlchemy、JWT认证、审计服务
API端点：GET /alerts, GET /alerts/{id}, POST /alerts/{id}/ack

Author: NightMend Team
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select, func, and_, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.alert import Alert
from app.models.remediation_log import RemediationLog
from app.models.user import User
from app.schemas.alert import AlertResponse
from app.services.audit import log_audit

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


@router.get("", response_model=dict)
async def list_alerts(
    status: Optional[str] = None,
    severity: Optional[str] = None,
    host_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """
    告警列表查询接口 (Alert List Query)
    
    分页查询告警记录，支持多维度筛选，按触发时间倒序排列。
    
    Args:
        status: 告警状态筛选（firing/acknowledged/resolved）
        severity: 严重级别筛选（critical/high/medium/low）
        host_id: 主机ID筛选
        page: 页码，从1开始
        page_size: 每页数量，限制1-100之间
        db: 数据库会话依赖注入
        _user: 当前登录用户（JWT认证）
    Returns:
        dict: 包含告警列表、总数、分页信息的响应
    流程：
        1. 根据筛选条件构建查询和计数语句
        2. 执行分页查询获取告警记录
        3. 按触发时间倒序排列（最新告警在前）
        4. 返回分页结果和元数据
    """
    # 构建基础查询和计数查询 (Build base query and count query)
    q = select(Alert)
    count_q = select(func.count(Alert.id))

    # 收集所有筛选条件 (Collect all filter conditions)
    filters = []
    if status:
        filters.append(Alert.status == status)  # 按告警状态筛选
    if severity:
        filters.append(Alert.severity == severity)  # 按严重级别筛选
    if host_id:
        filters.append(Alert.host_id == host_id)  # 按主机筛选

    # 应用筛选条件到查询和计数查询 (Apply filters to both query and count query)
    if filters:
        q = q.where(and_(*filters))  # 使用AND连接多个条件
        count_q = count_q.where(and_(*filters))

    total = (await db.execute(count_q)).scalar()
    q = q.order_by(Alert.fired_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(q)
    alerts = result.scalars().all()

    # 批量获取修复状态（子查询：每条告警取最新的修复记录状态）
    alert_ids = [a.id for a in alerts]
    remediation_map: dict = {}
    if alert_ids:
        rem_q = (
            select(RemediationLog.alert_id, RemediationLog.status)
            .where(RemediationLog.alert_id.in_(alert_ids))
            .order_by(RemediationLog.alert_id, RemediationLog.started_at.desc())
        )
        rem_result = await db.execute(rem_q)
        for row in rem_result.all():
            if row.alert_id not in remediation_map:
                remediation_map[row.alert_id] = row.status

    items = []
    for a in alerts:
        data = AlertResponse.model_validate(a).model_dump(mode="json")
        data["remediation_status"] = remediation_map.get(a.id)
        items.append(data)

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{alert_id}", response_model=AlertResponse)
async def get_alert(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """
    单个告警详情查询接口 (Single Alert Detail Query)
    
    根据告警ID获取告警的完整详细信息。
    
    Args:
        alert_id: 告警记录ID
        db: 数据库会话依赖注入
        _user: 当前登录用户（JWT认证）
    Returns:
        AlertResponse: 告警详情响应对象
    Raises:
        HTTPException 404: 告警记录不存在
    流程：
        1. 根据alert_id查询告警记录
        2. 检查告警是否存在
        3. 返回告警完整信息
    """
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


@router.post("/{alert_id}/ack", response_model=AlertResponse)
async def acknowledge_alert(
    alert_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    告警确认操作接口 (Alert Acknowledgment)
    
    将告警状态标记为已确认，记录确认时间和操作人员信息。
    
    Args:
        alert_id: 告警记录ID
        request: HTTP请求对象（用于获取客户端IP）
        db: 数据库会话依赖注入
        user: 当前登录用户（执行确认操作的用户）
    Returns:
        AlertResponse: 更新后的告警详情响应
    Raises:
        HTTPException 404: 告警记录不存在
        HTTPException 400: 告警已经解决，无法确认
    流程：
        1. 根据alert_id查询告警记录
        2. 检查告警状态是否允许确认（非resolved状态）
        3. 更新告警状态为acknowledged
        4. 记录确认时间和操作人ID
        5. 写入审计日志记录操作
    """
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    # 检查告警状态，已解决的告警不能再确认 (Check alert status, resolved alerts cannot be acknowledged)
    if alert.status == "resolved":
        raise HTTPException(status_code=400, detail="Alert already resolved")

    # 更新告警状态和确认信息 (Update alert status and acknowledgment info)
    alert.status = "acknowledged"  # 标记为已确认状态
    alert.acknowledged_at = datetime.now(timezone.utc)  # 记录确认时间
    alert.acknowledged_by = user.id  # 记录确认操作人
    
    # 记录审计日志，包含操作用户和客户端IP (Log audit trail with user and client IP)
    await log_audit(db, user.id, "acknowledge_alert", "alert", alert_id,
                    None, request.client.host if request.client else None)
    await db.commit()
    await db.refresh(alert)
    return alert
