"""
仪表盘数据路由模块 (Dashboard Data Router)

功能说明：为前端仪表盘提供聚合趋势数据，展示系统整体运行状况
核心职责：
  - 查询最近24小时的系统指标趋势
  - 聚合CPU和内存使用率的每小时平均值
  - 统计告警和错误日志的每小时数量
  - 构建完整24小时时间轴用于图表展示
依赖关系：依赖SQLAlchemy、PostgreSQL date_trunc聚合函数
API端点：GET /trends

Author: NightMend Team
"""
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select, and_, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.host_metric import HostMetric
from app.models.alert import Alert
from app.models.log_entry import LogEntry
from app.models.user import User

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@router.get("/summary")
async def get_summary(_user: User = Depends(get_current_user)):
    """
    仪表盘汇总数据快照接口 (Dashboard Summary Snapshot)

    通过 REST 接口返回与 WebSocket 推送相同的仪表盘汇总数据，
    适用于首屏初始化加载和非 WebSocket 客户端（如脚本、外部监控系统）。

    Returns:
        dict: 包含主机、服务、告警、资源使用率和健康评分的汇总数据
    """
    from app.routers.dashboard_ws import _collect_dashboard_data
    return await _collect_dashboard_data()


@router.get("/trends")
async def get_trends(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """
    仪表盘趋势数据查询接口 (Dashboard Trends Data Query)
    
    获取最近24小时的系统运行趋势数据，用于仪表盘图表展示。
    
    Args:
        db: 数据库会话依赖注入
        _user: 当前登录用户（JWT认证，但此接口不使用用户信息）
    Returns:
        dict: 包含24个小时趋势数据的响应
            - hour: 小时时间戳（ISO格式）
            - avg_cpu: 平均CPU使用率（百分比，保留1位小数）
            - avg_mem: 平均内存使用率（百分比，保留1位小数）  
            - alert_count: 该小时告警数量
            - error_log_count: 该小时错误日志数量
    流程：
        1. 计算24小时前的起始时间
        2. 分别查询每小时的指标、告警、错误日志聚合数据
        3. 构建完整的24小时时间轴
        4. 将数据库结果映射到时间轴，填补空缺小时
    """
    # 计算24小时前的时间作为查询起点 (Calculate 24 hours ago as query start point)
    since = datetime.now(timezone.utc) - timedelta(hours=24)

    # 查询每小时平均CPU和内存使用率（使用PostgreSQL date_trunc按小时分组聚合） 
    # (Query hourly average CPU and memory usage with PostgreSQL date_trunc grouping)
    metric_sql = text("""
        SELECT
            date_trunc('hour', recorded_at) AS hour,
            avg(cpu_percent) AS avg_cpu,
            avg(memory_percent) AS avg_mem
        FROM host_metrics
        WHERE recorded_at >= :since
        GROUP BY date_trunc('hour', recorded_at)
        ORDER BY hour ASC
    """)
    metric_result = await db.execute(metric_sql, {"since": since})
    metric_rows = metric_result.mappings().all()

    # 查询每小时告警触发数量 (Query hourly alert firing count)
    alert_sql = text("""
        SELECT
            date_trunc('hour', fired_at) AS hour,
            count(*) AS cnt
        FROM alerts
        WHERE fired_at >= :since
        GROUP BY date_trunc('hour', fired_at)
        ORDER BY hour ASC
    """)
    alert_result = await db.execute(alert_sql, {"since": since})
    alert_rows = alert_result.mappings().all()

    # 查询每小时错误级别日志数量（ERROR/CRITICAL/FATAL），排除被屏蔽主机
    from app.services.suppression_service import SuppressionService
    suppressed_host_ids = await SuppressionService.get_suppressed_host_ids_for_logs(db)

    exclude_clause = ""
    log_params: dict = {"since": since}
    if suppressed_host_ids:
        placeholders = ", ".join(f":hid{i}" for i, _ in enumerate(suppressed_host_ids))
        exclude_clause = f"AND host_id NOT IN ({placeholders})"
        for i, hid in enumerate(suppressed_host_ids):
            log_params[f"hid{i}"] = hid

    log_sql = text(f"""
        SELECT
            date_trunc('hour', timestamp) AS hour,
            count(*) AS cnt
        FROM log_entries
        WHERE timestamp >= :since AND level IN ('ERROR', 'CRITICAL', 'FATAL')
        {exclude_clause}
        GROUP BY date_trunc('hour', timestamp)
        ORDER BY hour ASC
    """)
    log_result = await db.execute(log_sql, log_params)
    log_rows = log_result.mappings().all()

    # 构建完整的24小时时间轴，确保图表显示连续性 (Build complete 24-hour timeline for chart continuity)
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)  # 对齐到整点
    hours = []
    for i in range(24):
        h = now - timedelta(hours=23 - i)  # 从24小时前到现在
        hours.append(h)

    # 将数据库查询结果映射为哈希表，便于快速查找 (Map database results to hash tables for fast lookup)
    def _to_aware_dt(val):
        """将 date_trunc 返回值统一为 UTC aware datetime（兼容 SQLite 返回字符串的情况）。"""
        if isinstance(val, str):
            val = datetime.fromisoformat(val)
        if val.tzinfo is None:
            return val.replace(tzinfo=timezone.utc)
        return val

    metric_map = {_to_aware_dt(row["hour"]): row for row in metric_rows}
    alert_map = {_to_aware_dt(row["hour"]): row["cnt"] for row in alert_rows}
    log_map = {_to_aware_dt(row["hour"]): row["cnt"] for row in log_rows}

    # 遍历时间轴，构建完整的趋势数据数组 (Iterate timeline to build complete trend data array)
    result = []
    for h in hours:
        m = metric_map.get(h)  # 获取该小时的指标数据
        result.append({
            "hour": h.isoformat(),  # ISO格式时间戳用于前端图表
            # 保留1位小数的CPU使用率，无数据时为None (1 decimal place for CPU, None if no data)
            "avg_cpu": round(float(m["avg_cpu"]), 1) if m and m["avg_cpu"] is not None else None,
            # 保留1位小数的内存使用率，无数据时为None (1 decimal place for memory, None if no data)
            "avg_mem": round(float(m["avg_mem"]), 1) if m and m["avg_mem"] is not None else None,
            # 告警数量，无数据时为0 (Alert count, 0 if no data)
            "alert_count": int(alert_map.get(h, 0)),
            # 错误日志数量，无数据时为0 (Error log count, 0 if no data)
            "error_log_count": int(log_map.get(h, 0)),
        })

    return {"trends": result}
