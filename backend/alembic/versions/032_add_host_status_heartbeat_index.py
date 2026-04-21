"""add composite index on hosts(status, last_heartbeat)

Revision ID: 032_add_host_status_heartbeat_index
Revises: 031_add_ops_session_usage_fields
Create Date: 2026-04-21

背景 (Context):
    offline_detector 每 60s 扫描 hosts 表。原实现仅用 hostname 单列索引，
    当主机数 >1k 时 `WHERE status = 'online'` + `last_heartbeat < cutoff`
    退化为 seq scan。加复合索引后走 index range scan，扫描成本从 O(N)
    降为 O(online_stale)。

方案 (Approach):
    使用 PostgreSQL 的 CONCURRENTLY 在生产大表上无锁建索引。
    若在 SQLite 测试环境会 fallback 到普通 CREATE INDEX（仍然是 O(log N) 收益）。
"""

from alembic import op


revision = "032_add_host_status_heartbeat_index"
down_revision = "031_add_ops_session_usage_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 判断方言：Postgres 用 CONCURRENTLY 避免锁表；其他方言走普通 create_index。
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # CONCURRENTLY 必须在 autocommit 之外，且不能进事务块。
        # alembic 默认 transactional_ddl=True，需要显式 execute 裸 SQL 并把事务提交掉。
        with op.get_context().autocommit_block():
            op.execute(
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
                "ix_hosts_status_last_heartbeat "
                "ON hosts (status, last_heartbeat)"
            )
    else:
        op.create_index(
            "ix_hosts_status_last_heartbeat",
            "hosts",
            ["status", "last_heartbeat"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_hosts_status_last_heartbeat")
    else:
        op.drop_index("ix_hosts_status_last_heartbeat", table_name="hosts")
