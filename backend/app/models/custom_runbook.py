"""
自定义 Runbook 模型 (Custom Runbook Model)

允许用户创建自定义修复脚本，扩展内置 Runbook 的能力。
Allows users to create custom remediation scripts, extending built-in Runbook capabilities.
"""
from datetime import datetime

from sqlalchemy import String, Integer, Boolean, DateTime, Text, JSON, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CustomRunbook(Base):
    """
    自定义 Runbook 表 (Custom Runbook Table)

    存储用户创建的自定义修复脚本定义。
    """
    __tablename__ = "custom_runbooks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    match_alert_types: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    trigger_keywords: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    steps: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    verify_steps: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    safety_checks: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_by: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
