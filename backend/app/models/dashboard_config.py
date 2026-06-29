"""
Dashboard 配置模型

支持用户自定义 Dashboard 布局：
- 组件可拖拽重排
- 组件可显示/隐藏
- 布局配置持久化保存
- 预设布局模板
"""
from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base


class DashboardLayout(Base):
    """仪表盘布局配置"""
    __tablename__ = "dashboard_layouts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)  # 布局名称，如 "我的布局"、"运维视角"等
    description = Column(String(255))  # 布局描述
    is_active = Column(Boolean, default=False)  # 是否为当前激活的布局
    is_preset = Column(Boolean, default=False)  # 是否为预设模板
    grid_cols = Column(Integer, default=24)  # 网格列数（Ant Design 栅格系统）
    config = Column(JSON, nullable=False)  # 布局配置 JSON，包含所有组件的位置和状态
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # 关联用户
    user = relationship("User", back_populates="dashboard_layouts")


class DashboardComponent(Base):
    """仪表盘组件定义"""
    __tablename__ = "dashboard_components"

    id = Column(String(50), primary_key=True)  # 组件ID，如 "metrics_cards", "server_overview"
    name = Column(String(100), nullable=False)  # 组件显示名称
    description = Column(String(255))  # 组件描述
    category = Column(String(50))  # 组件分类：metrics, charts, tables, alerts
    default_config = Column(JSON)  # 默认配置，如位置、大小等
    is_enabled = Column(Boolean, default=True)  # 是否启用
    sort_order = Column(Integer, default=0)  # 排序权重
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# 在 User 模型中添加关联关系（需要更新 user.py）
# 这里只是注释，实际需要在 user.py 中添加：
# dashboard_layouts = relationship("DashboardLayout", back_populates="user", cascade="all, delete-orphan")