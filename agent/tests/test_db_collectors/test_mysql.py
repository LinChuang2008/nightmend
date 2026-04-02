"""MySQL 采集器单元测试（Mock pymysql）。"""
import sys
from unittest.mock import MagicMock, patch
import pytest

from nightmend_agent.config import DatabaseMonitorConfig
from nightmend_agent.db_collectors.mysql import MySQLCollector


def _make_cfg(**kwargs) -> DatabaseMonitorConfig:
    defaults = dict(
        name="test-mysql", type="mysql",
        host="localhost", port=3306,
        database="testdb", username="monitor", password="secret",
        connect_timeout=10, connection_threshold=0.8,
    )
    defaults.update(kwargs)
    return DatabaseMonitorConfig(**defaults)


def _make_status_rows() -> list:
    """模拟 SHOW GLOBAL STATUS 返回的行列表。"""
    return [
        ("Threads_connected", "50"),
        ("Threads_running", "5"),
        ("Queries", "10000"),
        ("Slow_queries", "3"),
        ("Com_commit", "500"),
        ("Com_rollback", "10"),
        ("Innodb_buffer_pool_read_requests", "100000"),
        ("Innodb_buffer_pool_reads", "100"),
        ("Innodb_row_lock_waits", "2"),
        ("Select_scan", "50"),
        ("Created_tmp_tables", "20"),
    ]


class TestMySQLCollector:

    def test_import_error_returns_none(self):
        """pymysql 未安装时返回 None。"""
        collector = MySQLCollector()
        cfg = _make_cfg()
        with patch.dict(sys.modules, {"pymysql": None}):
            result = collector.collect(cfg)
        assert result is None

    def test_basic_metrics_collected(self):
        """基础指标正确采集。"""
        mock_pymysql = MagicMock()
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_pymysql.connect.return_value = mock_conn

        # SHOW GLOBAL STATUS → 返回所有状态行
        # SHOW GLOBAL VARIABLES → max_connections
        # database size fetchone
        # tables_count fetchone
        # deadlocks (INNODB_METRICS)
        # replication (SHOW SLAVE STATUS → None = not a slave)
        # slow queries (performance_schema)
        mock_cur.fetchall.side_effect = [
            _make_status_rows(),  # SHOW GLOBAL STATUS
            [],                   # slow queries from perf schema
        ]
        mock_cur.fetchone.side_effect = [
            ("max_connections", "200"),  # SHOW GLOBAL VARIABLES LIKE 'max_connections'
            (1024 * 1024 * 100,),        # database_size bytes
            (20,),                       # tables_count
            (0,),                        # deadlocks
            None,                        # SHOW SLAVE STATUS → not a slave
        ]

        collector = MySQLCollector()
        cfg = _make_cfg()

        with patch.dict(sys.modules, {"pymysql": mock_pymysql}):
            result = collector.collect(cfg)

        assert result is not None
        assert result.db_type == "mysql"
        assert result.connections_total == 50
        assert result.connections_active == 5
        assert result.connections_max == 200
        assert result.slow_queries == 3
        assert result.transactions_committed == 500
        assert result.transactions_rolled_back == 10
        assert result.lock_waits == 2

        # InnoDB buffer pool hit rate: (100000 - 100) / 100000 = 0.999
        hit_rate = result.extra.get("innodb_buffer_pool_hit_rate", 0)
        assert hit_rate > 0.99

    def test_connection_failure_returns_none(self):
        """连接失败返回 None。"""
        mock_pymysql = MagicMock()
        mock_pymysql.connect.side_effect = Exception("Access denied")

        collector = MySQLCollector()
        cfg = _make_cfg()

        with patch.dict(sys.modules, {"pymysql": mock_pymysql}):
            result = collector.collect(cfg)

        assert result is None

    def test_replication_lag_parsed(self):
        """主从复制延迟正确解析。"""
        mock_pymysql = MagicMock()
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_pymysql.connect.return_value = mock_conn

        mock_cur.fetchall.side_effect = [
            _make_status_rows(),  # SHOW GLOBAL STATUS
            [],                   # slow queries
        ]

        # SHOW SLAVE STATUS 返回一行，模拟 Seconds_Behind_Master
        slave_row = (None,) * 32 + (5,)  # index 32 = Seconds_Behind_Master
        desc_mock = [(name,) for name in
                     ["ignored"] * 32 + ["Seconds_Behind_Master"]]
        mock_cur.fetchone.side_effect = [
            ("max_connections", "200"),  # SHOW GLOBAL VARIABLES LIKE 'max_connections'
            (1024 * 100,),               # db size
            (10,),                       # tables count
            (0,),                        # deadlocks
            slave_row,                   # SHOW SLAVE STATUS
        ]
        mock_cur.description = desc_mock

        collector = MySQLCollector()
        cfg = _make_cfg()

        with patch.dict(sys.modules, {"pymysql": mock_pymysql}):
            result = collector.collect(cfg)

        assert result is not None
        lag = result.extra.get("replication_lag_seconds", -1)
        assert lag == 5

    def test_connection_breakdown_triggered(self):
        """连接数超阈值时触发根因分析。"""
        mock_pymysql = MagicMock()
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_pymysql.connect.return_value = mock_conn

        # 连接数 190/200 = 95% > 80%
        status_rows = [
            ("Threads_connected", "190"),
            ("Threads_running", "100"),
            ("Queries", "5000"),
            ("Slow_queries", "1"),
            ("Com_commit", "100"),
            ("Com_rollback", "2"),
            ("Innodb_buffer_pool_read_requests", "50000"),
            ("Innodb_buffer_pool_reads", "50"),
            ("Innodb_row_lock_waits", "0"),
            ("Select_scan", "10"),
            ("Created_tmp_tables", "5"),
        ]
        mock_cur.fetchall.side_effect = [
            status_rows,                             # SHOW GLOBAL STATUS
            [],                                      # slow queries
            [("root", 100), ("app", 90)],            # by_user
            [("127.0.0.1", 190)],                    # by_client
            [("Sleep", 180), ("Query", 10)],         # by_state
            [],                                      # longest_idle
            [],                                      # lock_waits_detail (exception OK)
        ]
        mock_cur.fetchone.side_effect = [
            ("max_connections", "200"),  # SHOW GLOBAL VARIABLES LIKE 'max_connections'
            (1024,),                     # db size
            (5,),                        # tables count
            (0,),                        # deadlocks
            None,                        # SHOW SLAVE STATUS
        ]

        collector = MySQLCollector()
        cfg = _make_cfg(connection_threshold=0.8)

        with patch.dict(sys.modules, {"pymysql": mock_pymysql}):
            result = collector.collect(cfg)

        assert result is not None
        assert "connection_breakdown" in result.extra
