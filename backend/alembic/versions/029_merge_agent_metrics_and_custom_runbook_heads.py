"""merge agent metrics and custom runbook migration heads

Revision ID: 029_merge_runbook_heads
Revises: 027_agent_res_metrics, 028_runbook_verify_steps
Create Date: 2026-03-26
"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "029_merge_runbook_heads"
down_revision: Union[str, Sequence[str], None] = (
    "028_runbook_verify_steps",
    "a9f923ad91b0",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
