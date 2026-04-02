"""
主机管理路由模块 (Host Management Router)

功能说明：提供主机列表查询、主机详情获取、历史性能指标分析等管理接口
核心职责：
  - 分页查询主机列表（支持状态、分组、关键词过滤）
  - 获取单个主机详细信息和实时指标
  - 查询主机历史性能指标（原始数据和时间聚合）
  - 集成Redis缓存提供实时指标展示
依赖关系：依赖SQLAlchemy、Redis缓存、JWT认证
API端点：GET /hosts, GET /hosts/{id}, GET /hosts/{id}/metrics

Author: NightMend Team
"""
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.redis import get_redis
from app.models.host import Host
from app.models.host_metric import HostMetric
from app.models.user import User
from app.schemas.host import HostWithMetrics, HostResponse, HostMetricResponse, HostUpdate

router = APIRouter(prefix="/api/v1/hosts", tags=["hosts"])


@router.get("")
async def list_hosts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = None,
    group_name: str | None = None,
    search: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    主机列表查询接口 (Host List Query)
    
    分页查询主机列表，支持多维度过滤，集成Redis实时指标展示。
    
    Args:
        page: 页码，从1开始
        page_size: 每页数量，限制1-100之间
        status: 主机状态过滤（online/offline等）
        group_name: 主机分组名称过滤
        search: 主机名关键词搜索（模糊匹配）
        user: 当前登录用户（JWT认证）
        db: 数据库会话依赖注入
    Returns:
        dict: 包含主机列表、总数、分页信息的响应
    流程：
        1. 根据过滤条件构建查询语句和计数语句
        2. 执行分页查询获取主机基础信息
        3. 从Redis获取每台主机的最新性能指标
        4. 合并数据返回完整的主机状态
    """
    # 构建基础查询和计数查询 (Build base query and count query)
    query = select(Host)
    count_query = select(func.count()).select_from(Host)

    # 按主机状态过滤（在线/离线） (Filter by host status - online/offline)
    if status:
        query = query.where(Host.status == status)
        count_query = count_query.where(Host.status == status)
    # 按主机分组过滤 (Filter by host group)
    if group_name:
        query = query.where(Host.group_name == group_name)
        count_query = count_query.where(Host.group_name == group_name)
    # 按主机名模糊搜索 (Fuzzy search by hostname)
    if search:
        query = query.where(Host.hostname.ilike(f"%{search}%"))
        count_query = count_query.where(Host.hostname.ilike(f"%{search}%"))

    # 获取符合条件的总记录数用于分页计算 (Get total count for pagination)
    total = (await db.execute(count_query)).scalar()

    query = query.order_by(Host.id.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    hosts = result.scalars().all()

    # 从Redis获取每台主机的最新性能指标缓存 (Get latest metrics cache from Redis for each host)
    redis = await get_redis()
    items = []
    for h in hosts:
        data = HostWithMetrics.model_validate(h)
        # 尝试获取Agent上报的最新指标数据 (Try to get latest metrics reported by Agent)
        cached = await redis.get(f"metrics:latest:{h.id}")
        if cached:
            data.latest_metrics = json.loads(cached)  # JSON反序列化指标数据
        items.append(data)

    return {"items": [item.model_dump() for item in items], "total": total, "page": page, "page_size": page_size}


@router.get("/{host_id}", response_model=HostWithMetrics)
async def get_host(
    host_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    单个主机详情查询接口 (Single Host Detail Query)
    
    获取指定主机的详细信息和最新性能指标。
    
    Args:
        host_id: 主机记录ID
        user: 当前登录用户（JWT认证）
        db: 数据库会话依赖注入
    Returns:
        HostWithMetrics: 主机详情和最新指标的合并响应
    Raises:
        HTTPException 404: 主机不存在
    流程：
        1. 根据host_id查询主机基础信息
        2. 从Redis获取该主机的最新性能指标缓存
        3. 合并主机信息和指标数据返回
    """
    result = await db.execute(select(Host).where(Host.id == host_id))
    host = result.scalar_one_or_none()
    if not host:
        raise HTTPException(status_code=404, detail="Host not found")

    data = HostWithMetrics.model_validate(host)
    redis = await get_redis()
    cached = await redis.get(f"metrics:latest:{host.id}")
    if cached:
        data.latest_metrics = json.loads(cached)
    return data


@router.get("/{host_id}/metrics", response_model=list[HostMetricResponse])
async def get_host_metrics(
    host_id: int,
    hours: int = Query(1, ge=1, le=720),
    interval: str = Query("raw", pattern="^(raw|5min|1h|1d)$"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    主机历史指标查询接口 (Host Historical Metrics Query)
    
    查询主机在指定时间范围内的性能指标，支持原始数据和时间聚合。
    
    Args:
        host_id: 主机记录ID
        hours: 查询时间范围（小时数，1-720小时）
        interval: 数据聚合间隔（raw/5min/1h/1d）
        user: 当前登录用户（JWT认证）
        db: 数据库会话依赖注入
    Returns:
        list[HostMetricResponse]: 按时间排序的指标数据列表
    流程：
        1. 计算查询的时间起点（当前时间减去指定小时数）
        2. raw模式：返回原始指标数据点（限制1000条）
        3. 聚合模式：使用date_trunc按时间间隔平均值聚合
        4. 按时间升序排列返回指标数据
    """
    from datetime import datetime, timezone, timedelta

    # 计算查询起始时间点 (Calculate query start time)
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    if interval == "raw":
        # 返回原始数据点，用于短时间范围的详细分析 (Return raw data points for detailed short-term analysis)
        query = (
            select(HostMetric)
            .where(HostMetric.host_id == host_id, HostMetric.recorded_at >= since)
            .order_by(HostMetric.recorded_at.asc())  # 按时间升序排列
            .limit(1000)  # 限制返回数量防止内存溢出
        )
        result = await db.execute(query)
        rows = result.scalars().all()
        # 处理计数器重置导致的负值（计数器溢出/重启场景）
        for row in rows:
            if row.net_send_rate_kb is not None and row.net_send_rate_kb < 0:
                row.net_send_rate_kb = 0.0
            if row.net_recv_rate_kb is not None and row.net_recv_rate_kb < 0:
                row.net_recv_rate_kb = 0.0
        return rows

    # 使用PostgreSQL的date_trunc函数聚合数据 (Use PostgreSQL date_trunc for data aggregation)
    # 安全说明：trunc_unit 来自固定白名单映射，非用户输入，无 SQL 注入风险
    interval_trunc_map = {"5min": "minute", "1h": "hour", "1d": "day"}
    trunc_unit = interval_trunc_map[interval]

    from sqlalchemy import text
    sql = text(f"""
        SELECT
            0 as id, :host_id as host_id,
            avg(cpu_percent) as cpu_percent,
            avg(cpu_load_1) as cpu_load_1,
            avg(cpu_load_5) as cpu_load_5,
            avg(cpu_load_15) as cpu_load_15,
            avg(memory_used_mb)::int as memory_used_mb,
            avg(memory_percent) as memory_percent,
            avg(disk_used_mb)::int as disk_used_mb,
            avg(disk_total_mb)::int as disk_total_mb,
            avg(disk_percent) as disk_percent,
            avg(net_bytes_sent)::bigint as net_bytes_sent,
            avg(net_bytes_recv)::bigint as net_bytes_recv,
            greatest(0, avg(net_send_rate_kb)) as net_send_rate_kb,
            greatest(0, avg(net_recv_rate_kb)) as net_recv_rate_kb,
            avg(net_packet_loss_rate) as net_packet_loss_rate,
            avg(agent_cpu_percent) as agent_cpu_percent,
            avg(agent_memory_rss_mb) as agent_memory_rss_mb,
            avg(agent_thread_count)::int as agent_thread_count,
            avg(agent_uptime_seconds)::int as agent_uptime_seconds,
            avg(agent_open_files)::int as agent_open_files,
            date_trunc('{trunc_unit}', recorded_at) as recorded_at
        FROM host_metrics
        WHERE host_id = :host_id AND recorded_at >= :since
        GROUP BY date_trunc('{trunc_unit}', recorded_at)
        ORDER BY recorded_at ASC
        LIMIT 500
    """)
    result = await db.execute(sql, {"host_id": host_id, "since": since})
    rows = result.mappings().all()
    return [HostMetricResponse(**dict(r)) for r in rows]


@router.patch("/{host_id}", response_model=HostResponse)
async def update_host(
    host_id: int,
    update_data: HostUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    更新主机信息接口 (Update Host)

    更新主机的可编辑字段（如显示名称）。

    Args:
        host_id: 主机记录ID
        update_data: 更新数据（目前仅支持 display_name）
        user: 当前登录用户（JWT认证）
        db: 数据库会话依赖注入
    Returns:
        HostResponse: 更新后的主机信息
    Raises:
        HTTPException 404: 主机不存在
    """
    result = await db.execute(select(Host).where(Host.id == host_id))
    host = result.scalar_one_or_none()
    if not host:
        raise HTTPException(status_code=404, detail="Host not found")

    # 更新显示名称
    if update_data.display_name is not None:
        host.display_name = update_data.display_name

    await db.commit()
    await db.refresh(host)
    return host
