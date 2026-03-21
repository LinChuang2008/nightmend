"""全局菜单设置模型。"""
from sqlalchemy import DateTime, Integer, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MenuSetting(Base):
    """全局菜单可见性配置（管理员维护，所有用户生效）。"""

    __tablename__ = "menu_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hidden_keys: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

