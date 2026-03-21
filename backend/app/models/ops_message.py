"""运维消息模型 (Ops Message Model)"""
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, func, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class OpsMessage(Base):
    __tablename__ = "ops_messages"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("ops_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)   # user / assistant / tool / system
    msg_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # text / tool_call / tool_result / command_request / command_output /
    # command_result / ask_user / ask_user_answer / todo_update / skill_load / compaction_summary
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    tool_call_id: Mapped[str | None] = mapped_column(String(100), nullable=True)  # OpenAI tool_call_id
    compacted: Mapped[bool] = mapped_column(nullable=False, default=False)  # 是否已被压缩（软删除）
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
