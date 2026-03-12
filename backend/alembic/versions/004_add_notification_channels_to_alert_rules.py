"""add notification_channel_ids to alert_rules

Revision ID: 004_add_notification_channels
Revises: 003_add_en_fields
Create Date: 2026-03-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "004_add_notification_channels"
down_revision: Union[str, None] = "003_add_en_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "alert_rules",
        sa.Column("notification_channel_ids", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("alert_rules", "notification_channel_ids")
