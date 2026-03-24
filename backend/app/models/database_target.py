"""
数据库监控目标配置模型 (Database Monitor Target Model)

用于存储由平台手动配置的数据库监控目标，Agent 可按 host_id 拉取目标并自动采集指标。
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DatabaseMonitorTarget(Base):
    """数据库监控目标配置表。"""

    __tablename__ = "database_monitor_targets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    host_id: Mapped[int] = mapped_column(Integer, ForeignKey("hosts.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    db_type: Mapped[str] = mapped_column(String(20), nullable=False, default="postgres")
    db_host: Mapped[str] = mapped_column(String(255), nullable=False, default="localhost")
    db_port: Mapped[int] = mapped_column(Integer, nullable=False, default=5432)
    db_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    username: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    password: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    interval_sec: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    connect_timeout_sec: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    extra_config = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
