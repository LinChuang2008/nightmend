"""add usage fields to ops_sessions

Revision ID: 031_add_ops_session_usage_fields
Revises: 030_add_session_id
Create Date: 2026-04-02
"""

from alembic import op
import sqlalchemy as sa


revision = "031_add_ops_session_usage_fields"
down_revision = "030_add_session_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ops_sessions", sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("ops_sessions", sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("ops_sessions", sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("ops_sessions", sa.Column("context_limit_tokens", sa.Integer(), nullable=False, server_default="120000"))

    op.alter_column("ops_sessions", "prompt_tokens", server_default=None)
    op.alter_column("ops_sessions", "completion_tokens", server_default=None)
    op.alter_column("ops_sessions", "total_tokens", server_default=None)
    op.alter_column("ops_sessions", "context_limit_tokens", server_default=None)


def downgrade() -> None:
    op.drop_column("ops_sessions", "context_limit_tokens")
    op.drop_column("ops_sessions", "total_tokens")
    op.drop_column("ops_sessions", "completion_tokens")
    op.drop_column("ops_sessions", "prompt_tokens")

