"""
服务器管理路由 (Server Management Router)

功能说明：提供服务器的完整生命周期管理，包括注册、查询、更新和删除
核心职责：
  - 服务器的注册和基础信息管理（hostname、IP、标签、状态）
  - 分页查询服务器列表（L1 视图），支持状态筛选和关键字搜索
  - 服务器详情钻取（L2 视图），展示运行的服务和 Nginx 上游配置
  - 服务器删除时的级联清理（关联的 server_services 和 nginx_upstreams）
  - 与拓扑管理的数据联动和层级结构支持
依赖关系：依赖 Server、ServerService、ServiceGroup、NginxUpstream 数据模型
API端点：GET/POST/PUT/DELETE /api/v1/servers, GET /api/v1/servers/{id}

History: Cycle 8 Day 2 从 topology.py 独立为专用路由，支持多服务器拓扑管理

Author: NightMend Team
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, get_operator_user
from app.models.server import Server
from app.models.server_service import ServerService
from app.models.service_group import ServiceGroup
from app.models.nginx_upstream import NginxUpstream
from app.models.user import User
from app.schemas.topology import (
    ServerCreate, ServerResponse, ServerSummary,
    ServerServiceResponse, ServerServiceDetail,
    NginxUpstreamResponse,
)

router = APIRouter(prefix="/api/v1/servers", tags=["servers"])


@router.get("")
async def list_servers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = None,
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    服务器列表查询 (Server List - L1 View)
    
    提供服务器管理的 L1 层级视图，展示所有服务器的概览信息。
    包含服务器基础信息、运行服务统计和资源使用均值，支持筛选和搜索。
    
    Args:
        page: 页码，从1开始
        page_size: 每页服务器数量，限制1-100台
        status: 可选的状态筛选（如 "active", "inactive", "error"）
        search: 可选的关键字搜索，支持主机名、标签、IP 地址模糊匹配
        db: 数据库会话
        user: 当前认证用户
        
    Returns:
        dict: 包含服务器概览列表、总数和分页信息的响应
        
    Features:
        - 分页查询减少大量服务器时的性能开销
        - 多字段搜索支持运维人员快速定位服务器
        - 聚合统计显示每台服务器的服务数量和资源使用情况
        - 按创建时间倒序，新注册的服务器优先显示
        
    Examples:
        GET /api/v1/servers?status=active&search=web&page=1&page_size=10
    """
    # 构建基础查询和计数查询
    query = select(Server)
    count_query = select(func.count()).select_from(Server)

    # 状态筛选：按服务器运行状态过滤
    if status:
        query = query.where(Server.status == status)
        count_query = count_query.where(Server.status == status)
        
    # 关键字搜索：支持主机名、标签、IP地址的模糊匹配
    if search:
        pattern = f"%{search}%"
        search_condition = (
            Server.hostname.ilike(pattern) | 
            Server.label.ilike(pattern) | 
            Server.ip_address.ilike(pattern)
        )
        query = query.where(search_condition)
        count_query = count_query.where(search_condition)

    # 获取符合条件的服务器总数
    total = (await db.execute(count_query)).scalar() or 0
    
    # 添加分页和排序：按 ID 倒序（新服务器在前）
    query = query.order_by(Server.id.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    servers = result.scalars().all()

    # 为每台服务器构建概览信息
    items = []
    for s in servers:
        # 统计该服务器上运行的服务数量
        svc_count = (await db.execute(
            select(func.count()).select_from(ServerService).where(ServerService.server_id == s.id)
        )).scalar() or 0

        # 计算该服务器上所有服务的 CPU 和内存使用均值
        agg = (await db.execute(
            select(func.avg(ServerService.cpu_percent), func.avg(ServerService.mem_mb))
            .where(ServerService.server_id == s.id)
        )).one()

        # 构建服务器概览对象
        items.append(ServerSummary(
            **ServerResponse.model_validate(s).model_dump(),  # 服务器基础信息
            service_count=svc_count,                          # 运行的服务数量
            cpu_avg=round(agg[0], 2) if agg[0] is not None else None,  # CPU 使用均值
            mem_avg=round(agg[1], 2) if agg[1] is not None else None,  # 内存使用均值(MB)
        ))

    return {"items": [i.model_dump() for i in items], "total": total, "page": page, "page_size": page_size}


@router.get("/{server_id}")
async def get_server(
    server_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    服务器详情查询 (Server Detail - L2 Drill-down View)
    
    提供指定服务器的详细信息，包括基础配置、运行的服务列表和 Nginx 负载均衡配置。
    这是 L2 层级的钻取视图，用于服务器详情页面的完整信息展示。
    
    Args:
        server_id: 服务器ID
        db: 数据库会话
        user: 当前认证用户
        
    Returns:
        dict: 包含服务器详情、服务列表、上游配置的完整响应
        
    Raises:
        HTTPException: 404 - 服务器不存在
        
    Response Structure:
        - server: 服务器基础信息（hostname、IP、状态等）
        - services: 运行在该服务器上的服务列表（含服务组信息）
        - nginx_upstreams: Nginx 负载均衡上游配置列表
        
    Use Cases:
        - 服务器详情页面展示
        - 服务分布分析
        - 负载均衡配置管理
    """
    # 查询服务器基础信息
    server = await db.get(Server, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="服务器不存在")

    # 查询该服务器上运行的所有服务，并关联服务组信息
    svc_stmt = (
        select(ServerService, ServiceGroup.name.label("group_name"))
        .outerjoin(ServiceGroup, ServerService.group_id == ServiceGroup.id)  # 左连接获取服务组名称
        .where(ServerService.server_id == server_id)
    )
    svc_rows = (await db.execute(svc_stmt)).all()
    
    # 构建服务详情列表，包含服务组信息
    services = [
        ServerServiceDetail(
            **ServerServiceResponse.model_validate(row.ServerService).model_dump(),
            group_name=row.group_name,  # 添加服务组名称，便于分类管理
        ).model_dump()
        for row in svc_rows
    ]

    # 查询该服务器上的 Nginx 上游配置
    ups_stmt = select(NginxUpstream).where(NginxUpstream.server_id == server_id)
    ups = (await db.execute(ups_stmt)).scalars().all()
    upstreams = [NginxUpstreamResponse.model_validate(u).model_dump() for u in ups]

    # 返回完整的服务器详情信息
    return {
        "server": ServerResponse.model_validate(server).model_dump(),    # 服务器基础信息
        "services": services,                                            # 运行的服务列表
        "nginx_upstreams": upstreams,                                   # Nginx 负载均衡配置
    }


@router.post("", response_model=ServerResponse, status_code=201)
async def create_server(
    body: ServerCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_operator_user),
):
    """
    注册新服务器 (Register New Server)
    
    向 NightMend 系统注册新的服务器节点，用于后续的服务监控和拓扑管理。
    hostname 必须唯一，作为服务器的主标识符。
    
    Args:
        body: 服务器创建请求，包含 hostname、IP、标签等基础信息
        db: 数据库会话
        user: 当前认证用户
        
    Returns:
        ServerResponse: 创建成功的服务器信息
        
    Raises:
        HTTPException: 400 - hostname 已存在（违反唯一性约束）
        
    Business Rules:
        - hostname 必须在系统中唯一
        - 创建后状态默认为 "active"
        - 支持后续通过 Agent 上报服务和监控数据
        
    Examples:
        POST /api/v1/servers
        {
            "hostname": "web-server-01",
            "ip_address": "192.168.1.10",
            "label": "Web服务器",
            "status": "active"
        }
    """
    # 检查 hostname 的唯一性，防止重复注册
    existing = (await db.execute(
        select(Server).where(Server.hostname == body.hostname)
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail=f"hostname '{body.hostname}' 已存在")

    # 创建新的服务器记录
    server = Server(**body.model_dump())  # 使用请求数据创建服务器对象
    db.add(server)
    await db.commit()       # 提交到数据库
    await db.refresh(server)  # 刷新对象获取数据库生成的字段（如 ID、时间戳）
    return ServerResponse.model_validate(server)


@router.put("/{server_id}", response_model=ServerResponse)
async def update_server(
    server_id: int,
    body: ServerCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_operator_user),
):
    """
    更新服务器信息 (Update Server Information)
    
    修改已注册服务器的基础信息，包括 hostname、IP 地址、标签和状态。
    如果修改 hostname，需要确保新名称的唯一性。
    
    Args:
        server_id: 要更新的服务器ID
        body: 服务器更新数据，包含所有要修改的字段
        db: 数据库会话
        user: 当前认证用户
        
    Returns:
        ServerResponse: 更新后的服务器信息
        
    Raises:
        HTTPException: 404 - 服务器不存在
        HTTPException: 400 - hostname 已被其他服务器占用
        
    Business Rules:
        - hostname 修改时必须保证唯一性
        - 支持所有字段的全量更新
        - 更新不影响已关联的服务和上游配置
        
    Examples:
        PUT /api/v1/servers/123
        {
            "hostname": "web-server-01-new",
            "ip_address": "192.168.1.11",
            "label": "主Web服务器",
            "status": "maintenance"
        }
    """
    # 查询要更新的服务器是否存在
    server = await db.get(Server, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="服务器不存在")

    # 如果要修改 hostname，检查新名称的唯一性
    if body.hostname != server.hostname:
        dup = (await db.execute(
            select(Server).where(Server.hostname == body.hostname)
        )).scalar_one_or_none()
        if dup:
            raise HTTPException(status_code=400, detail=f"hostname '{body.hostname}' 已被占用")

    # 应用所有字段更新
    for field, value in body.model_dump().items():
        setattr(server, field, value)

    await db.commit()       # 提交数据库更新
    await db.refresh(server)  # 刷新对象获取最新数据
    return ServerResponse.model_validate(server)


@router.delete("/{server_id}")
async def delete_server(
    server_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_operator_user),
):
    """
    删除服务器 (Delete Server)
    
    从系统中移除指定服务器及其所有关联数据。
    执行级联删除，清理服务列表和 Nginx 上游配置，确保数据一致性。
    
    Args:
        server_id: 要删除的服务器ID
        db: 数据库会话
        user: 当前认证用户
        
    Returns:
        dict: 删除成功的确认消息，包含服务器 hostname
        
    Raises:
        HTTPException: 404 - 服务器不存在
        
    Cascade Operations:
        1. 删除 ServerService 记录（该服务器上的所有服务）
        2. 删除 NginxUpstream 记录（该服务器的负载均衡配置）
        3. 删除 Server 主记录
        
    Warning:
        - 删除操作是不可逆的硬删除
        - 会影响拓扑图的展示和服务监控
        - 建议先将服务器状态设为 "inactive" 观察一段时间后再删除
        
    Examples:
        DELETE /api/v1/servers/123
    """
    # 查询要删除的服务器是否存在
    server = await db.get(Server, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="服务器不存在")

    # 级联删除：按依赖关系顺序删除关联数据
    # 1. 删除该服务器上的所有服务记录
    await db.execute(delete(ServerService).where(ServerService.server_id == server_id))
    
    # 2. 删除该服务器的 Nginx 上游配置
    await db.execute(delete(NginxUpstream).where(NginxUpstream.server_id == server_id))
    
    # 3. 删除服务器主记录
    await db.delete(server)
    
    await db.commit()  # 提交所有删除操作
    return {"detail": f"服务器 '{server.hostname}' 已删除"}
