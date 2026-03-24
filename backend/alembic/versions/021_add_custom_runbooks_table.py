"""add custom_runbooks table

Revision ID: 021_add_custom_runbooks_table
Revises: 020_add_continuous_alert_and_dedup_fields
Create Date: 2026-03-14

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '021_add_custom_runbooks_table'
down_revision = '021_add_suppression_rules'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'custom_runbooks',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=False, server_default=''),
        sa.Column('trigger_keywords', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('risk_level', sa.String(20), nullable=False, server_default='manual'),
        sa.Column('steps', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('safety_checks', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_custom_runbooks_name', 'custom_runbooks', ['name'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_custom_runbooks_name', table_name='custom_runbooks')
    op.drop_table('custom_runbooks')
