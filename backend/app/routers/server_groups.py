"""
服务组管理路由 (Service Group Management Router)

功能说明：提供服务组的完整生命周期管理和服务器关联管理
核心职责：
  - 服务组的创建、查询、更新和删除（基础 CRUD 操作）
  - 服务组详情查看，包含关联的服务器列表展示
  - 服务器与服务组的关联管理（添加/移除服务器）
  - 支持按类别筛选和分页查询，便于大量服务组的管理
  - 服务组统计信息（关联的服务器数量计算）
依赖关系：依赖 ServiceGroup、ServerService、Server 数据模型
API端点：GET/POST/PUT/DELETE /api/v1/server-groups, POST/DELETE /api/v1/server-groups/{id}/servers

History: Cycle 8 Day 2 从 topology.py 独立为专用路由，支持服务分类和拓扑管理

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
from app.models.user import User
from app.schemas.topology import (
    ServiceGroupCreate, ServiceGroupResponse, ServiceGroupDetail,
    ServerResponse,
    ServerServiceCreate, ServerServiceResponse,
)

router = APIRouter(prefix="/api/v1/server-groups", tags=["server-groups"])


@router.get("")
async def list_service_groups(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    category: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    服务组列表查询 (Service Groups List)
    
    分页查询系统中的所有服务组，支持按类别筛选。
    为每个服务组统计关联的服务器数量，便于管理员了解服务分布情况。
    
    Args:
        page: 页码，从1开始
        page_size: 每页服务组数量，限制1-200个
        category: 可选的类别筛选（如 "web", "database", "cache" 等）
        db: 数据库会话
        user: 当前认证用户
        
    Returns:
        dict: 包含服务组列表、总数和分页信息的响应
        
    Features:
        - 支持按服务类别进行筛选，便于分类管理
        - 实时统计每个服务组包含的服务器数量
        - 分页查询减少大量服务组时的性能开销
        - 按 ID 升序排列，保证展示顺序稳定
        
    Use Cases:
        - 服务组管理页面的列表展示
        - 服务分类统计和分析
        - 拓扑图的服务组筛选
        
    Examples:
        GET /api/v1/server-groups?category=web&page=1&page_size=20
    """
    # 构建基础查询和计数查询
    query = select(ServiceGroup)
    count_query = select(func.count()).select_from(ServiceGroup)

    # 按类别筛选：支持按服务类型过滤
    if category:
        query = query.where(ServiceGroup.category == category)
        count_query = count_query.where(ServiceGroup.category == category)

    # 获取符合条件的服务组总数
    count = (await db.execute(count_query)).scalar() or 0
    
    # 添加分页和排序：按 ID 升序排列
    stmt = query.order_by(ServiceGroup.id).offset((page - 1) * page_size).limit(page_size)
    groups = (await db.execute(stmt)).scalars().all()

    # 为每个服务组构建详细信息，包含服务器数量统计
    items = []
    for g in groups:
        # 统计该服务组关联的不同服务器数量
        # 使用 DISTINCT 避免同一台服务器运行多个该组服务时的重复计数
        server_count = (await db.execute(
            select(func.count(func.distinct(ServerService.server_id)))
            .where(ServerService.group_id == g.id)
        )).scalar() or 0
        
        # 构建服务组响应对象并添加服务器数量
        d = ServiceGroupResponse.model_validate(g).model_dump()
        d["server_count"] = server_count  # 关联的服务器数量
        items.append(d)

    return {"items": items, "total": count, "page": page, "page_size": page_size}


@router.get("/{group_id}")
async def get_service_group(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    服务组详情查询 (Service Group Detail)
    
    获取指定服务组的完整信息，包括基础属性和关联的所有服务器列表。
    用于服务组详情页面的展示和服务器分布分析。
    
    Args:
        group_id: 服务组ID
        db: 数据库会话
        user: 当前认证用户
        
    Returns:
        ServiceGroupDetail: 服务组详情，包含关联的服务器列表
        
    Raises:
        HTTPException: 404 - 服务组不存在
        
    Features:
        - 展示服务组的基础信息（名称、类别、描述等）
        - 列出运行该服务组服务的所有服务器
        - 使用 DISTINCT 确保同一台服务器只出现一次
        - 便于分析服务的部署分布和资源配置
        
    Use Cases:
        - 服务组详情页面展示
        - 服务部署分布分析
        - 服务器与服务组关联管理
        
    Examples:
        GET /api/v1/server-groups/123
    """
    # 查询服务组基础信息
    group = await db.get(ServiceGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="服务组不存在")

    # 查询该服务组关联的所有服务器
    # 通过 ServerService 中间表建立关联，使用 DISTINCT 避免重复
    stmt = (
        select(Server)
        .join(ServerService, ServerService.server_id == Server.id)  # 内连接获取运行该服务的服务器
        .where(ServerService.group_id == group_id)
        .distinct()  # 去重：同一台服务器可能运行该组的多个服务实例
    )
    servers = (await db.execute(stmt)).scalars().all()

    # 构建完整的服务组详情响应
    return ServiceGroupDetail(
        **ServiceGroupResponse.model_validate(group).model_dump(),  # 服务组基础信息
        servers=[ServerResponse.model_validate(s) for s in servers],  # 关联的服务器列表
    )


@router.post("", response_model=ServiceGroupResponse, status_code=201)
async def create_service_group(
    body: ServiceGroupCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_operator_user),
):
    """
    创建服务组 (Create Service Group)
    
    创建新的服务组用于对相同类型的服务进行分类管理。
    服务组名称必须唯一，便于后续的服务归类和拓扑展示。
    
    Args:
        body: 服务组创建请求，包含名称、类别、描述等信息
        db: 数据库会话
        user: 当前认证用户
        
    Returns:
        ServiceGroupResponse: 创建成功的服务组信息
        
    Raises:
        HTTPException: 400 - 服务组名称已存在
        
    Business Rules:
        - 服务组名称必须在系统中唯一
        - 支持多种服务类别（web、database、cache、mq 等）
        - 创建后可以通过关联管理接口添加服务器
        
    Examples:
        POST /api/v1/server-groups
        {
            "name": "Web服务器组",
            "category": "web",
            "description": "前端Web服务集群",
            "color": "#2196F3"
        }
    """
    # 检查服务组名称的唯一性
    existing = (await db.execute(
        select(ServiceGroup).where(ServiceGroup.name == body.name)
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail=f"服务组 '{body.name}' 已存在")

    # 创建新的服务组记录
    group = ServiceGroup(**body.model_dump())
    db.add(group)
    await db.commit()       # 提交到数据库
    await db.refresh(group)  # 刷新对象获取数据库生成的字段
    return ServiceGroupResponse.model_validate(group)


@router.put("/{group_id}", response_model=ServiceGroupResponse)
async def update_service_group(
    group_id: int,
    body: ServiceGroupCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_operator_user),
):
    """
    更新服务组信息 (Update Service Group)
    
    修改已存在服务组的基础信息，包括名称、类别、描述和颜色等。
    如果修改名称，需要确保新名称的唯一性。
    
    Args:
        group_id: 要更新的服务组ID
        body: 服务组更新数据，包含所有要修改的字段
        db: 数据库会话
        user: 当前认证用户
        
    Returns:
        ServiceGroupResponse: 更新后的服务组信息
        
    Raises:
        HTTPException: 404 - 服务组不存在
        HTTPException: 400 - 新名称已被其他服务组占用
        
    Business Rules:
        - 名称修改时必须保证唯一性
        - 支持所有字段的全量更新
        - 更新不影响已关联的服务器和服务
        
    Examples:
        PUT /api/v1/server-groups/123
        {
            "name": "Web服务器组-更新",
            "category": "web",
            "description": "更新后的描述",
            "color": "#FF5722"
        }
    """
    # 查询要更新的服务组是否存在
    group = await db.get(ServiceGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="服务组不存在")

    # 如果要修改名称，检查新名称的唯一性
    if body.name != group.name:
        dup = (await db.execute(
            select(ServiceGroup).where(ServiceGroup.name == body.name)
        )).scalar_one_or_none()
        if dup:
            raise HTTPException(status_code=400, detail=f"服务组 '{body.name}' 已被占用")

    # 应用所有字段更新
    for field, value in body.model_dump().items():
        setattr(group, field, value)

    await db.commit()       # 提交数据库更新
    await db.refresh(group)  # 刷新对象获取最新数据
    return ServiceGroupResponse.model_validate(group)


@router.delete("/{group_id}")
async def delete_service_group(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_operator_user),
):
    """
    删除服务组 (Delete Service Group)
    
    从系统中移除指定服务组及其所有关联的服务器-服务记录。
    执行级联删除，确保数据一致性。
    
    Args:
        group_id: 要删除的服务组ID
        db: 数据库会话
        user: 当前认证用户
        
    Returns:
        dict: 删除成功的确认消息，包含服务组名称
        
    Raises:
        HTTPException: 404 - 服务组不存在
        
    Cascade Operations:
        1. 删除 ServerService 记录（该服务组关联的所有服务器-服务关系）
        2. 删除 ServiceGroup 主记录
        
    Warning:
        - 删除操作是不可逆的硬删除
        - 会影响拓扑图的服务分类展示
        - 关联的服务器不会被删除，只是失去服务组归属
        - 建议先检查是否有重要服务正在使用该组
        
    Examples:
        DELETE /api/v1/server-groups/123
    """
    # 查询要删除的服务组是否存在
    group = await db.get(ServiceGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="服务组不存在")

    # 级联删除：按依赖关系顺序删除关联数据
    # 1. 删除该服务组的所有服务器-服务关联记录
    await db.execute(delete(ServerService).where(ServerService.group_id == group_id))
    
    # 2. 删除服务组主记录
    await db.delete(group)
    
    await db.commit()  # 提交所有删除操作
    return {"detail": f"服务组 '{group.name}' 已删除"}


# ==================== Server-Service 关联管理 (Server-Service Association Management) ====================

@router.post("/{group_id}/servers", response_model=ServerServiceResponse, status_code=201)
async def add_server_to_group(
    group_id: int,
    body: ServerServiceCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_operator_user),
):
    """
    将服务器添加到服务组 (Add Server to Service Group)
    
    在指定服务器和服务组之间建立关联，创建一个服务实例记录。
    这表示在该服务器上运行了属于指定服务组的服务。
    
    Args:
        group_id: 目标服务组ID（从URL路径获取）
        body: 服务器-服务关联创建请求，包含服务器ID、端口、进程等信息
        db: 数据库会话
        user: 当前认证用户
        
    Returns:
        ServerServiceResponse: 创建成功的服务器-服务关联记录
        
    Raises:
        HTTPException: 404 - 服务组不存在
        HTTPException: 404 - 服务器不存在
        
    Business Logic:
        - 强制使用路径中的 group_id，确保关联的正确性
        - 记录服务的运行状态信息（端口、进程ID、资源使用等）
        - 支持同一台服务器运行多个不同服务组的服务
        
    Examples:
        POST /api/v1/server-groups/123/servers
        {
            "server_id": 456,
            "port": 8080,
            "pid": 12345,
            "status": "running",
            "cpu_percent": 15.5,
            "mem_mb": 512
        }
    """
    # 验证服务组是否存在
    group = await db.get(ServiceGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="服务组不存在")

    # 验证服务器是否存在
    server = await db.get(Server, body.server_id)
    if not server:
        raise HTTPException(status_code=404, detail="服务器不存在")

    # 创建服务器-服务关联记录
    # 强制使用路径中的 group_id，防止请求体中的 group_id 不一致
    assoc = ServerService(
        server_id=body.server_id,
        group_id=group_id,              # 使用路径参数，确保一致性
        port=body.port,                 # 服务监听端口
        pid=body.pid,                   # 服务进程ID
        status=body.status,             # 服务运行状态
        cpu_percent=body.cpu_percent,   # CPU使用率
        mem_mb=body.mem_mb,             # 内存使用量(MB)
    )
    db.add(assoc)
    await db.commit()
    await db.refresh(assoc)  # 刷新对象获取数据库生成的字段
    return ServerServiceResponse.model_validate(assoc)


@router.delete("/{group_id}/servers/{server_id}")
async def remove_server_from_group(
    group_id: int,
    server_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_operator_user),
):
    """
    从服务组移除服务器 (Remove Server from Service Group)
    
    删除指定服务器与服务组之间的关联关系。
    如果该服务器在该服务组中有多个服务实例，会全部移除。
    
    Args:
        group_id: 服务组ID（从URL路径获取）
        server_id: 要移除的服务器ID（从URL路径获取）
        db: 数据库会话
        user: 当前认证用户
        
    Returns:
        dict: 移除成功的确认消息
        
    Raises:
        HTTPException: 404 - 指定的服务器-服务组关联不存在
        
    Business Logic:
        - 删除所有匹配的 ServerService 关联记录
        - 支持批量删除（同一服务器在同一服务组的多个服务实例）
        - 不删除服务器和服务组本身，只删除关联关系
        
    Use Cases:
        - 服务迁移：将服务从一台服务器迁移到另一台
        - 服务下线：停止某台服务器上的特定服务
        - 拓扑调整：重新规划服务分布
        
    Examples:
        DELETE /api/v1/server-groups/123/servers/456
    """
    # 查询指定服务器和服务组之间的所有关联记录
    result = await db.execute(
        select(ServerService).where(
            ServerService.group_id == group_id,
            ServerService.server_id == server_id,
        )
    )
    assocs = result.scalars().all()
    
    # 如果没有找到关联记录，返回 404 错误
    if not assocs:
        raise HTTPException(status_code=404, detail="关联不存在")

    # 删除所有找到的关联记录
    # 可能有多条记录：同一台服务器运行同一服务组的多个服务实例
    for a in assocs:
        await db.delete(a)
        
    await db.commit()  # 提交删除操作
    return {"detail": "已移除"}
