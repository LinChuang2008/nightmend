"""add network fields to hosts

Revision ID: 005_add_network_fields
Revises: 004_add_notification_channels
Create Date: 2026-03-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "005_add_network_fields"
down_revision: Union[str, None] = "004_add_notification_channels"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 添加新字段
    op.add_column('hosts', sa.Column('display_name', sa.String(255), nullable=True))
    op.add_column('hosts', sa.Column('private_ip', sa.String(45), nullable=True))
    op.add_column('hosts', sa.Column('public_ip', sa.String(45), nullable=True))
    op.add_column('hosts', sa.Column('network_info', sa.JSON(), nullable=True))

    # 数据迁移：智能分类现有 ip_address
    # 内网 IP 模式：10.x, 172.16-31.x, 192.168.x
    op.execute("""
        UPDATE hosts
        SET private_ip = ip_address
        WHERE ip_address IS NOT NULL
        AND (
            ip_address ~ '^10\\.'
            OR ip_address ~ '^172\\.(1[6-9]|2[0-9]|3[01])\\.'
            OR ip_address ~ '^192\\.168\\.'
        )
    """)

    # 公网 IP：非内网且非本地回环
    op.execute("""
        UPDATE hosts
        SET public_ip = ip_address
        WHERE ip_address IS NOT NULL
        AND private_ip IS NULL
        AND ip_address !~ '^127\\.'
        AND ip_address !~ '^169\\.254\\.'  # AWS link-local
        AND ip_address !~ '^fc00:'  # IPv6 私有地址
        AND ip_address !~ '^fe80:'  # IPv6 link-local
    """)

    # network_info 初始化（将现有的 ip_address 保存到 network_info）
    op.execute("""
        UPDATE hosts
        SET network_info = jsonb_build_object(
            'primary_ip', ip_address,
            'interfaces', jsonb_build_object(
                'default', jsonb_build_object(
                    'ipv4', ip_address,
                    'type', CASE
                        WHEN private_ip IS NOT NULL THEN 'private'
                        WHEN public_ip IS NOT NULL THEN 'public'
                        ELSE 'unknown'
                    END
                )
            )
        )
        WHERE ip_address IS NOT NULL
    """)


def downgrade() -> None:
    op.drop_column('hosts', 'network_info')
    op.drop_column('hosts', 'public_ip')
    op.drop_column('hosts', 'private_ip')
    op.drop_column('hosts', 'display_name')
