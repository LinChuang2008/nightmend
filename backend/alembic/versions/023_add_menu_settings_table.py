"""
新增全局菜单设置表 (Add Global Menu Settings Table)

Revision ID: 023_add_menu_settings_table
Revises: 022_add_ops_tables
Create Date: 2026-03-20
"""
from alembic import op

revision = "023_add_menu_settings_table"
down_revision = "022_add_ops_tables"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS menu_settings (
            id SERIAL PRIMARY KEY,
            hidden_keys JSONB NOT NULL DEFAULT '[]'::jsonb,
            updated_by INTEGER NULL,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
        """
    )


def downgrade():
    op.drop_table("menu_settings")

