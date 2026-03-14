"""
MySQL / MariaDB 采集器。

指标覆盖：
  - 连接数（总量/活跃/最大）
  - QPS / 慢查询
  - InnoDB Buffer Pool 命中率
  - 锁等待 / 死锁
  - 主从复制延迟
  - 事务统计（提交/回滚）
  - 慢查询详情（performance_schema）
  - 连接根因分析（超阈值时触发）

最小权限：GRANT PROCESS, REPLICATION CLIENT ON *.* TO monitor@'%';
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from vigilops_agent.config import DatabaseMonitorConfig
from vigilops_agent.db_schema import DBMetrics, SlowQuery
from vigilops_agent.db_collectors.base import AbstractDBCollector

logger = logging.getLogger(__name__)


class MySQLCollector(AbstractDBCollector, db_type="mysql"):
    """MySQL / MariaDB / TiDB 指标采集器。"""

    def collect(self, cfg: DatabaseMonitorConfig) -> Optional[DBMetrics]:
        try:
            import pymysql  # type: ignore
        except ImportError:
            logger.warning("pymysql not installed, skipping MySQL for %s", cfg.name)
            return None

        conn = None
        cur = None
        try:
            conn = pymysql.connect(
                host=cfg.host,
                port=cfg.port,
                database=cfg.database or None,
                user=cfg.username,
                password=cfg.password,
                connect_timeout=cfg.connect_timeout,
            )
            cur = conn.cursor()

            metrics = DBMetrics(
                db_name=cfg.name or cfg.database or cfg.host,
                db_type="mysql",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

            # 批量查询 SHOW STATUS
            status = self._fetch_status(cur)
            variables = self._fetch_variables(cur)

            # --- 连接数 ---
            metrics.connections_total = int(status.get("Threads_connected", 0))
            metrics.connections_active = int(status.get("Threads_running", 0))
            metrics.connections_max = int(variables.get("max_connections", 0))

            # --- QPS / 慢查询 ---
            metrics.qps = float(status.get("Queries", 0))
            metrics.slow_queries = int(status.get("Slow_queries", 0))

            # --- 事务统计 ---
            metrics.transactions_committed = int(status.get("Com_commit", 0))
            metrics.transactions_rolled_back = int(status.get("Com_rollback", 0))

            # --- 数据库大小 ---
            if cfg.database:
                cur.execute(
                    "SELECT SUM(data_length + index_length) "
                    "FROM information_schema.tables WHERE table_schema = %s;",
                    (cfg.database,),
                )
            else:
                cur.execute(
                    "SELECT SUM(data_length + index_length) "
                    "FROM information_schema.tables WHERE table_schema = DATABASE();"
                )
            row = cur.fetchone()
            metrics.database_size_mb = round(float(row[0] or 0) / (1024 * 1024), 2)

            # --- 表数量 ---
            if cfg.database:
                cur.execute(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema = %s;",
                    (cfg.database,),
                )
            else:
                cur.execute(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema = DATABASE();"
                )
            metrics.tables_count = int(cur.fetchone()[0])

            # --- InnoDB Buffer Pool 命中率 ---
            reads = float(status.get("Innodb_buffer_pool_read_requests", 1))
            disk_reads = float(status.get("Innodb_buffer_pool_reads", 0))
            hit_rate = (reads - disk_reads) / reads if reads > 0 else 0.0
            hit_rate = round(max(0.0, min(1.0, hit_rate)), 6)

            # --- 锁等待 / 死锁 ---
            metrics.lock_waits = int(status.get("Innodb_row_lock_waits", 0))
            metrics.deadlocks = self._fetch_deadlocks(cur)

            # --- 复制延迟 ---
            replication_lag = self._fetch_replication_lag(cur)

            # --- 慢查询详情 ---
            slow_detail = self._fetch_slow_queries(cur)
            if slow_detail:
                metrics.slow_queries_detail = slow_detail

            metrics.extra = {
                "innodb_buffer_pool_hit_rate": hit_rate,
                "replication_lag_seconds": replication_lag,
                "full_table_scans": int(status.get("Select_scan", 0)),
                "tmp_tables_created": int(status.get("Created_tmp_tables", 0)),
            }

            # --- 连接根因分析（超阈值时触发） ---
            if (metrics.connections_max > 0
                    and metrics.connections_total / metrics.connections_max
                    >= cfg.connection_threshold):
                metrics.extra["connection_breakdown"] = self._connection_breakdown(cur)

            return metrics

        except Exception as e:
            logger.error("MySQL collection failed for %s: %s", cfg.name, e)
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

    def _fetch_status(self, cur) -> dict:
        """批量获取 SHOW GLOBAL STATUS。"""
        cur.execute("SHOW GLOBAL STATUS;")
        return {row[0]: row[1] for row in cur.fetchall()}

    def _fetch_variables(self, cur) -> dict:
        """获取需要的 GLOBAL VARIABLES。"""
        cur.execute("SHOW GLOBAL VARIABLES LIKE 'max_connections';")
        row = cur.fetchone()
        return {"max_connections": row[1] if row else 0}

    def _fetch_deadlocks(self, cur) -> int:
        """从 information_schema.INNODB_METRICS 获取死锁数。"""
        try:
            cur.execute(
                "SELECT COUNT FROM information_schema.INNODB_METRICS "
                "WHERE NAME = 'lock_deadlocks';"
            )
            row = cur.fetchone()
            return int(row[0]) if row else 0
        except Exception:
            return 0

    def _fetch_replication_lag(self, cur) -> int:
        """获取主从复制延迟（秒），非从库返回 -1。"""
        try:
            # MySQL 8.0.22+ 推荐 SHOW REPLICA STATUS
            try:
                cur.execute("SHOW REPLICA STATUS;")
            except Exception:
                cur.execute("SHOW SLAVE STATUS;")
            row = cur.fetchone()
            if row is None:
                return -1
            # Seconds_Behind_Master 是第 33 列（0-indexed: 32），但列名更可靠
            cur_desc = cur.description
            col_names = [d[0] for d in cur_desc] if cur_desc else []
            if "Seconds_Behind_Master" in col_names:
                val = row[col_names.index("Seconds_Behind_Master")]
                return int(val) if val is not None else -1
            return -1
        except Exception:
            return -1

    def _fetch_slow_queries(self, cur):
        """从 performance_schema 采集 Top 10 慢查询详情。"""
        try:
            cur.execute(
                "SELECT DIGEST, AVG_TIMER_WAIT/1e12, COUNT_STAR, "
                "LEFT(QUERY_SAMPLE_TEXT, 200) "
                "FROM performance_schema.events_statements_summary_by_digest "
                "WHERE AVG_TIMER_WAIT > 1e12 "  # > 1秒
                "ORDER BY AVG_TIMER_WAIT DESC LIMIT 10;"
            )
            result = []
            for r in cur.fetchall():
                result.append(SlowQuery(
                    sql_id=str(r[0] or "")[:32],
                    avg_seconds=round(float(r[1]), 3),
                    executions=int(r[2]),
                    sql_text=str(r[3] or ""),
                ))
            return result
        except Exception:
            return []

    def _connection_breakdown(self, cur) -> dict:
        """当连接数超阈值时采集连接分布根因数据。"""
        breakdown = {}

        # 按用户分布 Top 10
        try:
            cur.execute(
                "SELECT USER, count(*) cnt FROM information_schema.PROCESSLIST "
                "GROUP BY USER ORDER BY cnt DESC LIMIT 10;"
            )
            breakdown["by_user"] = [
                {"user": r[0], "count": r[1]} for r in cur.fetchall()
            ]
        except Exception:
            pass

        # 按 Host/IP 分布 Top 10
        try:
            cur.execute(
                "SELECT SUBSTRING_INDEX(HOST, ':', 1) AS client_host, count(*) cnt "
                "FROM information_schema.PROCESSLIST "
                "GROUP BY client_host ORDER BY cnt DESC LIMIT 10;"
            )
            breakdown["by_client"] = [
                {"client": r[0], "count": r[1]} for r in cur.fetchall()
            ]
        except Exception:
            pass

        # 连接状态分布
        try:
            cur.execute(
                "SELECT COMMAND, count(*) cnt FROM information_schema.PROCESSLIST "
                "GROUP BY COMMAND;"
            )
            breakdown["by_state"] = {r[0]: r[1] for r in cur.fetchall()}
        except Exception:
            pass

        # 长时间 Sleep 连接 Top 10
        try:
            cur.execute(
                "SELECT ID, USER, HOST, DB, COMMAND, TIME, INFO "
                "FROM information_schema.PROCESSLIST "
                "WHERE COMMAND = 'Sleep' "
                "ORDER BY TIME DESC LIMIT 10;"
            )
            breakdown["longest_idle"] = [
                {
                    "pid": r[0], "user": r[1], "host": r[2],
                    "db": r[3], "command": r[4],
                    "idle_seconds": r[5], "query": str(r[6] or "")[:100],
                }
                for r in cur.fetchall()
            ]
        except Exception:
            pass

        # 当前锁等待详情
        try:
            cur.execute(
                "SELECT r.trx_id waiting_trx_id, r.trx_mysql_thread_id waiting_thread, "
                "b.trx_id blocking_trx_id, b.trx_mysql_thread_id blocking_thread, "
                "LEFT(r.trx_query, 100) waiting_query "
                "FROM information_schema.INNODB_TRX r "
                "JOIN information_schema.INNODB_TRX b "
                "  ON b.trx_id = r.trx_wait_started::bigint "
                "LIMIT 10;"
            )
            breakdown["lock_waits_detail"] = [
                {
                    "waiting_trx": r[0], "waiting_thread": r[1],
                    "blocking_trx": r[2], "blocking_thread": r[3],
                    "waiting_query": r[4],
                }
                for r in cur.fetchall()
            ]
        except Exception:
            pass

        return breakdown
