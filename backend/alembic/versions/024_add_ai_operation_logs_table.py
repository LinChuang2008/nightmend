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
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_operation_logs (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            session_id VARCHAR(36) NULL,
            request_id VARCHAR(64) NULL,
            host_id INTEGER NULL,
            host_name VARCHAR(255) NULL,
            command TEXT NOT NULL,
            reason TEXT NULL,
            exit_code INTEGER NULL,
            duration_ms INTEGER NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'unknown',
            created_at TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_ai_operation_logs_user_id ON ai_operation_logs (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_ai_operation_logs_session_id ON ai_operation_logs (session_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_ai_operation_logs_request_id ON ai_operation_logs (request_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_ai_operation_logs_host_id ON ai_operation_logs (host_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_ai_operation_logs_status ON ai_operation_logs (status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_ai_operation_logs_created_at ON ai_operation_logs (created_at)")


def downgrade():
    op.drop_table("ai_operation_logs")

