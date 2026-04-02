"""Oracle 采集器单元测试（Mock oracledb + subprocess）。"""
import sys
from unittest.mock import MagicMock, patch
import pytest

from nightmend_agent.config import DatabaseMonitorConfig
from nightmend_agent.db_collectors.oracle import OracleCollector


def _make_cfg(**kwargs) -> DatabaseMonitorConfig:
    defaults = dict(
        name="test-oracle", type="oracle",
        host="192.168.1.100", port=1521,
        username="monitor", password="secret",
        oracle_sid="ORCL", service_name="",
        connect_timeout=10, connection_mode="direct",
        container_name="", oracle_home="",
        connection_threshold=0.8,
    )
    defaults.update(kwargs)
    return DatabaseMonitorConfig(**defaults)


class TestOracleCollector:

    def test_direct_import_error_returns_none(self):
        """oracledb 未安装时直连返回 None。"""
        collector = OracleCollector()
        cfg = _make_cfg(connection_mode="direct")
        with patch.dict(sys.modules, {"oracledb": None}):
            result = collector.collect(cfg)
        assert result is None

    def test_direct_basic_metrics(self):
        """直连模式基础指标采集正确。"""
        mock_oracledb = MagicMock()
        mock_oracledb.is_thin_mode.return_value = True
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_oracledb.connect.return_value = mock_conn

        mock_cur.fetchone.side_effect = [
            (80,),                # connections_total (v$session WHERE type != 'BACKGROUND')
            (20,),                # connections_active
            ("500",),             # max processes
            (10240.5,),           # db_size_mb
            (1,),                 # lock_waits
            (95.0,),              # tablespace_used_pct
        ]
        mock_cur.fetchall.side_effect = [
            [],  # slow queries (v$sql)
        ]

        collector = OracleCollector()
        cfg = _make_cfg(connection_mode="direct")

        with patch.dict(sys.modules, {"oracledb": mock_oracledb}):
            result = collector.collect(cfg)

        assert result is not None
        assert result.db_type == "oracle"
        assert result.connections_total == 80
        assert result.connections_active == 20
        assert result.connections_max == 500
        assert result.lock_waits == 1
        assert result.extra.get("tablespace_used_pct") == 95.0

    def test_auto_mode_fallback_to_docker(self):
        """auto 模式直连失败时降级到 docker。"""
        mock_oracledb = MagicMock()
        mock_oracledb.connect.side_effect = Exception("Connection failed")
        mock_oracledb.is_thin_mode.return_value = True

        collector = OracleCollector()
        cfg = _make_cfg(
            connection_mode="auto",
            container_name="oracle-container",
        )

        with patch.dict(sys.modules, {"oracledb": mock_oracledb}):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    stdout=(
                        "TOTAL_SESSIONS=60\n"
                        "ACTIVE_SESSIONS=15\n"
                        "DB_SIZE_MB=20480.5\n"
                        "TABLESPACE_USED_PCT=70.5\n"
                        "SLOW_QUERIES=2\n"
                    ),
                    returncode=0,
                )
                result = collector.collect(cfg)

        assert result is not None
        assert result.connections_total == 60
        assert result.connections_active == 15
        assert result.slow_queries == 2
        assert result.extra.get("tablespace_used_pct") == 70.5

    def test_docker_mode_no_container_returns_none(self):
        """docker 模式未配置 container_name 时返回 None。"""
        collector = OracleCollector()
        cfg = _make_cfg(connection_mode="docker", container_name="")
        result = collector.collect(cfg)
        assert result is None

    def test_docker_mode_empty_output_returns_none(self):
        """docker exec 返回空输出时返回 None。"""
        collector = OracleCollector()
        cfg = _make_cfg(connection_mode="docker", container_name="oracle-db")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", returncode=1)
            result = collector.collect(cfg)

        assert result is None

    def test_connection_breakdown_triggered_direct(self):
        """直连模式超阈值时触发连接根因分析。"""
        mock_oracledb = MagicMock()
        mock_oracledb.is_thin_mode.return_value = True
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_oracledb.connect.return_value = mock_conn

        # connections_total=450, connections_max=500 → 90% > 80%
        mock_cur.fetchone.side_effect = [
            (450,),    # connections_total
            (200,),    # connections_active
            ("500",),  # max processes
            (5000.0,), # db_size_mb
            (3,),      # lock_waits
            (80.0,),   # tablespace_pct
        ]
        mock_cur.fetchall.side_effect = [
            [],                                   # slow queries
            [("APP_USER", 200), ("SYS", 50)],    # by_user
            [("JDBC", "host1", 300)],             # by_program
            [("INACTIVE", 400), ("ACTIVE", 50)], # by_status
            [],                                   # longest_idle
            [("db file sequential read", 100)],  # wait_events
        ]
        mock_cur.fetchmany.return_value = []

        collector = OracleCollector()
        cfg = _make_cfg(connection_mode="direct", connection_threshold=0.8)

        with patch.dict(sys.modules, {"oracledb": mock_oracledb}):
            result = collector.collect(cfg)

        assert result is not None
        assert "connection_breakdown" in result.extra
        bd = result.extra["connection_breakdown"]
        assert "by_user" in bd
        assert bd["by_user"][0]["user"] == "APP_USER"
