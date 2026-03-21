"""
新增 AI 操作日志表 (Add AI Operation Logs Table)

Revision ID: 024_add_ai_operation_logs_table
Revises: 023_add_menu_settings_table
Create Date: 2026-03-20
"""
from alembic import op
import sqlalchemy as sa

revision = "024_add_ai_operation_logs_table"
down_revision = "023_add_menu_settings_table"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ai_operation_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("host_id", sa.Integer(), nullable=True),
        sa.Column("host_name", sa.String(length=255), nullable=True),
        sa.Column("command", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="unknown"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_ai_operation_logs_user_id", "ai_operation_logs", ["user_id"])
    op.create_index("ix_ai_operation_logs_session_id", "ai_operation_logs", ["session_id"])
    op.create_index("ix_ai_operation_logs_request_id", "ai_operation_logs", ["request_id"])
    op.create_index("ix_ai_operation_logs_host_id", "ai_operation_logs", ["host_id"])
    op.create_index("ix_ai_operation_logs_status", "ai_operation_logs", ["status"])
    op.create_index("ix_ai_operation_logs_created_at", "ai_operation_logs", ["created_at"])


def downgrade():
    op.drop_table("ai_operation_logs")

