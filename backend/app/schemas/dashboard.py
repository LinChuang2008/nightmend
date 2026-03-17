"""
Dashboard 配置 Schema

定义 Dashboard 布局和组件的数据结构，用于 API 请求和响应的序列化。
"""
from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, ConfigDict, Field


# ==================== 组件配置 ====================

class ComponentConfigBase(BaseModel):
    """组件配置基础结构"""
    id: str = Field(..., description="组件唯一标识")
    name: str = Field(..., description="组件显示名称")
    visible: bool = Field(True, description="是否可见")
    position: Dict[str, Any] = Field(..., description="组件位置配置")
    size: Dict[str, Any] = Field(..., description="组件大小配置")
    settings: Optional[Dict[str, Any]] = Field(None, description="组件特定设置")


class DashboardComponentInfo(BaseModel):
    """仪表盘组件信息"""
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: Optional[str] = None
    category: str
    default_config: Optional[Dict[str, Any]] = None
    is_enabled: bool
    sort_order: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ==================== 布局配置 ====================

class DashboardLayoutBase(BaseModel):
    """仪表盘布局基础配置"""
    name: str = Field(..., max_length=100, description="布局名称")
    description: Optional[str] = Field(None, max_length=255, description="布局描述")
    grid_cols: int = Field(24, ge=12, le=48, description="网格列数")
    config: Dict[str, Any] = Field(..., description="布局配置JSON")


class DashboardLayoutCreate(DashboardLayoutBase):
    """创建仪表盘布局"""
    is_preset: bool = Field(False, description="是否为预设模板")


class DashboardLayoutUpdate(BaseModel):
    """更新仪表盘布局"""
    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, max_length=255)
    grid_cols: Optional[int] = Field(None, ge=12, le=48)
    config: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class DashboardLayoutResponse(DashboardLayoutBase):
    """仪表盘布局响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    is_active: bool
    is_preset: bool
    created_at: datetime
    updated_at: datetime


# ==================== 预设布局 ====================

class PresetLayoutInfo(BaseModel):
    """预设布局信息"""
    id: str = Field(..., description="预设布局ID")
    name: str = Field(..., description="预设布局名称")
    description: str = Field(..., description="预设布局描述")
    preview_image: Optional[str] = Field(None, description="预览图URL")
    config: Dict[str, Any] = Field(..., description="布局配置")


# ==================== 批量操作 ====================

class BatchLayoutOperation(BaseModel):
    """批量布局操作"""
    operation: str = Field(..., description="操作类型：activate, delete, copy")
    layout_ids: List[int] = Field(..., description="布局ID列表")


class DashboardLayoutList(BaseModel):
    """仪表盘布局列表"""
    total: int
    items: List[DashboardLayoutResponse]


# ==================== 快速配置 ====================

class QuickConfigUpdate(BaseModel):
    """快速配置更新"""
    component_id: str = Field(..., description="组件ID")
    visible: Optional[bool] = Field(None, description="显示/隐藏")
    position: Optional[Dict[str, Any]] = Field(None, description="位置更新")
    size: Optional[Dict[str, Any]] = Field(None, description="大小更新")


# ==================== 响应格式 ====================

class DashboardConfigResponse(BaseModel):
    """仪表盘配置响应"""
    current_layout: Optional[DashboardLayoutResponse] = None
    available_components: List[DashboardComponentInfo]
    preset_layouts: List[PresetLayoutInfo]
    user_layouts: List[DashboardLayoutResponse]


class OperationResponse(BaseModel):
    """操作响应"""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None