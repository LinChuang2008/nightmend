"""PostgreSQL 采集器单元测试（Mock psycopg2）。"""
import sys
from unittest.mock import MagicMock, patch, call
import pytest

from nightmend_agent.config import DatabaseMonitorConfig
from nightmend_agent.db_collectors.postgres import PostgreSQLCollector
from nightmend_agent.db_schema import DBMetrics


def _make_cfg(**kwargs) -> DatabaseMonitorConfig:
    defaults = dict(
        name="test-pg", type="postgres",
        host="localhost", port=5432,
        database="testdb", username="monitor", password="secret",
        connect_timeout=10, connection_threshold=0.8,
    )
    defaults.update(kwargs)
    return DatabaseMonitorConfig(**defaults)


def _make_cursor(rows_map: dict) -> MagicMock:
    """构造一个可按 execute 调用顺序返回不同结果的 cursor mock。"""
    cur = MagicMock()
    # 用 side_effect 列表模拟顺序调用
    cur.fetchone.side_effect = list(rows_map.values())
    cur.fetchall.return_value = []
    return cur


class TestPostgreSQLCollector:

    def test_import_error_returns_none(self):
        """psycopg2 未安装时返回 None，不崩溃。"""
        collector = PostgreSQLCollector()
        cfg = _make_cfg()
        with patch.dict(sys.modules, {"psycopg2": None}):
            result = collector.collect(cfg)
        assert result is None

    def test_basic_metrics_collected(self):
        """正常采集返回 DBMetrics 对象且字段正确。"""
        mock_psycopg2 = MagicMock()
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_psycopg2.connect.return_value = mock_conn

        # 按 execute 调用顺序设置 fetchone 返回值
        mock_cur.fetchone.side_effect = [
            (50,),        # connections_total
            (10,),        # connections_active
            ("200",),     # max_connections (SHOW max_connections)
            (5,),         # waiting connections (wait_event IS NOT NULL)
            (1024 * 1024 * 5,),  # database_size bytes
            (30,),        # tables_count
            (1000, 50),   # xact_commit, xact_rollback
            (2,),         # lock_waits
            (None,),      # cache_hit_ratio (NULL → 0)
            (0,),         # replication_lag
            (1,),         # long_running_queries
            (0,),         # autovacuum_count
        ]
        mock_cur.fetchall.return_value = []  # 慢查询返回空

        collector = PostgreSQLCollector()
        cfg = _make_cfg()

        with patch.dict(sys.modules, {"psycopg2": mock_psycopg2}):
            result = collector.collect(cfg)

        assert result is not None
        assert result.db_type == "postgres"
        assert result.db_name == "test-pg"
        assert result.connections_total == 50
        assert result.connections_active == 10
        assert result.connections_max == 200
        assert result.lock_waits == 2
        assert result.transactions_committed == 1000
        assert result.transactions_rolled_back == 50

    def test_connection_failure_returns_none(self):
        """连接异常时返回 None。"""
        mock_psycopg2 = MagicMock()
        mock_psycopg2.connect.side_effect = Exception("Connection refused")

        collector = PostgreSQLCollector()
        cfg = _make_cfg()

        with patch.dict(sys.modules, {"psycopg2": mock_psycopg2}):
            result = collector.collect(cfg)

        assert result is None

    def test_connection_breakdown_triggered_above_threshold(self):
        """连接数超阈值时 extra 中包含 connection_breakdown。"""
        mock_psycopg2 = MagicMock()
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_psycopg2.connect.return_value = mock_conn

        # connections_total=180, connections_max=200 → 90% > 80%
        mock_cur.fetchone.side_effect = [
            (180,),       # connections_total
            (100,),       # connections_active
            ("200",),     # max_connections (SHOW)
            (20,),        # waiting
            (1024 * 1024,),  # db size bytes
            (10,),        # tables_count
            (500, 10),    # xact_commit, rollback
            (5,),         # lock_waits
            (None,),      # cache_hit_ratio
            (0,),         # replication_lag
            (0,),         # long_running_queries
            (0,),         # autovacuum
        ]
        # connection_breakdown queries
        mock_cur.fetchall.side_effect = [
            [],  # slow queries (pg_stat_statements)
            [("user1", 100), ("user2", 80)],  # by_user
            [("127.0.0.1", 90)],              # by_client
            [("myapp", 180)],                 # by_application
            [("active", 100), ("idle", 80)],  # by_state
            [],                               # longest_idle
        ]

        collector = PostgreSQLCollector()
        cfg = _make_cfg(connection_threshold=0.8)

        with patch.dict(sys.modules, {"psycopg2": mock_psycopg2}):
            result = collector.collect(cfg)

        assert result is not None
        assert "connection_breakdown" in result.extra
        bd = result.extra["connection_breakdown"]
        assert "by_user" in bd
        assert bd["by_user"][0]["user"] == "user1"

    def test_slow_queries_fallback_when_no_pg_stat_statements(self):
        """pg_stat_statements 不可用时降级不崩溃。"""
        mock_psycopg2 = MagicMock()
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_psycopg2.connect.return_value = mock_conn

        mock_cur.fetchone.side_effect = [
            (10,),      # connections_total
            (2,),       # connections_active
            ("100",),   # max_connections
            (5,),       # waiting
            (1024,),    # db size
            (5,),       # tables
            (100, 5),   # xact
            (0,),       # lock_waits
            (None,),    # cache hit
            (0,),       # replication
            (0,),       # long_running
            (0,),       # autovacuum
            (3,),       # fallback slow count
        ]

        # pg_stat_statements 查询抛异常
        def fetchall_side():
            raise Exception("relation pg_stat_statements does not exist")

        mock_cur.fetchall.side_effect = fetchall_side

        collector = PostgreSQLCollector()
        cfg = _make_cfg()

        with patch.dict(sys.modules, {"psycopg2": mock_psycopg2}):
            result = collector.collect(cfg)

        # 不崩溃即可，slow_queries 使用降级路径
        assert result is not None
