"""merge agent metrics and custom runbook migration heads

Revision ID: 029_merge_runbook_heads
Revises: 028_runbook_verify_steps
Create Date: 2026-03-26

历史备注：原本是合并 `027_agent_res_metrics` + `028_runbook_verify_steps` 两个 head，
但 `027_agent_res_metrics` 迁移文件已从代码库移除（见 git log 73ee4d9），
这里保留文件结构把它退化成单父节点的 no-op"merge"，避免 alembic 启动时 KeyError。
"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "029_merge_runbook_heads"
down_revision: Union[str, Sequence[str], None] = "028_runbook_verify_steps"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
