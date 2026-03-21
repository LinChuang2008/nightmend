"""
添加屏蔽规则表 (Add Suppression Rules Table)

创建 suppression_rules 表，用于统一管理各种监控维度的告警屏蔽规则。
支持按资源类型、资源ID、告警规则、时间范围等多维度配置屏蔽。

Revision ID: 021
Revises: 020
Create Date: 2026-03-13
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '021_add_suppression_rules'
down_revision = '020_add_continuous_alert_and_dedup_fields'
branch_labels = None
depends_on = None


def upgrade():
    """创建 suppression_rules 表及其索引"""
    op.create_table(
        'suppression_rules',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('resource_type', sa.String(length=50), server_default='general', nullable=False),
        sa.Column('resource_id', sa.Integer(), nullable=True),
        sa.Column('resource_pattern', sa.String(length=500), nullable=True),
        sa.Column('alert_rule_id', sa.Integer(), nullable=True),
        sa.Column('start_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('end_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('suppress_alerts', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('suppress_notifications', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('suppress_ai_analysis', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('suppress_log_scan', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('created_by', sa.String(length=255), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('match_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # 创建外键约束
    op.create_foreign_key(
        'fk_suppression_rules_alert_rule_id',
        'suppression_rules', 'alert_rules',
        ['alert_rule_id'], ['id']
    )

    # 创建索引以提升查询性能
    op.create_index('ix_suppression_rules_resource_type', 'suppression_rules', ['resource_type'])
    op.create_index('ix_suppression_rules_resource_id', 'suppression_rules', ['resource_id'])
    op.create_index('ix_suppression_rules_alert_rule_id', 'suppression_rules', ['alert_rule_id'])
    op.create_index('ix_suppression_rules_is_active', 'suppression_rules', ['is_active'])
    op.create_index('ix_suppression_rules_start_time', 'suppression_rules', ['start_time'])
    op.create_index('ix_suppression_rules_end_time', 'suppression_rules', ['end_time'])


def downgrade():
    """删除 suppression_rules 表"""
    op.drop_table('suppression_rules')
