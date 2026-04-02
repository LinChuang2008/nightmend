"""
服务拓扑路由模块 (Service Topology Router)

功能说明：提供服务依赖拓扑图的数据管理和智能分析功能
核心职责：
  - 服务拓扑图数据查询（支持力导向和分层布局）
  - 服务依赖关系CRUD管理
  - AI智能依赖关系推荐
  - 自定义布局存储和恢复
  - 多服务器拓扑管理（Cycle 8新增）
  - 服务分组和Nginx上游配置管理
  - 支持服务分类的层级展示
依赖关系：依赖SQLAlchemy、AI引擎、JWT认证
API端点：GET /topology, POST /dependencies, GET /recommend-dependencies, POST /layout, 多服务器相关API

Author: NightMend Team
"""
import re
import json
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, text, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.config import settings
from app.models.service import Service
from app.models.host import Host
from app.models.service_dependency import ServiceDependency
from app.models.topology_layout import TopologyLayout
from app.models.user import User
from app.models.server import Server
from app.models.service_group import ServiceGroup
from app.models.server_service import ServerService
from app.models.nginx_upstream import NginxUpstream
from app.schemas.topology import (
    ServerCreate, ServerResponse, ServerSummary,
    ServiceGroupCreate, ServiceGroupResponse, ServiceGroupDetail,
    ServerServiceCreate, ServerServiceResponse, ServerServiceDetail,
    NginxUpstreamCreate, NginxUpstreamResponse, TopologyEdge,
)

router = APIRouter(prefix="/api/v1/topology", tags=["topology"])


# ==================== 请求/响应模型 ====================

class DependencyCreate(BaseModel):
    """创建依赖关系的请求体"""
    source_service_id: int
    target_service_id: int
    dependency_type: str = "calls"
    description: Optional[str] = None


class DependencyResponse(BaseModel):
    """依赖关系响应"""
    id: int
    source_service_id: int
    target_service_id: int
    dependency_type: str
    description: Optional[str] = None


class LayoutSaveRequest(BaseModel):
    """保存布局请求体"""
    positions: Dict[str, Dict[str, float]]  # {"node_id": {"x": 100, "y": 200}}
    name: str = "default"


class AISuggestRequest(BaseModel):
    """AI 推荐请求体"""
    services: Optional[List[Dict[str, Any]]] = None  # 可选，不传则自动获取


# ==================== 分类辅助 ====================

def _classify_service(name: str) -> str:
    """根据服务名称推断分组类别"""
    name_lower = name.lower()
    if any(k in name_lower for k in ("postgres", "mysql", "mariadb", "mongo", "oracle")):
        return "database"
    if any(k in name_lower for k in ("redis", "memcache")):
        return "cache"
    if any(k in name_lower for k in ("rabbitmq", "kafka", "mq")):
        return "mq"
    if any(k in name_lower for k in ("clickhouse",)):
        return "olap"
    if any(k in name_lower for k in ("nacos",)):
        return "registry"
    if any(k in name_lower for k in ("nginx", "frontend", "web")):
        return "web"
    if any(k in name_lower for k in ("backend", "api")):
        return "api"
    return "app"


def _infer_edges(services: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    自动推断有意义的服务依赖关系。
    仅作为无自定义依赖时的默认回退。
    """
    edges: List[Dict[str, Any]] = []
    seen = set()

    def add_edge(src_id: int, tgt_id: int, etype: str, desc: str):
        key = (src_id, tgt_id, etype)
        if key not in seen:
            seen.add(key)
            edges.append({"source": src_id, "target": tgt_id, "type": etype, "description": desc})

    api_pattern = re.compile(r"backend|api", re.I)
    fe_pattern = re.compile(r"frontend", re.I)
    nacos_pattern = re.compile(r"nacos", re.I)
    mq_pattern = re.compile(r"rabbitmq|\bmq\b", re.I)
    db_cache_pattern = re.compile(r"postgres|redis|mysql|mariadb|mongo|oracle", re.I)
    app_pattern = re.compile(r"service|app|admin|job", re.I)
    infra_pattern = re.compile(r"postgres|redis|mysql|rabbitmq|mariadb|mongo|oracle|clickhouse|memcache|nacos", re.I)

    api_services = [s for s in services if api_pattern.search(s["name"])]
    fe_services = [s for s in services if fe_pattern.search(s["name"])]
    nacos_services = [s for s in services if nacos_pattern.search(s["name"])]
    mq_services = [s for s in services if mq_pattern.search(s["name"])]
    biz_services = [s for s in services if
                    (api_pattern.search(s["name"]) or app_pattern.search(s["name"]))
                    and not infra_pattern.search(s["name"])
                    and not fe_pattern.search(s["name"])
                    and not nacos_pattern.search(s["name"])]

    def get_prefix(name: str) -> str:
        parts = re.split(r'[-_]', name.lower())
        return parts[0] if parts else ""

    # frontend → 同前缀 backend
    for fe in fe_services:
        fe_prefix = get_prefix(fe["name"])
        for api in api_services:
            if get_prefix(api["name"]) == fe_prefix:
                add_edge(fe["id"], api["id"], "calls", "API 调用")

    # backend → 同前缀数据库/缓存
    for api in api_services:
        api_prefix = get_prefix(api["name"])
        for s in services:
            if db_cache_pattern.search(s["name"]) and get_prefix(s["name"]) == api_prefix:
                add_edge(api["id"], s["id"], "depends_on", "数据依赖")

    # 业务服务 → nacos
    if nacos_services:
        nacos_main = nacos_services[0]
        for biz in biz_services:
            add_edge(biz["id"], nacos_main["id"], "depends_on", "服务注册")

    # 业务服务 → rabbitmq
    if mq_services:
        mq_main = mq_services[0]
        for biz in biz_services:
            if not mq_pattern.search(biz["name"]):
                add_edge(biz["id"], mq_main["id"], "depends_on", "消息队列")

    return edges


# ==================== 路由 ====================

@router.get("")
async def get_topology(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    获取服务拓扑图数据。
    返回节点、边、用户保存的布局。
    """
    # 查询所有活跃服务
    stmt = (
        select(Service.id, Service.name, Service.type, Service.status,
               Service.host_id, Host.hostname)
        .outerjoin(Host, Service.host_id == Host.id)
        .where(Service.is_active == True)
    )
    result = await db.execute(stmt)
    rows = result.all()

    # 去重（同名服务只保留一个）
    seen_names: Dict[str, int] = {}
    nodes = []
    services_data = []

    for row in rows:
        svc_id, name, svc_type, status, host_id, hostname = row
        base_name = re.sub(r'\s*\(:\d+\)$', '', name).strip()
        if base_name in seen_names:
            continue
        seen_names[base_name] = svc_id

        node = {
            "id": svc_id,
            "name": name,
            "type": svc_type,
            "status": status or "unknown",
            "host": hostname or "",
            "host_id": host_id,
            "group": _classify_service(name),
        }
        nodes.append(node)
        services_data.append({"id": svc_id, "name": name, "host_id": host_id})

    # 查询用户自定义依赖
    dep_result = await db.execute(select(ServiceDependency))
    deps = dep_result.scalars().all()

    if deps:
        edges = [
            {"source": d.source_service_id, "target": d.target_service_id,
             "type": d.dependency_type, "description": d.description or "",
             "id": d.id, "manual": True}
            for d in deps
        ]
    else:
        edges = _infer_edges(services_data)
        for e in edges:
            e["manual"] = False

    # 加载用户保存的布局
    layout_result = await db.execute(
        select(TopologyLayout)
        .where(TopologyLayout.user_id == user.id, TopologyLayout.name == "default")
    )
    layout = layout_result.scalar_one_or_none()
    saved_positions = layout.positions if layout else None

    # 主机列表
    hosts_map = {}
    for node in nodes:
        hid = node.get("host_id")
        if hid and hid not in hosts_map:
            hosts_map[hid] = node["host"]
    hosts = [{"id": hid, "name": hname} for hid, hname in hosts_map.items()]

    return {
        "nodes": nodes,
        "edges": edges,
        "hosts": hosts,
        "saved_positions": saved_positions,
        "has_custom_deps": bool(deps),
    }


# ==================== 布局保存/加载 ====================

@router.post("/layout")
async def save_layout(
    body: LayoutSaveRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """保存用户自定义布局（节点位置）"""
    # upsert
    existing = await db.execute(
        select(TopologyLayout)
        .where(TopologyLayout.user_id == user.id, TopologyLayout.name == body.name)
    )
    layout = existing.scalar_one_or_none()

    if layout:
        layout.positions = body.positions
    else:
        layout = TopologyLayout(
            user_id=user.id,
            name=body.name,
            positions=body.positions,
        )
        db.add(layout)

    await db.commit()
    return {"detail": "布局已保存", "positions": body.positions}


@router.delete("/layout")
async def reset_layout(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """重置用户自定义布局"""
    existing = await db.execute(
        select(TopologyLayout)
        .where(TopologyLayout.user_id == user.id, TopologyLayout.name == "default")
    )
    layout = existing.scalar_one_or_none()
    if layout:
        await db.delete(layout)
        await db.commit()
    return {"detail": "布局已重置"}


# ==================== 依赖管理 ====================

@router.post("/dependencies")
async def create_dependency(
    body: DependencyCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """手动添加服务依赖关系"""
    for sid in (body.source_service_id, body.target_service_id):
        svc = await db.get(Service, sid)
        if not svc:
            raise HTTPException(status_code=404, detail=f"服务 {sid} 不存在")

    # 检查重复
    existing = await db.execute(
        select(ServiceDependency).where(
            ServiceDependency.source_service_id == body.source_service_id,
            ServiceDependency.target_service_id == body.target_service_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="依赖关系已存在")

    dep = ServiceDependency(
        source_service_id=body.source_service_id,
        target_service_id=body.target_service_id,
        dependency_type=body.dependency_type,
        description=body.description,
    )
    db.add(dep)
    await db.commit()
    await db.refresh(dep)
    return DependencyResponse(
        id=dep.id,
        source_service_id=dep.source_service_id,
        target_service_id=dep.target_service_id,
        dependency_type=dep.dependency_type,
        description=dep.description,
    )


@router.delete("/dependencies/{dep_id}")
async def delete_dependency(
    dep_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """删除指定的服务依赖关系"""
    dep = await db.get(ServiceDependency, dep_id)
    if not dep:
        raise HTTPException(status_code=404, detail="依赖关系不存在")
    await db.delete(dep)
    await db.commit()
    return {"detail": "已删除"}


@router.delete("/dependencies")
async def clear_all_dependencies(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """清空所有自定义依赖（回退到自动推断）"""
    try:
        await db.execute(text("DELETE FROM service_dependencies"))
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return {"detail": "所有自定义依赖已清空"}


# ==================== AI 智能推荐 ====================

@router.post("/ai-suggest")
async def ai_suggest_topology(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    AI 分析服务列表，智能推荐依赖关系。
    使用 DeepSeek 分析服务名称、端口、类型，推荐合理的依赖关系。
    """
    import httpx

    # 获取所有服务
    stmt = (
        select(Service.id, Service.name, Service.type, Service.status, Host.hostname)
        .outerjoin(Host, Service.host_id == Host.id)
        .where(Service.is_active == True)
    )
    result = await db.execute(stmt)
    rows = result.all()

    # 去重
    seen = {}
    services_info = []
    for svc_id, name, svc_type, status, hostname in rows:
        base_name = re.sub(r'\s*\(:\d+\)$', '', name).strip()
        if base_name in seen:
            continue
        seen[base_name] = svc_id
        services_info.append({"id": svc_id, "name": name, "type": svc_type, "host": hostname or ""})

    # 查询已有依赖
    dep_result = await db.execute(select(ServiceDependency))
    existing_deps = [
        {"source": d.source_service_id, "target": d.target_service_id, "type": d.dependency_type}
        for d in dep_result.scalars().all()
    ]

    # 构造 AI Prompt
    services_text = json.dumps(services_info, ensure_ascii=False, indent=2)
    existing_text = json.dumps(existing_deps, ensure_ascii=False, indent=2) if existing_deps else "（暂无）"

    prompt = f"""你是一个资深运维架构师。根据以下服务器上运行的服务列表，分析它们之间的依赖关系。

## 当前服务列表
{services_text}

## 已有依赖关系
{existing_text}

## 要求
1. 根据服务名称、端口号、类型，推断服务间的合理依赖关系
2. 依赖类型只能是: "calls"（API调用）或 "depends_on"（基础设施依赖）
3. 不要重复已有的依赖关系
4. 每条依赖都要有简短的中文描述说明为什么存在这个依赖
5. 只返回有较高确信度的依赖关系，不确定的不要返回

## 输出格式（严格 JSON 数组）
```json
[
  {{"source": <source_service_id>, "target": <target_service_id>, "type": "calls|depends_on", "description": "描述原因"}}
]
```

只返回 JSON 数组，不要其他文字。"""

    # 调用 DeepSeek API
    api_key = getattr(settings, 'AI_API_KEY', None) or getattr(settings, 'ai_api_key', None)
    api_base = getattr(settings, 'AI_API_BASE', None) or getattr(settings, 'ai_api_base', 'https://api.deepseek.com/v1')

    if not api_key:
        raise HTTPException(status_code=500, detail="AI API Key 未配置")

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{api_base}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "max_tokens": 2000,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]

            # 提取 JSON
            json_match = re.search(r'\[.*\]', content, re.DOTALL)
            if not json_match:
                raise ValueError("AI 返回格式异常")

            suggestions = json.loads(json_match.group())

            # 验证 source/target 是否是有效的服务 ID
            valid_ids = {s["id"] for s in services_info}
            validated = []
            for s in suggestions:
                if s.get("source") in valid_ids and s.get("target") in valid_ids:
                    # 排除已有依赖
                    is_dup = any(
                        d["source"] == s["source"] and d["target"] == s["target"]
                        for d in existing_deps
                    )
                    if not is_dup:
                        validated.append({
                            "source": s["source"],
                            "target": s["target"],
                            "type": s.get("type", "depends_on"),
                            "description": s.get("description", ""),
                        })

            return {
                "suggestions": validated,
                "total": len(validated),
                "message": f"AI 分析了 {len(services_info)} 个服务，推荐 {len(validated)} 条新依赖关系",
            }

    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"AI 服务调用失败: {str(e)}")
    except (json.JSONDecodeError, ValueError, KeyError) as e:
        raise HTTPException(status_code=500, detail=f"AI 返回解析失败: {str(e)}")


@router.post("/ai-suggest/apply")
async def apply_ai_suggestions(
    suggestions: List[DependencyCreate],
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """批量应用 AI 推荐的依赖关系"""
    created = 0
    for s in suggestions:
        # 检查重复
        existing = await db.execute(
            select(ServiceDependency).where(
                ServiceDependency.source_service_id == s.source_service_id,
                ServiceDependency.target_service_id == s.target_service_id,
            )
        )
        if existing.scalar_one_or_none():
            continue

        dep = ServiceDependency(
            source_service_id=s.source_service_id,
            target_service_id=s.target_service_id,
            dependency_type=s.dependency_type,
            description=s.description,
        )
        db.add(dep)
        created += 1

    await db.commit()
    return {"detail": f"已应用 {created} 条依赖关系", "created": created}


# ====================================================================
# Cycle 8: 多服务器拓扑概览
# ====================================================================

@router.get("/multi-server", response_model=dict)
async def get_multi_server_topology(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    多服务器拓扑概览（图数据）。
    返回所有服务器节点 + nginx upstream 推导的边 + 统计摘要。
    前端可直接渲染为拓扑图。
    """
    # 所有服务器（带摘要指标）
    servers_result = (await db.execute(select(Server).order_by(Server.id))).scalars().all()
    nodes = []
    for s in servers_result:
        svc_count = (await db.execute(
            select(func.count()).select_from(ServerService).where(ServerService.server_id == s.id)
        )).scalar() or 0

        agg = (await db.execute(
            select(func.avg(ServerService.cpu_percent), func.avg(ServerService.mem_mb))
            .where(ServerService.server_id == s.id)
        )).one()

        nodes.append(ServerSummary(
            **ServerResponse.model_validate(s).model_dump(),
            service_count=svc_count,
            cpu_avg=round(agg[0], 2) if agg[0] is not None else None,
            mem_avg=round(agg[1], 2) if agg[1] is not None else None,
        ).model_dump())

    # 从 nginx_upstreams 推导边：upstream 所在服务器 → backend_address 对应的服务器
    edges = []
    upstreams = (await db.execute(select(NginxUpstream))).scalars().all()

    # 构建 IP → server 映射
    ip_to_server = {}
    for s in servers_result:
        if s.ip_address:
            ip_to_server[s.ip_address] = s.hostname

    for u in upstreams:
        # 找到 upstream 所属服务器的 hostname
        from_server = None
        for s in servers_result:
            if s.id == u.server_id:
                from_server = s.hostname
                break
        if not from_server:
            continue

        # backend_address 格式 "ip:port" 或 "hostname:port"
        backend_host = u.backend_address.split(":")[0]
        to_server = ip_to_server.get(backend_host, backend_host)

        edges.append(TopologyEdge(
            from_server=from_server,
            to_server=to_server,
            via="nginx_upstream",
            upstream=u.upstream_name,
        ).model_dump())

    # 汇总
    summary = {
        "server_count": len(nodes),
        "online_count": sum(1 for n in nodes if n["status"] == "online"),
        "offline_count": sum(1 for n in nodes if n["status"] == "offline"),
        "service_group_count": (await db.execute(
            select(func.count()).select_from(ServiceGroup)
        )).scalar() or 0,
        "edge_count": len(edges),
    }

    return {"servers": nodes, "edges": edges, "summary": summary}


# ====================================================================
# Cycle 8: Servers CRUD
# ====================================================================

@router.get("/servers", response_model=list[ServerSummary])
async def list_servers(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """列出所有服务器（带摘要指标）。"""
    servers = (await db.execute(select(Server).order_by(Server.id))).scalars().all()
    result = []
    for s in servers:
        svc_count = (await db.execute(
            select(func.count()).select_from(ServerService).where(ServerService.server_id == s.id)
        )).scalar() or 0
        agg = (await db.execute(
            select(func.avg(ServerService.cpu_percent), func.avg(ServerService.mem_mb))
            .where(ServerService.server_id == s.id)
        )).one()
        result.append(ServerSummary(
            **ServerResponse.model_validate(s).model_dump(),
            service_count=svc_count,
            cpu_avg=round(agg[0], 2) if agg[0] is not None else None,
            mem_avg=round(agg[1], 2) if agg[1] is not None else None,
        ))
    return result


@router.get("/servers/{server_id}")
async def get_server_detail(
    server_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取单台服务器详情（含运行的服务列表 + nginx upstream）。"""
    server = await db.get(Server, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="服务器不存在")

    # 服务列表
    ss_rows = (await db.execute(
        select(ServerService, ServiceGroup.name, ServiceGroup.category)
        .outerjoin(ServiceGroup, ServerService.group_id == ServiceGroup.id)
        .where(ServerService.server_id == server_id)
        .order_by(ServerService.id)
    )).all()
    services = []
    for ss, gname, gcat in ss_rows:
        d = ServerServiceResponse.model_validate(ss).model_dump()
        d["group_name"] = gname
        d["group_category"] = gcat
        services.append(d)

    # nginx upstreams
    upstreams = (await db.execute(
        select(NginxUpstream).where(NginxUpstream.server_id == server_id)
    )).scalars().all()
    upstream_list = [NginxUpstreamResponse.model_validate(u).model_dump() for u in upstreams]

    # 摘要
    svc_count = len(services)
    agg = (await db.execute(
        select(func.avg(ServerService.cpu_percent), func.avg(ServerService.mem_mb))
        .where(ServerService.server_id == server_id)
    )).one()

    return {
        "server": ServerSummary(
            **ServerResponse.model_validate(server).model_dump(),
            service_count=svc_count,
            cpu_avg=round(agg[0], 2) if agg[0] is not None else None,
            mem_avg=round(agg[1], 2) if agg[1] is not None else None,
        ).model_dump(),
        "services": services,
        "upstreams": upstream_list,
    }


@router.post("/servers", response_model=ServerResponse, status_code=201)
async def create_server(
    body: ServerCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """注册新服务器。"""
    existing = (await db.execute(
        select(Server).where(Server.hostname == body.hostname)
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail=f"服务器 {body.hostname} 已存在")
    server = Server(**body.model_dump())
    db.add(server)
    await db.commit()
    await db.refresh(server)
    return ServerResponse.model_validate(server)


@router.delete("/servers/{server_id}")
async def delete_server(
    server_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """删除服务器及其关联数据。"""
    server = await db.get(Server, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="服务器不存在")
    await db.execute(text("DELETE FROM server_services WHERE server_id = :sid"), {"sid": server_id})
    await db.execute(text("DELETE FROM nginx_upstreams WHERE server_id = :sid"), {"sid": server_id})
    await db.delete(server)
    await db.commit()
    return {"detail": "已删除"}


# ====================================================================
# Cycle 8: Service Groups
# ====================================================================

@router.get("/service-groups")
async def list_service_groups(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """列出所有服务组（含服务器分布）。"""
    groups = (await db.execute(select(ServiceGroup).order_by(ServiceGroup.id))).scalars().all()
    result = []
    for g in groups:
        # 找到运行此服务组的服务器
        ss_rows = (await db.execute(
            select(ServerService, Server.hostname, Server.ip_address, Server.status)
            .join(Server, ServerService.server_id == Server.id)
            .where(ServerService.group_id == g.id)
        )).all()
        servers = []
        for ss, hostname, ip, srv_status in ss_rows:
            servers.append({
                "server_id": ss.server_id,
                "hostname": hostname,
                "ip_address": ip,
                "server_status": srv_status,
                "port": ss.port,
                "pid": ss.pid,
                "service_status": ss.status,
                "cpu_percent": ss.cpu_percent,
                "mem_mb": ss.mem_mb,
            })
        result.append({
            "id": g.id,
            "name": g.name,
            "category": g.category,
            "created_at": g.created_at.isoformat() if g.created_at else None,
            "server_count": len(servers),
            "servers": servers,
        })
    return result
