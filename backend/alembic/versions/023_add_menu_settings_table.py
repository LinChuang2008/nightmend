"""
新增全局菜单设置表 (Add Global Menu Settings Table)

Revision ID: 023_add_menu_settings_table
Revises: 022_add_ops_tables
Create Date: 2026-03-20
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "023_add_menu_settings_table"
down_revision = "022_add_ops_tables"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "menu_settings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("hidden_keys", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("menu_settings")

