"""add database monitor targets table

Revision ID: 025_add_database_monitor_targets
Revises: 024_add_ai_operation_logs_table
Create Date: 2026-03-23
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "025_add_database_monitor_targets"
down_revision: Union[str, None] = "024_add_ai_operation_logs_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS database_monitor_targets (
            id SERIAL PRIMARY KEY,
            host_id INTEGER NOT NULL REFERENCES hosts(id),
            name VARCHAR(255) NOT NULL,
            db_type VARCHAR(20) NOT NULL DEFAULT 'postgres',
            db_host VARCHAR(255) NOT NULL DEFAULT 'localhost',
            db_port INTEGER NOT NULL DEFAULT 5432,
            db_name VARCHAR(255) NOT NULL DEFAULT '',
            username VARCHAR(255) NOT NULL DEFAULT '',
            password VARCHAR(512) NOT NULL DEFAULT '',
            interval_sec INTEGER NOT NULL DEFAULT 60,
            connect_timeout_sec INTEGER NOT NULL DEFAULT 10,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            extra_config JSON NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_database_monitor_targets_host_id ON database_monitor_targets (host_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_database_monitor_targets_is_active ON database_monitor_targets (is_active)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_database_monitor_targets_host_name ON database_monitor_targets (host_id, name)")


def downgrade() -> None:
    op.drop_index("ix_database_monitor_targets_host_name", table_name="database_monitor_targets")
    op.drop_index("ix_database_monitor_targets_is_active", table_name="database_monitor_targets")
    op.drop_index("ix_database_monitor_targets_host_id", table_name="database_monitor_targets")
    op.drop_table("database_monitor_targets")
