"""
PromQL 查询路由模块 (PromQL Query Router)

功能说明：提供类 Prometheus 的 PromQL 查询 API，支持即时查询和范围查询。
核心职责：
  - 即时查询 (Instant Query)：返回指定时间点的指标值
  - 范围查询 (Range Query)：返回时间范围内的指标矩阵
  - 兼容 Prometheus HTTP API 响应格式
依赖关系：依赖 PromQL 服务引擎、SQLAlchemy、JWT 认证
API端点：
  - GET /api/v1/promql/query (即时查询)
  - GET /api/v1/promql/query_range (范围查询)

Provides Prometheus-like PromQL query API, supporting instant and range queries.
Core responsibilities:
  - Instant Query: returns metric values at a specified point in time
  - Range Query: returns metric matrix over a time range
  - Compatible with Prometheus HTTP API response format

Author: VigilOps Team
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.services.promql_service import (
    execute_instant_query,
    execute_range_query,
    parse_duration,
    METRIC_FIELD_MAP,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/promql", tags=["promql"])


@router.get("/query")
async def instant_query(
    query: str = Query(..., description="PromQL 查询表达式 (PromQL query expression)"),
    time: float | None = Query(
        None,
        description="评估时间点的 Unix 时间戳（秒），默认当前时间 "
                    "(Evaluation timestamp in Unix seconds, defaults to now)",
    ),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    PromQL 即时查询接口 (PromQL Instant Query)

    执行 PromQL 表达式并返回单一时间点的查询结果。兼容 Prometheus
    /api/v1/query 端点的响应格式。

    Execute a PromQL expression and return query results at a single point in time.
    Compatible with the Prometheus /api/v1/query endpoint response format.

    支持的查询模式 (Supported Query Patterns):
    - 简单选择: vigilops_host_cpu_percent
    - 标签过滤: vigilops_host_cpu_percent{hostname="web-01"}
    - 聚合函数: avg(vigilops_host_cpu_percent) by(group)
    - 范围函数: rate(vigilops_host_network_bytes_sent_total[5m])
    - 算术运算: vigilops_host_cpu_percent * 100

    Args:
        query: PromQL 表达式字符串 (PromQL expression string)
        time: 可选的评估时间戳（秒） (Optional evaluation timestamp in seconds)
        user: 当前登录用户（JWT 认证） (Current user via JWT auth)
        db: 数据库会话依赖注入 (Database session dependency injection)

    Returns:
        dict: Prometheus 格式的响应:
            {
                "status": "success",
                "data": {
                    "resultType": "vector",
                    "result": [...]
                }
            }

    Raises:
        HTTPException 400: 无效的查询表达式 (Invalid query expression)
        HTTPException 500: 查询执行失败 (Query execution failure)
    """
    eval_time = None
    if time is not None:
        try:
            eval_time = datetime.fromtimestamp(time, tz=timezone.utc)
        except (OSError, ValueError, OverflowError):
            raise HTTPException(status_code=400, detail=f"Invalid timestamp: {time}")

    try:
        data = await execute_instant_query(db, query, eval_time)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("PromQL instant query failed: %s", query)
        raise HTTPException(status_code=500, detail=f"Query execution error: {e}")

    return {"status": "success", "data": data}


@router.get("/query_range")
async def range_query(
    query: str = Query(..., description="PromQL 查询表达式 (PromQL query expression)"),
    start: float = Query(..., description="起始时间 Unix 时间戳（秒） (Start timestamp in Unix seconds)"),
    end: float = Query(..., description="结束时间 Unix 时间戳（秒） (End timestamp in Unix seconds)"),
    step: str = Query(
        "60s",
        description="查询步长，如 15s, 1m, 5m, 1h (Query step, e.g. 15s, 1m, 5m, 1h)",
    ),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    PromQL 范围查询接口 (PromQL Range Query)

    在指定时间范围内以固定步长执行 PromQL 表达式，返回矩阵格式结果。
    兼容 Prometheus /api/v1/query_range 端点的响应格式。

    Execute a PromQL expression over a time range at fixed step intervals,
    returning matrix format results. Compatible with the Prometheus
    /api/v1/query_range endpoint response format.

    Args:
        query: PromQL 表达式字符串 (PromQL expression string)
        start: 起始时间 Unix 时间戳 (Start time Unix timestamp)
        end: 结束时间 Unix 时间戳 (End time Unix timestamp)
        step: 步长字符串，如 "15s", "1m", "5m" (Step string, e.g. "15s", "1m", "5m")
        user: 当前登录用户（JWT 认证） (Current user via JWT auth)
        db: 数据库会话依赖注入 (Database session dependency injection)

    Returns:
        dict: Prometheus 格式的响应:
            {
                "status": "success",
                "data": {
                    "resultType": "matrix",
                    "result": [
                        {
                            "metric": {"__name__": "...", "hostname": "..."},
                            "values": [[timestamp, "value"], ...]
                        }
                    ]
                }
            }

    Raises:
        HTTPException 400: 无效的参数或查询表达式 (Invalid parameters or query expression)
        HTTPException 500: 查询执行失败 (Query execution failure)
    """
    # ── 参数校验 (Parameter validation) ──────────────────────────────────
    try:
        start_dt = datetime.fromtimestamp(start, tz=timezone.utc)
    except (OSError, ValueError, OverflowError):
        raise HTTPException(status_code=400, detail=f"Invalid start timestamp: {start}")

    try:
        end_dt = datetime.fromtimestamp(end, tz=timezone.utc)
    except (OSError, ValueError, OverflowError):
        raise HTTPException(status_code=400, detail=f"Invalid end timestamp: {end}")

    if end_dt <= start_dt:
        raise HTTPException(status_code=400, detail="end must be greater than start")

    try:
        step_td = parse_duration(step)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid step: {step}")

    if step_td.total_seconds() < 1:
        raise HTTPException(status_code=400, detail="Step must be at least 1 second")

    # 限制最大步数以防止内存溢出 (Limit max steps to prevent memory overflow)
    max_steps = 11000
    total_steps = (end_dt - start_dt).total_seconds() / step_td.total_seconds()
    if total_steps > max_steps:
        raise HTTPException(
            status_code=400,
            detail=f"Too many steps ({int(total_steps)}). "
                   f"Maximum allowed is {max_steps}. "
                   f"Please increase the step or narrow the time range.",
        )

    try:
        data = await execute_range_query(db, query, start_dt, end_dt, step_td)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("PromQL range query failed: %s", query)
        raise HTTPException(status_code=500, detail=f"Query execution error: {e}")

    return {"status": "success", "data": data}


@router.get("/metadata")
async def query_metadata(
    user: User = Depends(get_current_user),
):
    """
    PromQL 指标元数据接口 (PromQL Metric Metadata)

    返回所有支持的指标名称及其对应的 HostMetric 模型字段，帮助
    用户构建有效的 PromQL 查询。

    Returns all supported metric names and their corresponding HostMetric
    model fields, helping users build valid PromQL queries.

    Args:
        user: 当前登录用户（JWT 认证） (Current user via JWT auth)

    Returns:
        dict: 包含支持的指标列表和可用标签 (Supported metrics list and available labels)
    """
    metrics = []
    for metric_name, field_name in sorted(METRIC_FIELD_MAP.items()):
        metrics.append({
            "metric_name": metric_name,
            "field": field_name,
            "type": "counter" if "total" in metric_name else "gauge",
        })

    return {
        "status": "success",
        "data": {
            "metrics": metrics,
            "labels": ["hostname", "host_ip", "group", "host_id"],
            "functions": {
                "aggregation": ["sum", "avg", "min", "max", "count"],
                "range_vector": ["rate", "increase", "avg_over_time", "max_over_time", "min_over_time"],
            },
            "examples": [
                'vigilops_host_cpu_percent',
                'vigilops_host_cpu_percent{hostname="web-01"}',
                'avg(vigilops_host_cpu_percent) by(group)',
                'rate(vigilops_host_network_bytes_sent_total[5m])',
                'vigilops_host_memory_percent * 100',
            ],
        },
    }
