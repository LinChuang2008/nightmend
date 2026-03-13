"""add continuous_alert to alert_rules and update alert_deduplications table

Revision ID: 020_add_continuous_alert_and_dedup_fields
Revises:
Create Date: 2026-03-13

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '020_add_continuous_alert_and_dedup_fields'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. 给 alert_rules 添加 continuous_alert 字段
    op.add_column('alert_rules', sa.Column('continuous_alert', sa.Boolean(), server_default='true', nullable=False))
    print("Added continuous_alert column to alert_rules")

    # 2. 更新 alert_deduplications 表结构
    # 注意：由于字段变更较大，需要谨慎处理
    # 先重命名旧字段
    op.alter_column('alert_deduplications', 'first_occurrence', new_column_name='first_violation_time')
    print("Renamed first_occurrence to first_violation_time")

    # 添加新字段
    op.add_column('alert_deduplications', sa.Column('first_alert_time', sa.DateTime(timezone=True), nullable=True))
    op.add_column('alert_deduplications', sa.Column('last_alert_time', sa.DateTime(timezone=True), nullable=True))
    op.add_column('alert_deduplications', sa.Column('last_check_time', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.add_column('alert_deduplications', sa.Column('alert_sent_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('alert_deduplications', sa.Column('alert_triggered', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('alert_deduplications', sa.Column('recovery_start_time', sa.DateTime(timezone=True), nullable=True))
    print("Added new columns to alert_deduplications")

    # 3. 将 last_occurrence 的数据迁移到 last_check_time
    op.execute("""
        UPDATE alert_deduplications
        SET last_check_time = last_occurrence
        WHERE last_check_time IS NULL
    """)
    print("Migrated last_occurrence data to last_check_time")


def downgrade() -> None:
    # 回滚字段变更
    op.alter_column('alert_deduplications', 'first_violation_time', new_column_name='first_occurrence')
    op.drop_column('alert_deduplications', 'first_alert_time')
    op.drop_column('alert_deduplications', 'last_alert_time')
    op.drop_column('alert_deduplications', 'last_check_time')
    op.drop_column('alert_deduplications', 'alert_sent_count')
    op.drop_column('alert_deduplications', 'alert_triggered')
    op.drop_column('alert_deduplications', 'recovery_start_time')
    op.drop_column('alert_rules', 'continuous_alert')
    print("Rolled back all changes")
