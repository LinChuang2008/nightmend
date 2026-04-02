"""Redis 采集器单元测试（Mock redis-py）。"""
import sys
from unittest.mock import MagicMock, patch
import pytest

from nightmend_agent.config import DatabaseMonitorConfig
from nightmend_agent.db_collectors.redis import RedisCollector


def _make_cfg(**kwargs) -> DatabaseMonitorConfig:
    defaults = dict(
        name="test-redis", type="redis",
        host="127.0.0.1", port=6379,
        password="", redis_mode="single",
        sentinel_master="", connect_timeout=10,
    )
    defaults.update(kwargs)
    return DatabaseMonitorConfig(**defaults)


def _make_info() -> dict:
    """模拟 Redis INFO all 返回的字典。"""
    return {
        "connected_clients": 25,
        "used_memory_rss": 50 * 1024 * 1024,  # 50 MB
        "maxmemory": 100 * 1024 * 1024,        # 100 MB
        "keyspace_hits": 9900,
        "keyspace_misses": 100,
        "evicted_keys": 5,
        "expired_keys": 200,
        "blocked_clients": 2,
        "instantaneous_ops_per_sec": 1000,
        "connected_slaves": 1,
        "repl_backlog_size": 1024 * 1024,
        "aof_rewrite_in_progress": 0,
        "loading": 0,
        "redis_version": "7.0.0",
        "role": "master",
        "uptime_in_seconds": 86400,
        "total_commands_processed": 1000000,
    }


class TestRedisCollector:

    def test_import_error_returns_none(self):
        """redis 未安装时返回 None。"""
        collector = RedisCollector()
        cfg = _make_cfg()
        with patch.dict(sys.modules, {"redis": None}):
            result = collector.collect(cfg)
        assert result is None

    def test_basic_metrics_single_mode(self):
        """单机模式基础指标正确采集。"""
        mock_redis_lib = MagicMock()
        mock_client = MagicMock()
        mock_redis_lib.Redis.return_value = mock_client
        mock_client.info.side_effect = [_make_info(), {}]  # all, keyspace

        collector = RedisCollector()
        cfg = _make_cfg(redis_mode="single")

        with patch.dict(sys.modules, {"redis": mock_redis_lib}):
            result = collector.collect(cfg)

        assert result is not None
        assert result.db_type == "redis"
        assert result.db_name == "test-redis"
        assert result.connections_total == 25
        assert result.qps == 1000.0

        extra = result.extra
        assert extra["used_memory_mb"] == 50.0
        assert extra["maxmemory_ratio"] == 0.5
        assert extra["keyspace_hit_ratio"] == pytest.approx(0.99, abs=0.001)
        assert extra["evicted_keys"] == 5
        assert extra["blocked_clients"] == 2
        assert extra["redis_version"] == "7.0.0"
        assert extra["role"] == "master"
        assert extra["connected_slaves"] == 1

    def test_zero_ops_hit_ratio(self):
        """无 ops 时命中率为 0，不除零。"""
        mock_redis_lib = MagicMock()
        mock_client = MagicMock()
        mock_redis_lib.Redis.return_value = mock_client

        info = _make_info()
        info["keyspace_hits"] = 0
        info["keyspace_misses"] = 0
        mock_client.info.side_effect = [info, {}]

        collector = RedisCollector()
        cfg = _make_cfg()

        with patch.dict(sys.modules, {"redis": mock_redis_lib}):
            result = collector.collect(cfg)

        assert result is not None
        assert result.extra["keyspace_hit_ratio"] == 0.0

    def test_connection_failure_returns_none(self):
        """连接失败返回 None。"""
        mock_redis_lib = MagicMock()
        mock_client = MagicMock()
        mock_redis_lib.Redis.return_value = mock_client
        mock_client.info.side_effect = Exception("Connection refused")

        collector = RedisCollector()
        cfg = _make_cfg()

        with patch.dict(sys.modules, {"redis": mock_redis_lib}):
            result = collector.collect(cfg)

        assert result is None

    def test_keyspace_keys_counted(self):
        """keyspace 中的 key 数量正确累加。"""
        mock_redis_lib = MagicMock()
        mock_client = MagicMock()
        mock_redis_lib.Redis.return_value = mock_client

        keyspace = {
            "db0": {"keys": 1000, "expires": 100, "avg_ttl": 0},
            "db1": {"keys": 500, "expires": 50, "avg_ttl": 0},
        }
        mock_client.info.side_effect = [_make_info(), keyspace]

        collector = RedisCollector()
        cfg = _make_cfg()

        with patch.dict(sys.modules, {"redis": mock_redis_lib}):
            result = collector.collect(cfg)

        assert result is not None
        assert result.extra["total_keys"] == 1500

    def test_sentinel_mode_creates_sentinel_client(self):
        """sentinel 模式下使用 Sentinel 客户端。"""
        mock_redis_lib = MagicMock()
        mock_sentinel_instance = MagicMock()
        mock_master_client = MagicMock()
        mock_redis_lib.sentinel.Sentinel.return_value = mock_sentinel_instance
        mock_sentinel_instance.master_for.return_value = mock_master_client
        mock_master_client.info.side_effect = [_make_info(), {}]

        collector = RedisCollector()
        cfg = _make_cfg(redis_mode="sentinel", sentinel_master="mymaster")

        with patch.dict(sys.modules, {
            "redis": mock_redis_lib,
            "redis.sentinel": mock_redis_lib.sentinel,
        }):
            result = collector.collect(cfg)

        mock_redis_lib.sentinel.Sentinel.assert_called_once()
        mock_sentinel_instance.master_for.assert_called_once_with("mymaster")


class TestDBCollectorDispatch:
    """测试顶层 collect_db_metrics 分派到 Redis。"""

    def test_dispatch_redis(self):
        """collect_db_metrics 正确分派到 RedisCollector。"""
        from nightmend_agent.db_collector import collect_db_metrics

        mock_redis_lib = MagicMock()
        mock_client = MagicMock()
        mock_redis_lib.Redis.return_value = mock_client
        mock_client.info.side_effect = [_make_info(), {}]

        cfg = _make_cfg()
        with patch.dict(sys.modules, {"redis": mock_redis_lib}):
            result = collect_db_metrics(cfg)

        assert result is not None
        assert result["db_type"] == "redis"
        assert "used_memory_mb" in result["extra"]

    def test_dispatch_unknown_type_returns_none(self):
        """未知 type 返回 None 不崩溃。"""
        from nightmend_agent.db_collector import collect_db_metrics
        cfg = _make_cfg(type="unknown_database_xyz")
        result = collect_db_metrics(cfg)
        assert result is None
