"""
添加 AI 运维助手会话表 (Add Ops Assistant Session Tables)

创建 ops_sessions 和 ops_messages 表，支持 AI Agent Loop 多轮对话持久化。

Revision ID: 022
Revises: 021
Create Date: 2026-03-18
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = '022_add_ops_tables'
down_revision = '021_add_custom_runbooks_table'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'ops_sessions',
        sa.Column('id', UUID(as_uuid=False), primary_key=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(100), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='active'),
        sa.Column('target_host_id', sa.Integer(), nullable=True),
        sa.Column('token_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('compacted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_ops_sessions_user_id', 'ops_sessions', ['user_id'])

    op.create_table(
        'ops_messages',
        sa.Column('id', UUID(as_uuid=False), primary_key=True),
        sa.Column('session_id', UUID(as_uuid=False),
                  sa.ForeignKey('ops_sessions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('role', sa.String(20), nullable=False),
        sa.Column('msg_type', sa.String(30), nullable=False),
        sa.Column('content', JSONB, nullable=False),
        sa.Column('tool_call_id', sa.String(100), nullable=True),
        sa.Column('compacted', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_ops_messages_session_id', 'ops_messages', ['session_id'])
    op.create_index('ix_ops_messages_created_at', 'ops_messages', ['created_at'])


def downgrade():
    op.drop_table('ops_messages')
    op.drop_table('ops_sessions')
