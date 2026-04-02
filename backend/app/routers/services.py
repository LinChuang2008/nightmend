"""
服务监控路由模块 (Service Monitoring Router)

功能说明：提供服务健康监控和可用性分析的核心接口
核心职责：
  - 服务列表查询（支持状态、分类、主机筛选）
  - 服务详情获取（包含可用率计算）
  - 健康检查历史记录查询
  - 服务可用率统计分析（24小时/自定义时间范围）
  - 支持三层服务分类（middleware/business/infrastructure）
依赖关系：依赖SQLAlchemy、JWT认证、服务健康检查数据
API端点：GET /services, GET /services/{id}, GET /services/{id}/checks

Author: NightMend Team
"""
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.service import Service, ServiceCheck
from app.models.host import Host
from app.models.user import User
from app.schemas.service import ServiceResponse, ServiceCheckResponse

router = APIRouter(prefix="/api/v1/services", tags=["services"])


async def _calc_uptime(db: AsyncSession, service_id: int, hours: int = 24) -> float | None:
    """计算指定服务在最近 N 小时内的可用率（百分比）。"""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    total = (await db.execute(
        select(func.count()).select_from(ServiceCheck)
        .where(ServiceCheck.service_id == service_id, ServiceCheck.checked_at >= since)
    )).scalar()
    if not total:
        return None
    up = (await db.execute(
        select(func.count()).select_from(ServiceCheck)
        .where(ServiceCheck.service_id == service_id, ServiceCheck.checked_at >= since, ServiceCheck.status == "up")
    )).scalar()
    return round(up / total * 100, 2)


@router.get("")
async def list_services(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = None,
    category: str | None = None,
    host_id: int | None = None,
    group_by_host: bool = False,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    分页查询服务列表，支持按状态、分类、主机筛选，附带 24h 可用率。
    group_by_host=true 时返回按主机分组的结构。
    """
    query = select(Service).where(Service.is_active == True)
    count_query = select(func.count()).select_from(Service).where(Service.is_active == True)

    if status:
        query = query.where(Service.status == status)
        count_query = count_query.where(Service.status == status)
    if category:
        query = query.where(Service.category == category)
        count_query = count_query.where(Service.category == category)
    if host_id:
        query = query.where(Service.host_id == host_id)
        count_query = count_query.where(Service.host_id == host_id)

    total = (await db.execute(count_query)).scalar()
    query = query.order_by(Service.host_id, Service.category, Service.name).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    services = result.scalars().all()

    # 查询主机名映射
    host_ids = list(set(s.host_id for s in services if s.host_id))
    host_map = {}
    if host_ids:
        host_result = await db.execute(
            select(Host.id, Host.hostname, Host.display_name, Host.ip_address, Host.status)
            .where(Host.id.in_(host_ids))
        )
        for hid, hname, hdisplay, hip, hstatus in host_result.all():
            host_map[hid] = {
                "id": hid,
                "hostname": hdisplay or hname,
                "ip": hip,
                "status": hstatus,
            }

    items = []
    for s in services:
        data = ServiceResponse.model_validate(s)
        data.uptime_percent = await _calc_uptime(db, s.id)
        d = data.model_dump()
        # 附加主机信息
        d["host_info"] = host_map.get(s.host_id) if s.host_id else None
        items.append(d)

    # 全局统计（不受筛选影响）
    all_stats_result = await db.execute(
        select(Service.category, Service.status, func.count())
        .where(Service.is_active == True)
        .group_by(Service.category, Service.status)
    )
    stats_map: dict = {"total": 0, "middleware": 0, "business": 0, "infrastructure": 0, "healthy": 0, "unhealthy": 0}
    for cat, st, cnt in all_stats_result.all():
        stats_map["total"] += cnt
        if cat in stats_map:
            stats_map[cat] += cnt
        if st in ("up", "healthy"):
            stats_map["healthy"] += cnt
        elif st in ("down", "unhealthy"):
            stats_map["unhealthy"] += cnt

    resp = {"items": items, "total": total, "page": page, "page_size": page_size, "stats": stats_map}

    # group_by_host 模式：额外返回按主机分组的结构
    if group_by_host:
        groups = {}
        for item in items:
            hid = item.get("host_id") or 0
            if hid not in groups:
                hi = item.get("host_info") or {}
                groups[hid] = {
                    "host_id": hid,
                    "hostname": hi.get("hostname", "未关联主机"),
                    "ip": hi.get("ip", ""),
                    "host_status": hi.get("status", "unknown"),
                    "services": [],
                }
            groups[hid]["services"].append(item)
        resp["host_groups"] = list(groups.values())

    return resp


@router.get("/{service_id}", response_model=ServiceResponse)
async def get_service(
    service_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取单个服务详情。"""
    result = await db.execute(select(Service).where(Service.id == service_id))
    service = result.scalar_one_or_none()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    data = ServiceResponse.model_validate(service)
    data.uptime_percent = await _calc_uptime(db, service.id)
    return data


@router.get("/{service_id}/checks", response_model=list[ServiceCheckResponse])
async def get_service_checks(
    service_id: int,
    hours: int = Query(24, ge=1, le=720),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查询服务健康检查历史记录。"""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    result = await db.execute(
        select(ServiceCheck)
        .where(ServiceCheck.service_id == service_id, ServiceCheck.checked_at >= since)
        .order_by(ServiceCheck.checked_at.desc())
        .limit(500)
    )
    return result.scalars().all()
