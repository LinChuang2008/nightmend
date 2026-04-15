"""
Dashboard 配置管理 API

提供 Dashboard 布局的 CRUD 操作、预设模板管理、组件配置等功能。
用户可以自定义 Dashboard 布局，保存多个配置方案，并在不同方案间切换。
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.dashboard_config import DashboardLayout, DashboardComponent
from app.schemas.dashboard import (
    DashboardLayoutCreate,
    DashboardLayoutUpdate, 
    DashboardLayoutResponse,
    DashboardLayoutList,
    DashboardComponentInfo,
    DashboardConfigResponse,
    PresetLayoutInfo,
    QuickConfigUpdate,
    OperationResponse,
)

router = APIRouter(prefix="/dashboard-config", tags=["dashboard-config"])


# ==================== 预设布局数据 ====================

PRESET_LAYOUTS = [
    {
        "id": "operations_view",
        "name": "运维视角",
        "description": "突出系统监控和告警，适合运维人员日常使用",
        "config": {
            "components": [
                {"id": "metrics_cards", "position": {"row": 0, "col": 0, "span": 24}, "visible": True},
                {"id": "alert_summary", "position": {"row": 1, "col": 0, "span": 12}, "visible": True},
                {"id": "server_overview", "position": {"row": 1, "col": 12, "span": 12}, "visible": True},
                {"id": "trends_charts", "position": {"row": 2, "col": 0, "span": 24}, "visible": True},
                {"id": "resource_compare", "position": {"row": 3, "col": 0, "span": 12}, "visible": True},
                {"id": "network_bandwidth", "position": {"row": 3, "col": 12, "span": 12}, "visible": True},
                {"id": "recent_alerts", "position": {"row": 4, "col": 0, "span": 24}, "visible": True},
            ]
        }
    },
    {
        "id": "management_view", 
        "name": "管理视角",
        "description": "突出整体状态和趋势分析，适合管理人员决策参考",
        "config": {
            "components": [
                {"id": "metrics_cards", "position": {"row": 0, "col": 0, "span": 18}, "visible": True},
                {"id": "health_score", "position": {"row": 0, "col": 18, "span": 6}, "visible": True},
                {"id": "trends_charts", "position": {"row": 1, "col": 0, "span": 24}, "visible": True},
                {"id": "resource_compare", "position": {"row": 2, "col": 0, "span": 12}, "visible": True},
                {"id": "network_bandwidth", "position": {"row": 2, "col": 12, "span": 12}, "visible": True},
                {"id": "server_overview", "position": {"row": 3, "col": 0, "span": 24}, "visible": True},
                {"id": "log_stats", "position": {"row": 4, "col": 0, "span": 12}, "visible": True},
                {"id": "recent_alerts", "position": {"row": 4, "col": 12, "span": 12}, "visible": True},
            ]
        }
    },
    {
        "id": "developer_view",
        "name": "开发视角", 
        "description": "突出服务状态和日志信息，适合开发人员故障排查",
        "config": {
            "components": [
                {"id": "metrics_cards", "position": {"row": 0, "col": 0, "span": 24}, "visible": True},
                {"id": "server_overview", "position": {"row": 1, "col": 0, "span": 24}, "visible": True},
                {"id": "log_stats", "position": {"row": 2, "col": 0, "span": 12}, "visible": True},
                {"id": "recent_alerts", "position": {"row": 2, "col": 12, "span": 12}, "visible": True},
                {"id": "trends_charts", "position": {"row": 3, "col": 0, "span": 24}, "visible": True},
                {"id": "resource_compare", "position": {"row": 4, "col": 0, "span": 24}, "visible": False},
                {"id": "network_bandwidth", "position": {"row": 5, "col": 0, "span": 24}, "visible": False},
            ]
        }
    }
]

DEFAULT_COMPONENTS = [
    {
        "id": "metrics_cards",
        "name": "核心指标卡片",
        "description": "显示服务器、服务、数据库、告警等核心指标",
        "category": "metrics",
        "default_config": {"position": {"row": 0, "col": 0, "span": 24}, "visible": True},
        "is_enabled": True,
        "sort_order": 1,
    },
    {
        "id": "health_score", 
        "name": "健康评分",
        "description": "系统整体健康评分和状态",
        "category": "metrics",
        "default_config": {"position": {"row": 0, "col": 20, "span": 4}, "visible": True},
        "is_enabled": True,
        "sort_order": 2,
    },
    {
        "id": "server_overview",
        "name": "服务器总览",
        "description": "服务器健康状态和关键指标总览",
        "category": "metrics",
        "default_config": {"position": {"row": 1, "col": 0, "span": 24}, "visible": True},
        "is_enabled": True,
        "sort_order": 3,
    },
    {
        "id": "trends_charts",
        "name": "24小时趋势",
        "description": "CPU、内存、告警、错误日志趋势图",
        "category": "charts",
        "default_config": {"position": {"row": 2, "col": 0, "span": 24}, "visible": True},
        "is_enabled": True,
        "sort_order": 4,
    },
    {
        "id": "resource_compare",
        "name": "资源使用率对比",
        "description": "多服务器资源使用情况对比图表",
        "category": "charts",
        "default_config": {"position": {"row": 3, "col": 0, "span": 12}, "visible": True},
        "is_enabled": True,
        "sort_order": 5,
    },
    {
        "id": "network_bandwidth",
        "name": "网络带宽",
        "description": "服务器网络带宽使用情况",
        "category": "charts",
        "default_config": {"position": {"row": 3, "col": 12, "span": 12}, "visible": True},
        "is_enabled": True,
        "sort_order": 6,
    },
    {
        "id": "log_stats",
        "name": "日志统计",
        "description": "日志数量和错误统计",
        "category": "tables",
        "default_config": {"position": {"row": 4, "col": 0, "span": 12}, "visible": True},
        "is_enabled": True,
        "sort_order": 7,
    },
    {
        "id": "recent_alerts",
        "name": "最新告警",
        "description": "最近的告警事件列表",
        "category": "alerts",
        "default_config": {"position": {"row": 4, "col": 12, "span": 12}, "visible": True},
        "is_enabled": True,
        "sort_order": 8,
    },
]


# ==================== API 端点 ====================

@router.get("/", response_model=DashboardConfigResponse)
async def get_dashboard_config(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取用户的仪表盘配置信息"""
    # 获取用户当前激活的布局
    result = await db.execute(
        select(DashboardLayout).where(
            and_(DashboardLayout.user_id == current_user.id, DashboardLayout.is_active == True)
        )
    )
    current_layout = result.scalar_one_or_none()
    
    # 获取用户所有布局
    result = await db.execute(
        select(DashboardLayout).where(
            and_(DashboardLayout.user_id == current_user.id, DashboardLayout.is_preset == False)
        ).order_by(DashboardLayout.updated_at.desc())
    )
    user_layouts = result.scalars().all()
    
    # 获取可用组件（从数据库或默认配置）
    result = await db.execute(
        select(DashboardComponent).where(
            DashboardComponent.is_enabled == True
        ).order_by(DashboardComponent.sort_order)
    )
    db_components = result.scalars().all()
    
    # 如果数据库中没有组件，使用默认配置
    if not db_components:
        available_components = [DashboardComponentInfo(**comp) for comp in DEFAULT_COMPONENTS]
    else:
        available_components = [DashboardComponentInfo.from_orm(comp) for comp in db_components]
    
    return DashboardConfigResponse(
        current_layout=DashboardLayoutResponse.from_orm(current_layout) if current_layout else None,
        available_components=available_components,
        preset_layouts=[PresetLayoutInfo(**preset) for preset in PRESET_LAYOUTS],
        user_layouts=[DashboardLayoutResponse.from_orm(layout) for layout in user_layouts]
    )


@router.post("/layouts", response_model=DashboardLayoutResponse)
async def create_layout(
    layout_data: DashboardLayoutCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """创建新的仪表盘布局"""
    result = await db.execute(
        select(DashboardLayout).where(
            and_(DashboardLayout.user_id == current_user.id, DashboardLayout.name == layout_data.name)
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"布局名称 '{layout_data.name}' 已存在")
    
    db_layout = DashboardLayout(
        user_id=current_user.id, name=layout_data.name, description=layout_data.description,
        grid_cols=layout_data.grid_cols, config=layout_data.config,
        is_preset=layout_data.is_preset, is_active=False
    )
    db.add(db_layout)
    await db.commit()
    await db.refresh(db_layout)
    return DashboardLayoutResponse.from_orm(db_layout)


@router.get("/layouts", response_model=DashboardLayoutList)
async def list_layouts(
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取用户的仪表盘布局列表"""
    from sqlalchemy import func as sqlfunc
    offset = (page - 1) * page_size
    
    total_result = await db.execute(
        select(sqlfunc.count(DashboardLayout.id)).where(DashboardLayout.user_id == current_user.id)
    )
    total = total_result.scalar() or 0
    
    result = await db.execute(
        select(DashboardLayout).where(DashboardLayout.user_id == current_user.id)
        .order_by(DashboardLayout.is_active.desc(), DashboardLayout.updated_at.desc())
        .offset(offset).limit(page_size)
    )
    layouts = result.scalars().all()
    
    return DashboardLayoutList(
        total=total,
        items=[DashboardLayoutResponse.from_orm(layout) for layout in layouts]
    )


@router.put("/layouts/{layout_id}", response_model=DashboardLayoutResponse)
async def update_layout(
    layout_id: int,
    layout_data: DashboardLayoutUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """更新仪表盘布局"""
    from sqlalchemy import update as sql_update
    result = await db.execute(
        select(DashboardLayout).where(and_(DashboardLayout.id == layout_id, DashboardLayout.user_id == current_user.id))
    )
    layout = result.scalar_one_or_none()
    if not layout:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="布局不存在")
    
    if layout_data.is_active:
        await db.execute(
            sql_update(DashboardLayout).where(
                and_(DashboardLayout.user_id == current_user.id, DashboardLayout.id != layout_id)
            ).values(is_active=False)
        )
    
    update_data = layout_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(layout, field, value)
    
    await db.commit()
    await db.refresh(layout)
    return DashboardLayoutResponse.from_orm(layout)


@router.delete("/layouts/{layout_id}", response_model=OperationResponse)
async def delete_layout(
    layout_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """删除仪表盘布局"""
    result = await db.execute(
        select(DashboardLayout).where(and_(DashboardLayout.id == layout_id, DashboardLayout.user_id == current_user.id))
    )
    layout = result.scalar_one_or_none()
    if not layout:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="布局不存在")
    if layout.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无法删除当前激活的布局，请先切换到其他布局")
    
    await db.delete(layout)
    await db.commit()
    return OperationResponse(success=True, message="布局删除成功")


@router.post("/layouts/{layout_id}/activate", response_model=OperationResponse)
async def activate_layout(
    layout_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """激活指定的仪表盘布局"""
    from sqlalchemy import update as sql_update
    result = await db.execute(
        select(DashboardLayout).where(and_(DashboardLayout.id == layout_id, DashboardLayout.user_id == current_user.id))
    )
    layout = result.scalar_one_or_none()
    if not layout:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="布局不存在")
    
    await db.execute(
        sql_update(DashboardLayout).where(
            and_(DashboardLayout.user_id == current_user.id, DashboardLayout.id != layout_id)
        ).values(is_active=False)
    )
    layout.is_active = True
    await db.commit()
    return OperationResponse(success=True, message=f"布局 '{layout.name}' 已激活")


@router.post("/layouts/from-preset", response_model=DashboardLayoutResponse)
async def create_from_preset(
    preset_id: str,
    layout_name: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """从预设模板创建新布局"""
    preset = next((p for p in PRESET_LAYOUTS if p["id"] == preset_id), None)
    if not preset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="预设模板不存在")
    
    result = await db.execute(
        select(DashboardLayout).where(and_(DashboardLayout.user_id == current_user.id, DashboardLayout.name == layout_name))
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"布局名称 '{layout_name}' 已存在")
    
    db_layout = DashboardLayout(
        user_id=current_user.id, name=layout_name,
        description=f"基于 '{preset['name']}' 模板创建",
        grid_cols=24, config=preset["config"], is_preset=False, is_active=False
    )
    db.add(db_layout)
    await db.commit()
    await db.refresh(db_layout)
    return DashboardLayoutResponse.from_orm(db_layout)


@router.post("/quick-config", response_model=OperationResponse)
async def quick_config_update(
    updates: QuickConfigUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """快速更新组件配置（用于拖拽等实时操作）"""
    result = await db.execute(
        select(DashboardLayout).where(
            and_(DashboardLayout.user_id == current_user.id, DashboardLayout.is_active == True)
        )
    )
    layout = result.scalar_one_or_none()
    if not layout:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="没有激活的布局")
    
    config = layout.config
    components = config.get("components", [])
    
    updated = False
    for component in components:
        if component["id"] == updates.component_id:
            if updates.visible is not None:
                component["visible"] = updates.visible
            if updates.position is not None:
                component["position"].update(updates.position)
            if updates.size is not None:
                component.setdefault("size", {}).update(updates.size)
            updated = True
            break
    
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"组件 '{updates.component_id}' 不存在")
    
    layout.config = config
    await db.commit()
    return OperationResponse(success=True, message="配置更新成功")


@router.get("/components", response_model=List[DashboardComponentInfo])
async def list_components(db: AsyncSession = Depends(get_db)):
    """获取所有可用的仪表盘组件"""
    result = await db.execute(
        select(DashboardComponent).where(DashboardComponent.is_enabled == True).order_by(DashboardComponent.sort_order)
    )
    components = result.scalars().all()
    
    if not components:
        return [DashboardComponentInfo(**comp) for comp in DEFAULT_COMPONENTS]
    
    return [DashboardComponentInfo.from_orm(comp) for comp in components]