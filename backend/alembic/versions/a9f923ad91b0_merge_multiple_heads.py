"""merge_multiple_heads

Revision ID: a9f923ad91b0
Revises: 005_add_network_fields, 021_add_custom_runbooks_table, 024_add_ai_operation_logs_table
Create Date: 2026-03-22 02:54:17.771342

"""
from typing import Sequence, Union



# revision identifiers, used by Alembic.
revision: str = 'a9f923ad91b0'
down_revision: Union[str, None] = ('005_add_network_fields', '021_add_custom_runbooks_table', '024_add_ai_operation_logs_table')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
