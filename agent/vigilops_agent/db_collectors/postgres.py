"""
PostgreSQL 采集器。

指标覆盖：
  - 连接数（总量/活跃/最大/等待）
  - 事务统计（提交/回滚）
  - 慢查询（依赖 pg_stat_statements）
  - 锁等待
  - 缓存命中率
  - 复制延迟
  - 长事务数
  - 连接根因分析（超阈值时触发）

最小权限：GRANT pg_monitor TO monitor_user;（PG 10+）
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from vigilops_agent.config import DatabaseMonitorConfig
from vigilops_agent.db_schema import DBMetrics, SlowQuery
from vigilops_agent.db_collectors.base import AbstractDBCollector

logger = logging.getLogger(__name__)


class PostgreSQLCollector(AbstractDBCollector, db_type="postgres"):
    """PostgreSQL / GaussDB 指标采集器。"""

    def collect(self, cfg: DatabaseMonitorConfig) -> Optional[DBMetrics]:
        try:
            import psycopg2  # type: ignore
        except ImportError:
            logger.warning("psycopg2 not installed, skipping PostgreSQL for %s", cfg.name)
            return None

        conn = None
        cur = None
        try:
            conn = psycopg2.connect(
                host=cfg.host,
                port=cfg.port,
                dbname=cfg.database,
                user=cfg.username,
                password=cfg.password,
                connect_timeout=cfg.connect_timeout,
            )
            conn.autocommit = True
            cur = conn.cursor()

            metrics = DBMetrics(
                db_name=cfg.name or cfg.database,
                db_type="postgres",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

            # --- 连接数 ---
            cur.execute("SELECT count(*) FROM pg_stat_activity;")
            metrics.connections_total = cur.fetchone()[0]

            cur.execute("SELECT count(*) FROM pg_stat_activity WHERE state = 'active';")
            metrics.connections_active = cur.fetchone()[0]

            cur.execute("SHOW max_connections;")
            metrics.connections_max = int(cur.fetchone()[0])

            # 等待连接数（有 wait_event 且非 idle）
            cur.execute(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE wait_event IS NOT NULL AND state != 'idle';"
            )
            waiting = cur.fetchone()[0]

            # --- 数据库大小 ---
            cur.execute("SELECT pg_database_size(current_database());")
            metrics.database_size_mb = round(cur.fetchone()[0] / (1024 * 1024), 2)

            # --- 表数量 ---
            cur.execute(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = 'public';"
            )
            metrics.tables_count = cur.fetchone()[0]

            # --- 事务统计 ---
            cur.execute(
                "SELECT xact_commit, xact_rollback FROM pg_stat_database "
                "WHERE datname = current_database();"
            )
            row = cur.fetchone()
            if row:
                metrics.transactions_committed = row[0]
                metrics.transactions_rolled_back = row[1]

            # --- 慢查询（依赖 pg_stat_statements） ---
            slow_queries_detail = []
            try:
                cur.execute(
                    "SELECT queryid::text, mean_exec_time/1000.0, calls, "
                    "LEFT(query, 200) "
                    "FROM pg_stat_statements "
                    "WHERE mean_exec_time > 1000 "
                    "ORDER BY mean_exec_time DESC LIMIT 10;"
                )
                for r in cur.fetchall():
                    slow_queries_detail.append(SlowQuery(
                        sql_id=str(r[0]),
                        avg_seconds=round(float(r[1]), 3),
                        executions=int(r[2]),
                        sql_text=str(r[3]),
                    ))
                metrics.slow_queries = len(slow_queries_detail)
                metrics.slow_queries_detail = slow_queries_detail
            except Exception as e:
                # pg_stat_statements 未安装时降级
                logger.debug("pg_stat_statements unavailable for %s: %s", cfg.name, e)
                try:
                    cur.execute(
                        "SELECT count(*) FROM pg_stat_activity "
                        "WHERE state = 'active' AND query_start < now() - interval '1 second';"
                    )
                    metrics.slow_queries = cur.fetchone()[0]
                except Exception as e:
                    logger.debug("Slow query fallback failed for %s: %s", cfg.name, e)

            # --- 锁等待 ---
            try:
                cur.execute(
                    "SELECT count(*) FROM pg_locks WHERE NOT granted;"
                )
                metrics.lock_waits = cur.fetchone()[0]
            except Exception as e:
                logger.debug("Lock waits query failed for %s: %s", cfg.name, e)

            # --- 缓存命中率 ---
            try:
                cur.execute(
                    "SELECT ROUND("
                    "  SUM(heap_blks_hit) * 100.0 / NULLIF(SUM(heap_blks_hit + heap_blks_read), 0), 4"
                    ") FROM pg_statio_all_tables;"
                )
                row = cur.fetchone()
                cache_hit = float(row[0]) / 100.0 if row and row[0] else 0.0
            except Exception as e:
                logger.debug("Cache hit ratio query failed for %s: %s", cfg.name, e)
                cache_hit = 0.0

            # --- 复制延迟 ---
            replication_lag_bytes = 0
            try:
                cur.execute(
                    "SELECT COALESCE(MAX("
                    "  pg_wal_lsn_diff(sent_lsn, replay_lsn)"
                    "), 0) FROM pg_stat_replication;"
                )
                row = cur.fetchone()
                replication_lag_bytes = int(row[0]) if row and row[0] else 0
            except Exception as e:
                logger.debug("Replication lag query failed for %s: %s", cfg.name, e)

            # --- 长事务数 ---
            long_running_queries = 0
            try:
                cur.execute(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE state = 'idle in transaction' "
                    "AND xact_start < now() - interval '60 seconds';"
                )
                long_running_queries = cur.fetchone()[0]
            except Exception as e:
                logger.debug("Long running queries check failed for %s: %s", cfg.name, e)

            # --- autovacuum 活跃数 ---
            autovacuum_count = 0
            try:
                cur.execute(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE query ILIKE 'autovacuum:%';"
                )
                autovacuum_count = cur.fetchone()[0]
            except Exception as e:
                logger.debug("Autovacuum count query failed for %s: %s", cfg.name, e)

            metrics.extra = {
                "waiting_connections": waiting,
                "cache_hit_ratio": cache_hit,
                "replication_lag_bytes": replication_lag_bytes,
                "long_running_queries": long_running_queries,
                "autovacuum_count": autovacuum_count,
            }

            # --- 连接根因分析（超阈值时触发） ---
            if (metrics.connections_max > 0
                    and metrics.connections_total / metrics.connections_max
                    >= cfg.connection_threshold):
                metrics.extra["connection_breakdown"] = self._connection_breakdown(cur)

            return metrics

        except Exception as e:
            logger.error("PostgreSQL collection failed for %s: %s", cfg.name, e)
            return None
        finally:
            if cur:
                try:
                    cur.close()
                except Exception:
                    pass
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def _connection_breakdown(self, cur) -> dict:
        """当连接数超阈值时采集连接分布根因数据。"""
        breakdown = {}

        # 按用户分布 Top 10
        try:
            cur.execute(
                "SELECT usename, count(*) cnt FROM pg_stat_activity "
                "GROUP BY usename ORDER BY cnt DESC LIMIT 10;"
            )
            breakdown["by_user"] = [
                {"user": r[0], "count": r[1]} for r in cur.fetchall()
            ]
        except Exception:
            pass

        # 按客户端 IP 分布 Top 10
        try:
            cur.execute(
                "SELECT client_addr, count(*) cnt FROM pg_stat_activity "
                "GROUP BY client_addr ORDER BY cnt DESC LIMIT 10;"
            )
            breakdown["by_client"] = [
                {"client": str(r[0]), "count": r[1]} for r in cur.fetchall()
            ]
        except Exception:
            pass

        # 按应用名分布 Top 10
        try:
            cur.execute(
                "SELECT application_name, count(*) cnt FROM pg_stat_activity "
                "GROUP BY application_name ORDER BY cnt DESC LIMIT 10;"
            )
            breakdown["by_application"] = [
                {"application": r[0], "count": r[1]} for r in cur.fetchall()
            ]
        except Exception:
            pass

        # 连接状态分布
        try:
            cur.execute(
                "SELECT state, count(*) cnt FROM pg_stat_activity "
                "GROUP BY state;"
            )
            breakdown["by_state"] = {r[0]: r[1] for r in cur.fetchall()}
        except Exception:
            pass

        # 最长 idle 连接 Top 10
        try:
            cur.execute(
                "SELECT pid, usename, client_addr, application_name, state, "
                "EXTRACT(EPOCH FROM (now() - state_change))::int AS idle_seconds, "
                "LEFT(query, 100) "
                "FROM pg_stat_activity "
                "WHERE state = 'idle' "
                "ORDER BY idle_seconds DESC LIMIT 10;"
            )
            breakdown["longest_idle"] = [
                {
                    "pid": r[0], "user": r[1], "client": str(r[2]),
                    "application": r[3], "state": r[4],
                    "idle_seconds": r[5], "query": r[6],
                }
                for r in cur.fetchall()
            ]
        except Exception:
            pass

        return breakdown
