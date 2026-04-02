"""
Redis 采集器。

支持单机、Sentinel、Cluster 三种模式。
通过 INFO all 命令采集核心指标。

配置示例：
  type: redis
  host: 127.0.0.1
  port: 6379
  password: xxx
  redis_mode: single       # single | sentinel | cluster
  sentinel_master: mymaster  # Sentinel 模式下 master 名称

最小权限：AUTH 密码认证即可，无需特殊权限。
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from nightmend_agent.config import DatabaseMonitorConfig
from nightmend_agent.db_schema import DBMetrics
from nightmend_agent.db_collectors.base import AbstractDBCollector

logger = logging.getLogger(__name__)


class RedisCollector(AbstractDBCollector, db_type="redis"):
    """Redis / Valkey 指标采集器（支持单机/Sentinel/Cluster）。"""

    def collect(self, cfg: DatabaseMonitorConfig) -> Optional[DBMetrics]:
        try:
            import redis as redis_lib  # type: ignore
        except ImportError:
            logger.warning("redis-py not installed, skipping Redis for %s", cfg.name)
            return None

        client = None
        try:
            client = self._create_client(cfg, redis_lib)
            info = client.info("all")
            keyspace = client.info("keyspace")

            return self._parse_metrics(cfg, info, keyspace)

        except Exception as e:
            logger.error("Redis collection failed for %s: %s", cfg.name, e)
            return None
        finally:
            if client:
                try:
                    client.close()
                except Exception:
                    pass

    def _create_client(self, cfg: DatabaseMonitorConfig, redis_lib):
        """根据 redis_mode 创建对应的客户端。"""
        mode = (cfg.redis_mode or "single").lower()
        common = dict(
            password=cfg.password or None,
            socket_timeout=cfg.connect_timeout,
            socket_connect_timeout=cfg.connect_timeout,
            decode_responses=True,
        )

        if mode == "sentinel":
            sentinel = redis_lib.sentinel.Sentinel(
                [(cfg.host, cfg.port)],
                sentinel_kwargs=common,
                **common,
            )
            master_name = cfg.sentinel_master or "mymaster"
            return sentinel.master_for(master_name)

        elif mode == "cluster":
            return redis_lib.cluster.RedisCluster(
                host=cfg.host,
                port=cfg.port or 6379,
                **common,
            )

        else:  # single（默认）
            return redis_lib.Redis(
                host=cfg.host,
                port=cfg.port or 6379,
                **common,
            )

    def _parse_metrics(self, cfg: DatabaseMonitorConfig, info: dict, keyspace: dict) -> DBMetrics:
        """从 INFO all 输出解析指标。"""
        # 命中率
        hits = int(info.get("keyspace_hits", 0))
        misses = int(info.get("keyspace_misses", 0))
        total_ops = hits + misses
        hit_ratio = round(hits / total_ops, 6) if total_ops > 0 else 0.0

        # 内存使用
        used_memory_bytes = int(info.get("used_memory_rss", 0))
        used_memory_mb = round(used_memory_bytes / (1024 * 1024), 2)
        maxmemory = int(info.get("maxmemory", 0))
        maxmemory_ratio = (
            round(used_memory_bytes / maxmemory, 4) if maxmemory > 0 else 0.0
        )

        # 总 key 数（all dbs 累加）
        total_keys = sum(
            v.get("keys", 0)
            for v in keyspace.values()
            if isinstance(v, dict)
        )

        # 主从复制
        connected_slaves = int(info.get("connected_slaves", 0))
        repl_backlog_size = int(info.get("repl_backlog_size", 0))

        # AOF / RDB 状态
        aof_rewrite = int(info.get("aof_rewrite_in_progress", 0))
        rdb_loading = int(info.get("loading", 0))

        metrics = DBMetrics(
            db_name=cfg.name or f"{cfg.host}:{cfg.port}",
            db_type="redis",
            timestamp=datetime.now(timezone.utc).isoformat(),
            connections_total=int(info.get("connected_clients", 0)),
            connections_active=int(info.get("connected_clients", 0)),
            qps=float(info.get("instantaneous_ops_per_sec", 0)),
            extra={
                "used_memory_mb": used_memory_mb,
                "maxmemory_ratio": maxmemory_ratio,
                "keyspace_hit_ratio": hit_ratio,
                "keyspace_hits": hits,
                "keyspace_misses": misses,
                "evicted_keys": int(info.get("evicted_keys", 0)),
                "expired_keys": int(info.get("expired_keys", 0)),
                "blocked_clients": int(info.get("blocked_clients", 0)),
                "total_keys": total_keys,
                "connected_slaves": connected_slaves,
                "repl_backlog_size": repl_backlog_size,
                "aof_rewrite_in_progress": aof_rewrite,
                "rdb_loading": rdb_loading,
                "redis_version": info.get("redis_version", ""),
                "role": info.get("role", ""),
                "uptime_in_seconds": int(info.get("uptime_in_seconds", 0)),
                "total_commands_processed": int(info.get("total_commands_processed", 0)),
            },
        )
        return metrics
