"""merge orphan head a9f923ad91b0 into main chain

Revision ID: 999_merge_orphan_head
Revises: 031_add_ops_session_usage_fields, a9f923ad91b0
Create Date: 2026-04-21

背景：
    alembic 仓库里有两个 head：
      - 031_add_ops_session_usage_fields（主链当前尾部）
      - a9f923ad91b0（早期遗留的 merge 节点，没有后继）

    no-op merge 把它们汇合，让 `alembic upgrade head` 工作，
    不改动 schema 也不触发任何 DDL。
"""
from typing import Sequence, Union


revision: str = "999_merge_orphan_head"
down_revision: Union[str, Sequence[str], None] = (
    "031_add_ops_session_usage_fields",
    "a9f923ad91b0",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
