"""add server_id to host_metrics

Revision ID: 002_metrics_server_id
Revises: 001_topology
Create Date: 2026-02-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002_metrics_server_id"
down_revision: Union[str, None] = "001_topology"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'host_metrics')"
        )
    )
    if not result.scalar():
        return
    result2 = conn.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'host_metrics' AND column_name = 'server_id')"
        )
    )
    if result2.scalar():
        return
    op.add_column(
        "host_metrics",
        sa.Column("server_id", sa.Integer(), nullable=True, index=True),
    )
    op.create_foreign_key(
        "fk_host_metrics_server_id",
        "host_metrics",
        "servers",
        ["server_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_host_metrics_server_id", "host_metrics", type_="foreignkey")
    op.drop_column("host_metrics", "server_id")
