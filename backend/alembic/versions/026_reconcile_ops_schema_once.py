"""one-shot schema reconciliation for ops/database features

Revision ID: 026_reconcile_ops_schema_once
Revises: 025_add_database_monitor_targets
Create Date: 2026-03-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "026_reconcile_ops_schema_once"
down_revision: Union[str, None] = "025_add_database_monitor_targets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _column_exists(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    try:
        cols = inspector.get_columns(table_name)
    except Exception:
        return False
    return any(c.get("name") == column_name for c in cols)


def _ensure_index(sql: str) -> None:
    op.execute(sa.text(sql))


def _ensure_alert_rule_and_dedup_columns(inspector: sa.Inspector) -> None:
    if _table_exists(inspector, "alert_rules") and not _column_exists(inspector, "alert_rules", "continuous_alert"):
        op.execute(sa.text("ALTER TABLE alert_rules ADD COLUMN IF NOT EXISTS continuous_alert BOOLEAN NOT NULL DEFAULT TRUE"))

    if not _table_exists(inspector, "alert_deduplications"):
        return

    has_first_occurrence = _column_exists(inspector, "alert_deduplications", "first_occurrence")
    has_first_violation = _column_exists(inspector, "alert_deduplications", "first_violation_time")

    if has_first_occurrence and not has_first_violation:
        op.alter_column("alert_deduplications", "first_occurrence", new_column_name="first_violation_time")
    elif (not has_first_occurrence) and (not has_first_violation):
        op.execute(sa.text("ALTER TABLE alert_deduplications ADD COLUMN IF NOT EXISTS first_violation_time TIMESTAMPTZ NULL"))

    op.execute(sa.text("ALTER TABLE alert_deduplications ADD COLUMN IF NOT EXISTS first_alert_time TIMESTAMPTZ NULL"))
    op.execute(sa.text("ALTER TABLE alert_deduplications ADD COLUMN IF NOT EXISTS last_alert_time TIMESTAMPTZ NULL"))
    op.execute(sa.text("ALTER TABLE alert_deduplications ADD COLUMN IF NOT EXISTS last_check_time TIMESTAMPTZ NOT NULL DEFAULT now()"))
    op.execute(sa.text("ALTER TABLE alert_deduplications ADD COLUMN IF NOT EXISTS alert_sent_count INTEGER NOT NULL DEFAULT 0"))
    op.execute(sa.text("ALTER TABLE alert_deduplications ADD COLUMN IF NOT EXISTS alert_triggered BOOLEAN NOT NULL DEFAULT FALSE"))
    op.execute(sa.text("ALTER TABLE alert_deduplications ADD COLUMN IF NOT EXISTS recovery_start_time TIMESTAMPTZ NULL"))

    if _column_exists(inspector, "alert_deduplications", "last_occurrence"):
        op.execute(sa.text("UPDATE alert_deduplications SET last_check_time = last_occurrence WHERE last_check_time IS NULL"))
        op.execute(sa.text("ALTER TABLE alert_deduplications DROP COLUMN IF EXISTS last_occurrence"))


def _ensure_suppression_rules(inspector: sa.Inspector) -> None:
    if not _table_exists(inspector, "suppression_rules"):
        op.execute(sa.text(
            """
            CREATE TABLE IF NOT EXISTS suppression_rules (
                id SERIAL PRIMARY KEY,
                resource_type VARCHAR(50) NOT NULL DEFAULT 'general',
                resource_id INTEGER NULL,
                resource_pattern VARCHAR(500) NULL,
                alert_rule_id INTEGER NULL,
                start_time TIMESTAMPTZ NULL,
                end_time TIMESTAMPTZ NULL,
                suppress_alerts BOOLEAN NOT NULL DEFAULT TRUE,
                suppress_notifications BOOLEAN NOT NULL DEFAULT TRUE,
                suppress_ai_analysis BOOLEAN NOT NULL DEFAULT TRUE,
                suppress_log_scan BOOLEAN NOT NULL DEFAULT FALSE,
                reason TEXT NULL,
                created_by VARCHAR(255) NULL,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                match_count INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        ))

    _ensure_index("CREATE INDEX IF NOT EXISTS ix_suppression_rules_resource_type ON suppression_rules (resource_type)")
    _ensure_index("CREATE INDEX IF NOT EXISTS ix_suppression_rules_resource_id ON suppression_rules (resource_id)")
    _ensure_index("CREATE INDEX IF NOT EXISTS ix_suppression_rules_alert_rule_id ON suppression_rules (alert_rule_id)")
    _ensure_index("CREATE INDEX IF NOT EXISTS ix_suppression_rules_is_active ON suppression_rules (is_active)")
    _ensure_index("CREATE INDEX IF NOT EXISTS ix_suppression_rules_start_time ON suppression_rules (start_time)")
    _ensure_index("CREATE INDEX IF NOT EXISTS ix_suppression_rules_end_time ON suppression_rules (end_time)")

    op.execute(sa.text(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_suppression_rules_alert_rule_id'
            ) THEN
                ALTER TABLE suppression_rules
                ADD CONSTRAINT fk_suppression_rules_alert_rule_id
                FOREIGN KEY (alert_rule_id) REFERENCES alert_rules(id);
            END IF;
        END $$;
        """
    ))


def _ensure_custom_runbooks(inspector: sa.Inspector) -> None:
    if not _table_exists(inspector, "custom_runbooks"):
        op.execute(sa.text(
            """
            CREATE TABLE IF NOT EXISTS custom_runbooks (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                trigger_keywords JSON NOT NULL DEFAULT '[]',
                risk_level VARCHAR(20) NOT NULL DEFAULT 'manual',
                steps JSON NOT NULL DEFAULT '[]',
                safety_checks JSON NOT NULL DEFAULT '[]',
                created_by INTEGER NOT NULL,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        ))

    _ensure_index("CREATE UNIQUE INDEX IF NOT EXISTS ix_custom_runbooks_name ON custom_runbooks (name)")


def _ensure_ops_tables(inspector: sa.Inspector) -> None:
    if not _table_exists(inspector, "ops_sessions"):
        op.execute(sa.text(
            """
            CREATE TABLE IF NOT EXISTS ops_sessions (
                id VARCHAR(36) PRIMARY KEY,
                user_id INTEGER NOT NULL,
                title VARCHAR(100) NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'active',
                target_host_id INTEGER NULL,
                token_count INTEGER NOT NULL DEFAULT 0,
                compacted_at TIMESTAMPTZ NULL,
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ DEFAULT now()
            )
            """
        ))
    _ensure_index("CREATE INDEX IF NOT EXISTS ix_ops_sessions_user_id ON ops_sessions (user_id)")

    if not _table_exists(inspector, "ops_messages"):
        op.execute(sa.text(
            """
            CREATE TABLE IF NOT EXISTS ops_messages (
                id VARCHAR(36) PRIMARY KEY,
                session_id VARCHAR(36) NOT NULL REFERENCES ops_sessions(id) ON DELETE CASCADE,
                role VARCHAR(20) NOT NULL,
                msg_type VARCHAR(30) NOT NULL,
                content JSONB NOT NULL,
                tool_call_id VARCHAR(100) NULL,
                compacted BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMPTZ DEFAULT now()
            )
            """
        ))
    _ensure_index("CREATE INDEX IF NOT EXISTS ix_ops_messages_session_id ON ops_messages (session_id)")
    _ensure_index("CREATE INDEX IF NOT EXISTS ix_ops_messages_created_at ON ops_messages (created_at)")


def _ensure_menu_settings(inspector: sa.Inspector) -> None:
    if not _table_exists(inspector, "menu_settings"):
        op.execute(sa.text(
            """
            CREATE TABLE IF NOT EXISTS menu_settings (
                id SERIAL PRIMARY KEY,
                hidden_keys JSONB NOT NULL DEFAULT '[]'::jsonb,
                updated_by INTEGER NULL,
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ DEFAULT now()
            )
            """
        ))


def _ensure_ai_operation_logs(inspector: sa.Inspector) -> None:
    if not _table_exists(inspector, "ai_operation_logs"):
        op.execute(sa.text(
            """
            CREATE TABLE IF NOT EXISTS ai_operation_logs (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                session_id VARCHAR(36) NULL,
                request_id VARCHAR(64) NULL,
                host_id INTEGER NULL,
                host_name VARCHAR(255) NULL,
                command TEXT NOT NULL,
                reason TEXT NULL,
                exit_code INTEGER NULL,
                duration_ms INTEGER NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'unknown',
                created_at TIMESTAMPTZ DEFAULT now()
            )
            """
        ))

    _ensure_index("CREATE INDEX IF NOT EXISTS ix_ai_operation_logs_user_id ON ai_operation_logs (user_id)")
    _ensure_index("CREATE INDEX IF NOT EXISTS ix_ai_operation_logs_session_id ON ai_operation_logs (session_id)")
    _ensure_index("CREATE INDEX IF NOT EXISTS ix_ai_operation_logs_request_id ON ai_operation_logs (request_id)")
    _ensure_index("CREATE INDEX IF NOT EXISTS ix_ai_operation_logs_host_id ON ai_operation_logs (host_id)")
    _ensure_index("CREATE INDEX IF NOT EXISTS ix_ai_operation_logs_status ON ai_operation_logs (status)")
    _ensure_index("CREATE INDEX IF NOT EXISTS ix_ai_operation_logs_created_at ON ai_operation_logs (created_at)")


def _ensure_database_monitor_targets(inspector: sa.Inspector) -> None:
    if not _table_exists(inspector, "database_monitor_targets"):
        op.execute(sa.text(
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
        ))

    _ensure_index("CREATE INDEX IF NOT EXISTS ix_database_monitor_targets_host_id ON database_monitor_targets (host_id)")
    _ensure_index("CREATE INDEX IF NOT EXISTS ix_database_monitor_targets_is_active ON database_monitor_targets (is_active)")
    _ensure_index("CREATE INDEX IF NOT EXISTS ix_database_monitor_targets_host_name ON database_monitor_targets (host_id, name)")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    _ensure_alert_rule_and_dedup_columns(inspector)
    _ensure_suppression_rules(inspector)
    _ensure_custom_runbooks(inspector)
    _ensure_ops_tables(inspector)
    _ensure_menu_settings(inspector)
    _ensure_ai_operation_logs(inspector)
    _ensure_database_monitor_targets(inspector)


def downgrade() -> None:
    # 该迁移用于一次性兜底补齐，不执行 destructive downgrade，避免误删线上结构/数据。
    pass
