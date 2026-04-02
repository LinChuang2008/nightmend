"""add session_id to remediation_logs

Revision ID: 030_add_session_id
Revises: 029_merge_runbook_heads
Create Date: 2026-04-01
"""
from alembic import op
import sqlalchemy as sa


revision = "030_add_session_id"
down_revision = "029_merge_runbook_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "remediation_logs",
        sa.Column("session_id", sa.String(36), nullable=True),
    )
    op.create_index(
        "ix_remediation_logs_session_id",
        "remediation_logs",
        ["session_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_remediation_logs_session_id", table_name="remediation_logs")
    op.drop_column("remediation_logs", "session_id")
