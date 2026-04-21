"""add query_expr + for_duration to alert_rules

Revision ID: 033_add_alert_rule_query_expr
Revises: 032_add_host_status_heartbeat_index
Create Date: 2026-04-21

背景 (Context):
    Prometheus 集成 Milestone 2：允许 AlertRule 使用原生 PromQL 表达式触发告警。
    - query_expr: PromQL 表达式（如 rate(http_requests_total{status=~"5.."}[5m]) > 0.1）
    - for_duration_seconds: 表达式持续满足的时间，映射到 Prometheus 规则的 for 字段
    - prom_rule_synced_at: 上次同步到 /etc/prometheus/rules/*.yml 的时间戳

向后兼容：所有字段可空；既有 metric+threshold 规则保持原路径执行。
"""

from alembic import op
import sqlalchemy as sa


revision = "033_add_alert_rule_query_expr"
down_revision = "032_add_host_status_heartbeat_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "alert_rules",
        sa.Column("query_expr", sa.Text(), nullable=True),
    )
    op.add_column(
        "alert_rules",
        sa.Column("for_duration_seconds", sa.Integer(), nullable=True),
    )
    op.add_column(
        "alert_rules",
        sa.Column("prom_rule_synced_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("alert_rules", "prom_rule_synced_at")
    op.drop_column("alert_rules", "for_duration_seconds")
    op.drop_column("alert_rules", "query_expr")
