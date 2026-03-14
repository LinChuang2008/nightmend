"""
Oracle 采集器（双模式：直连 + docker exec）。

connection_mode:
  "direct"  → python-oracledb 直连（推荐）
  "docker"  → docker exec + sqlplus（兼容旧容器部署）
  "auto"    → 优先直连，失败则降级 docker（默认）

直连模式：
  - Oracle 12c+ 使用 Thin 模式（无需 Instant Client）
  - Oracle 11g 需要 Thick 模式（需 Instant Client，通过 oracle_home 配置）

最小权限：
  GRANT SELECT ON v_$session TO monitor;
  GRANT SELECT ON v_$sql TO monitor;
  GRANT SELECT ON dba_data_files TO monitor;
  GRANT SELECT ON dba_tablespace_usage_metrics TO monitor;
  GRANT SELECT ON v_$lock TO monitor;
"""
import logging
import re
import subprocess
from datetime import datetime, timezone
from typing import Dict, List, Optional

from vigilops_agent.config import DatabaseMonitorConfig
from vigilops_agent.db_schema import DBMetrics, SlowQuery
from vigilops_agent.db_collectors.base import AbstractDBCollector

logger = logging.getLogger(__name__)


class OracleCollector(AbstractDBCollector, db_type="oracle"):
    """Oracle 11g/12c/19c 指标采集器（支持直连和 docker exec 双模式）。"""

    def collect(self, cfg: DatabaseMonitorConfig) -> Optional[DBMetrics]:
        mode = cfg.connection_mode.lower() if cfg.connection_mode else "auto"

        if mode == "direct":
            return self._collect_direct(cfg)
        elif mode == "docker":
            return self._collect_docker(cfg)
        else:  # auto
            result = self._collect_direct(cfg)
            if result is None and cfg.container_name:
                logger.info("Oracle direct connection failed for %s, falling back to docker", cfg.name)
                result = self._collect_docker(cfg)
            return result

    # ─────────────────────────── 直连模式 ───────────────────────────

    def _collect_direct(self, cfg: DatabaseMonitorConfig) -> Optional[DBMetrics]:
        """使用 python-oracledb 直连采集。"""
        try:
            import oracledb  # type: ignore
        except ImportError:
            logger.warning(
                "oracledb not installed (pip install oracledb), "
                "skipping Oracle direct connection for %s", cfg.name
            )
            return None

        try:
            # 构建 DSN
            sid = cfg.oracle_sid or cfg.database
            svc = cfg.service_name
            if svc:
                dsn = f"{cfg.host}:{cfg.port}/{svc}"
            elif sid:
                dsn = f"{cfg.host}:{cfg.port}/{sid}"
            else:
                dsn = f"{cfg.host}:{cfg.port}"

            # 11g Thick 模式（需要 oracle_home / Instant Client）
            if cfg.oracle_home and not oracledb.is_thin_mode():
                try:
                    oracledb.init_oracle_client(lib_dir=cfg.oracle_home)
                except Exception as e:
                    logger.debug("Oracle thick mode init skipped: %s", e)

            conn = oracledb.connect(
                user=cfg.username,
                password=cfg.password,
                dsn=dsn,
            )
            cur = conn.cursor()

            metrics = DBMetrics(
                db_name=cfg.name or svc or sid or cfg.host,
                db_type="oracle",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

            # --- 连接数 ---
            cur.execute(
                "SELECT count(*) FROM v$session WHERE type != 'BACKGROUND'"
            )
            metrics.connections_total = cur.fetchone()[0]

            cur.execute(
                "SELECT count(*) FROM v$session "
                "WHERE type != 'BACKGROUND' AND status = 'ACTIVE'"
            )
            metrics.connections_active = cur.fetchone()[0]

            # processes 参数作为最大连接数上限
            try:
                cur.execute(
                    "SELECT value FROM v$parameter WHERE name = 'processes'"
                )
                row = cur.fetchone()
                metrics.connections_max = int(row[0]) if row else 0
            except Exception as e:
                logger.debug("Failed to collect max connections: %s", e)

            # --- 数据库大小 ---
            cur.execute(
                "SELECT ROUND(SUM(bytes)/1024/1024, 2) FROM dba_data_files"
            )
            row = cur.fetchone()
            metrics.database_size_mb = float(row[0] or 0)

            # --- 慢查询 ---
            slow_detail = self._fetch_slow_queries_direct(cur)
            metrics.slow_queries = len(slow_detail)
            metrics.slow_queries_detail = slow_detail

            # --- 锁等待 ---
            try:
                cur.execute(
                    "SELECT count(*) FROM v$lock WHERE block = 1"
                )
                metrics.lock_waits = cur.fetchone()[0]
            except Exception as e:
                logger.debug("Failed to collect lock waits: %s", e)

            # --- 表空间使用率 ---
            tablespace_pct = self._fetch_tablespace(cur)

            # --- 连接根因分析 ---
            extra = {"tablespace_used_pct": tablespace_pct}
            if (metrics.connections_max > 0
                    and metrics.connections_total / metrics.connections_max
                    >= cfg.connection_threshold):
                extra["connection_breakdown"] = self._connection_breakdown_direct(cur)

            metrics.extra = extra

            cur.close()
            conn.close()
            return metrics

        except Exception as e:
            logger.error("Oracle direct connection failed for %s: %s", cfg.name, e)
            return None

    def _fetch_slow_queries_direct(self, cur) -> List[SlowQuery]:
        """采集 Top 10 慢查询（v$sql）。"""
        try:
            cur.execute(
                "SELECT sql_id, "
                "ROUND(elapsed_time/GREATEST(executions,1)/1000000, 2), "
                "executions, SUBSTR(sql_text, 1, 200) "
                "FROM ("
                "  SELECT sql_id, elapsed_time, executions, sql_text "
                "  FROM v$sql WHERE executions > 0 "
                "  ORDER BY elapsed_time/executions DESC"
                ") WHERE ROWNUM <= 10"
            )
            result = []
            for r in cur.fetchall():
                result.append(SlowQuery(
                    sql_id=str(r[0]),
                    avg_seconds=float(r[1] or 0),
                    executions=int(r[2] or 0),
                    sql_text=str(r[3] or ""),
                ))
            return result
        except Exception as e:
            logger.debug("Failed to collect slow queries: %s", e)
            return []

    def _fetch_tablespace(self, cur) -> float:
        """获取最大表空间使用率（%）。"""
        # Oracle 11g 无 dba_tablespace_usage_metrics，降级到 dba_free_space
        try:
            cur.execute(
                "SELECT ROUND(MAX(used_percent), 2) "
                "FROM dba_tablespace_usage_metrics"
            )
            row = cur.fetchone()
            return float(row[0] or 0)
        except Exception as e:
            logger.debug("Failed to collect tablespace from usage_metrics: %s", e)
        try:
            cur.execute(
                "SELECT ROUND("
                "  (1 - SUM(f.bytes)/SUM(t.bytes)) * 100, 2"
                ") FROM dba_tablespaces t, dba_free_space f "
                "WHERE t.tablespace_name = f.tablespace_name(+)"
            )
            row = cur.fetchone()
            return float(row[0] or 0)
        except Exception as e:
            logger.debug("Failed to collect tablespace from dba_free_space: %s", e)
            return 0.0

    def _connection_breakdown_direct(self, cur) -> dict:
        """Oracle 连接数高时的根因分析（PM 文档第 8 节 5 个查询）。"""
        breakdown = {}

        # 1. 按用户名分布
        try:
            cur.execute(
                "SELECT username, count(*) cnt FROM v$session "
                "WHERE type != 'BACKGROUND' "
                "GROUP BY username ORDER BY cnt DESC FETCH FIRST 10 ROWS ONLY"
            )
            breakdown["by_user"] = [
                {"user": r[0], "count": r[1]} for r in cur.fetchall()
            ]
        except Exception as e:
            logger.debug("Failed to collect by_user (FETCH FIRST): %s", e)
            try:
                cur.execute(
                    "SELECT username, count(*) cnt FROM v$session "
                    "WHERE type != 'BACKGROUND' "
                    "GROUP BY username ORDER BY cnt DESC"
                )
                rows = cur.fetchmany(10)
                breakdown["by_user"] = [{"user": r[0], "count": r[1]} for r in rows]
            except Exception as e:
                logger.debug("Failed to collect by_user (fallback): %s", e)

        # 2. 按程序/应用分布
        try:
            cur.execute(
                "SELECT program, machine, count(*) cnt FROM v$session "
                "WHERE type != 'BACKGROUND' "
                "GROUP BY program, machine ORDER BY cnt DESC FETCH FIRST 10 ROWS ONLY"
            )
            breakdown["by_program"] = [
                {"program": r[0], "machine": r[1], "count": r[2]}
                for r in cur.fetchall()
            ]
        except Exception as e:
            logger.debug("Failed to collect by_program (FETCH FIRST): %s", e)
            try:
                cur.execute(
                    "SELECT program, machine, count(*) cnt FROM v$session "
                    "WHERE type != 'BACKGROUND' "
                    "GROUP BY program, machine ORDER BY cnt DESC"
                )
                rows = cur.fetchmany(10)
                breakdown["by_program"] = [
                    {"program": r[0], "machine": r[1], "count": r[2]} for r in rows
                ]
            except Exception as e:
                logger.debug("Failed to collect by_program (fallback): %s", e)

        # 3. 连接状态分布
        try:
            cur.execute(
                "SELECT status, count(*) cnt FROM v$session "
                "WHERE type != 'BACKGROUND' GROUP BY status"
            )
            breakdown["by_status"] = {r[0]: r[1] for r in cur.fetchall()}
        except Exception as e:
            logger.debug("Failed to collect by_status: %s", e)

        # 4. 长时间 INACTIVE 连接（idle 堆积）
        try:
            cur.execute(
                "SELECT sid, serial#, username, program, machine, "
                "ROUND((SYSDATE - logon_time)*24*60) login_minutes, "
                "ROUND(last_call_et/60) idle_minutes "
                "FROM v$session WHERE status = 'INACTIVE' AND type != 'BACKGROUND' "
                "ORDER BY idle_minutes DESC FETCH FIRST 10 ROWS ONLY"
            )
            breakdown["longest_idle"] = [
                {
                    "sid": r[0], "serial": r[1], "user": r[2],
                    "program": r[3], "machine": r[4],
                    "login_minutes": r[5], "idle_minutes": r[6],
                }
                for r in cur.fetchall()
            ]
        except Exception as e:
            logger.debug("Failed to collect longest_idle (FETCH FIRST): %s", e)
            try:
                cur.execute(
                    "SELECT sid, serial#, username, program, machine, "
                    "ROUND((SYSDATE - logon_time)*24*60) login_minutes, "
                    "ROUND(last_call_et/60) idle_minutes "
                    "FROM v$session WHERE status = 'INACTIVE' AND type != 'BACKGROUND' "
                    "ORDER BY idle_minutes DESC"
                )
                rows = cur.fetchmany(10)
                breakdown["longest_idle"] = [
                    {
                        "sid": r[0], "serial": r[1], "user": r[2],
                        "program": r[3], "machine": r[4],
                        "login_minutes": r[5], "idle_minutes": r[6],
                    }
                    for r in rows
                ]
            except Exception as e:
                logger.debug("Failed to collect longest_idle (fallback): %s", e)

        # 5. 等待事件分布（Oracle 11g 特有：为什么连接在等）
        try:
            cur.execute(
                "SELECT event, count(*) cnt FROM v$session "
                "WHERE wait_class != 'Idle' AND type != 'BACKGROUND' "
                "GROUP BY event ORDER BY cnt DESC FETCH FIRST 10 ROWS ONLY"
            )
            breakdown["wait_events"] = [
                {"event": r[0], "count": r[1]} for r in cur.fetchall()
            ]
        except Exception as e:
            logger.debug("Failed to collect wait_events (FETCH FIRST): %s", e)
            try:
                cur.execute(
                    "SELECT event, count(*) cnt FROM v$session "
                    "WHERE wait_class != 'Idle' AND type != 'BACKGROUND' "
                    "GROUP BY event ORDER BY cnt DESC"
                )
                rows = cur.fetchmany(10)
                breakdown["wait_events"] = [{"event": r[0], "count": r[1]} for r in rows]
            except Exception as e:
                logger.debug("Failed to collect wait_events (fallback): %s", e)

        return breakdown

    # ─────────────────────────── Docker exec 模式 ───────────────────────────

    def _collect_docker(self, cfg: DatabaseMonitorConfig) -> Optional[DBMetrics]:
        """使用 docker exec + sqlplus 采集（保留现有实现）。"""
        container = cfg.container_name
        if not container:
            logger.warning(
                "Oracle docker mode requires container_name for %s", cfg.name
            )
            return None

        if cfg.oracle_home:
            oracle_env = (
                f"export ORACLE_HOME={cfg.oracle_home}; "
                f"export ORACLE_SID={cfg.oracle_sid}; "
                f"export PATH=$ORACLE_HOME/bin:$PATH; "
            )
        else:
            oracle_env = "source /home/oracle/.bash_profile 2>/dev/null; "

        sql_script = (
            "SET PAGESIZE 0 FEEDBACK OFF VERIFY OFF HEADING OFF ECHO OFF\n"
            "SELECT 'TOTAL_SESSIONS=' || count(*) FROM v$session;\n"
            "SELECT 'ACTIVE_SESSIONS=' || count(*) FROM v$session WHERE status = 'ACTIVE';\n"
            "SELECT 'DB_SIZE_MB=' || ROUND(SUM(bytes)/1024/1024, 2) FROM dba_data_files;\n"
            "SELECT 'TABLESPACE_USED_PCT=' || ROUND(MAX(used_percent), 2) "
            "FROM dba_tablespace_usage_metrics;\n"
            "SELECT 'SLOW_QUERIES=' || count(*) FROM v$sql "
            "WHERE elapsed_time/GREATEST(executions,1) > 5000000 AND executions > 0;\n"
            "EXIT;\n"
        )

        bash_cmd = (
            oracle_env
            + "printf '%s' '"
            + sql_script.replace("'", "'\\''")
            + "' | sqlplus -s / as sysdba"
        )
        cmd = ["docker", "exec", container, "bash", "-c", bash_cmd]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            output = result.stdout
        except subprocess.TimeoutExpired:
            logger.error("Oracle sqlplus timed out for %s", cfg.name)
            return None
        except Exception as e:
            logger.error("Oracle docker collection failed for %s: %s", cfg.name, e)
            return None

        values: Dict[str, str] = {}
        for line in output.splitlines():
            line = line.strip()
            if "=" in line:
                key, _, val = line.partition("=")
                key = key.strip()
                if key in (
                    "TOTAL_SESSIONS", "ACTIVE_SESSIONS",
                    "DB_SIZE_MB", "TABLESPACE_USED_PCT", "SLOW_QUERIES",
                ):
                    values[key] = val.strip()

        if not values:
            logger.error(
                "Oracle: no metrics parsed from sqlplus output for %s", cfg.name
            )
            return None

        def _int(k: str, default: int = 0) -> int:
            try:
                return int(values.get(k, str(default)))
            except (ValueError, TypeError):
                return default

        def _float(k: str, default: float = 0.0) -> float:
            try:
                return float(values.get(k, str(default)))
            except (ValueError, TypeError):
                return default

        slow_queries_detail = self._collect_docker_slow_queries(container, oracle_env)

        metrics = DBMetrics(
            db_name=cfg.name or cfg.database or cfg.oracle_sid,
            db_type="oracle",
            timestamp=datetime.now(timezone.utc).isoformat(),
            connections_total=_int("TOTAL_SESSIONS"),
            connections_active=_int("ACTIVE_SESSIONS"),
            database_size_mb=_float("DB_SIZE_MB"),
            slow_queries=_int("SLOW_QUERIES"),
            slow_queries_detail=slow_queries_detail or [],
            extra={"tablespace_used_pct": _float("TABLESPACE_USED_PCT")},
        )
        return metrics

    def _collect_docker_slow_queries(
        self, container: str, oracle_env: str
    ) -> Optional[List[SlowQuery]]:
        """docker exec 模式采集 Top 10 慢查询。"""
        sql = (
            "SET PAGESIZE 0 FEEDBACK OFF VERIFY OFF HEADING OFF ECHO OFF LINESIZE 500\n"
            "SELECT sql_id || '|||' || ROUND(elapsed_time/executions/1000000, 2)"
            " || '|||' || executions || '|||' || SUBSTR(sql_text, 1, 200)\n"
            "FROM (SELECT sql_id, elapsed_time, executions, sql_text\n"
            "      FROM v$sql WHERE executions > 0 ORDER BY elapsed_time/executions DESC)\n"
            "WHERE ROWNUM <= 10;\n"
            "EXIT;\n"
        )
        bash_cmd = (
            oracle_env
            + "printf '%s' '"
            + sql.replace("'", "'\\''")
            + "' | sqlplus -s / as sysdba"
        )
        cmd = ["docker", "exec", container, "bash", "-c", bash_cmd]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            output = result.stdout
        except Exception as e:
            logger.debug("Failed to collect docker slow queries: %s", e)
            return None

        queries = []
        for line in output.splitlines():
            line = line.strip()
            if not line or "|||" not in line:
                continue
            parts = line.split("|||", 3)
            if len(parts) < 4:
                continue
            try:
                queries.append(SlowQuery(
                    sql_id=parts[0].strip(),
                    avg_seconds=float(parts[1].strip()),
                    executions=int(parts[2].strip()),
                    sql_text=parts[3].strip(),
                ))
            except (ValueError, IndexError):
                continue
        return queries if queries else None
