"""
PromQL 查询引擎服务 (PromQL Query Engine Service)

功能描述 (Description):
    提供类 PromQL 查询语法支持，用于对 NightMend 存储的主机指标数据执行灵活查询。
    支持即时查询（Instant Query）和范围查询（Range Query），兼容 Prometheus HTTP API 的
    响应格式，方便与现有 Grafana/Dashboard 工具集成。

    Provides PromQL-like query syntax support for flexible querying of host metric data
    stored by NightMend. Supports instant queries and range queries, compatible with the
    Prometheus HTTP API response format for easy integration with existing Grafana/Dashboard tools.

支持的功能 (Supported Features):
    - 即时查询: nightmend_host_cpu_percent, nightmend_host_cpu_percent{hostname="web-01"}
    - 范围查询: nightmend_host_cpu_percent[5m]
    - 标签匹配: =, !=, =~, !~ (正则)
    - 聚合函数: sum(), avg(), min(), max(), count() 支持 by(label) / without(label)
    - 范围向量函数: rate(), increase(), avg_over_time(), max_over_time(), min_over_time()
    - 基本算术: +, -, *, / (标量与向量之间)

Author: NightMend Team
"""
import re
import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.host_metric import HostMetric
from app.models.host import Host

logger = logging.getLogger(__name__)

# ─── 指标名称到模型字段的映射 (Metric Name to Model Field Mapping) ──────────────

METRIC_FIELD_MAP: dict[str, str] = {
    "nightmend_host_cpu_percent": "cpu_percent",
    "nightmend_host_memory_percent": "memory_percent",
    "nightmend_host_disk_percent": "disk_percent",
    "nightmend_host_cpu_load_1m": "cpu_load_1",
    "nightmend_host_cpu_load_5m": "cpu_load_5",
    "nightmend_host_cpu_load_15m": "cpu_load_15",
    "nightmend_host_network_bytes_sent_total": "net_bytes_sent",
    "nightmend_host_network_bytes_received_total": "net_bytes_recv",
}

# ─── 时间解析 (Duration Parsing) ─────────────────────────────────────────────────

_DURATION_RE = re.compile(r"^(\d+)([smhdw])$")

_DURATION_SECONDS: dict[str, int] = {
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
    "w": 604800,
}


def parse_duration(duration_str: str) -> timedelta:
    """
    解析 PromQL 风格的时间段字符串 (Parse PromQL-style duration string)

    支持格式: 30s, 5m, 1h, 7d, 1w
    Supported formats: 30s, 5m, 1h, 7d, 1w

    Args:
        duration_str: 时间段字符串 (Duration string)

    Returns:
        timedelta 对象 (timedelta object)

    Raises:
        ValueError: 无效的时间段格式 (Invalid duration format)
    """
    stripped = duration_str.strip()
    # 支持纯数字作为秒数 (Support plain numbers as seconds — Prometheus compatible)
    if stripped.isdigit():
        return timedelta(seconds=int(stripped))
    m = _DURATION_RE.match(stripped)
    if not m:
        raise ValueError(f"Invalid duration: {duration_str}")
    value, unit = int(m.group(1)), m.group(2)
    return timedelta(seconds=value * _DURATION_SECONDS[unit])


# ─── 标签匹配器 (Label Matchers) ─────────────────────────────────────────────────

# 匹配: label="value", label!="value", label=~"regex", label!~"regex"
_LABEL_MATCHER_RE = re.compile(
    r'(\w+)\s*(=~|!~|!=|=)\s*"([^"]*)"'
)


class LabelMatcher:
    """
    标签匹配器 (Label Matcher)

    支持四种匹配操作符：
    - = : 精确相等 (Exact equality)
    - != : 不等于 (Not equal)
    - =~ : 正则匹配 (Regex match)
    - !~ : 正则不匹配 (Regex not match)
    """

    def __init__(self, label: str, op: str, value: str):
        self.label = label
        self.op = op
        self.value = value
        if op in ("=~", "!~"):
            self._pattern = re.compile(value)
        else:
            self._pattern = None

    def matches(self, label_value: str | None) -> bool:
        """
        检查标签值是否匹配 (Check if label value matches)

        Args:
            label_value: 实际标签值 (Actual label value)

        Returns:
            bool: 是否匹配 (Whether it matches)
        """
        v = label_value or ""
        if self.op == "=":
            return v == self.value
        elif self.op == "!=":
            return v != self.value
        elif self.op == "=~":
            return bool(self._pattern.search(v))
        elif self.op == "!~":
            return not self._pattern.search(v)
        return False


def _parse_label_matchers(label_str: str) -> list[LabelMatcher]:
    """
    解析花括号内的标签匹配器列表 (Parse label matchers inside curly braces)

    Args:
        label_str: 花括号内的内容，如 'hostname="web-01",group!="test"'

    Returns:
        LabelMatcher 列表 (List of LabelMatcher)
    """
    matchers = []
    for m in _LABEL_MATCHER_RE.finditer(label_str):
        matchers.append(LabelMatcher(m.group(1), m.group(2), m.group(3)))
    return matchers


# ─── PromQL 解析器 (PromQL Parser) ───────────────────────────────────────────────

# 匹配: metric_name{labels}[duration]
_VECTOR_SELECTOR_RE = re.compile(
    r"^([\w:]+)"                     # 指标名 (metric name)
    r"(?:\{([^}]*)\})?"              # 可选标签 {labels}
    r"(?:\[(\d+[smhdw])\])?"         # 可选范围 [duration]
    r"$"
)

# 匹配聚合函数: func(... ) by(label) 或 func(... ) without(label)
_AGGREGATION_RE = re.compile(
    r"^(sum|avg|min|max|count)\s*\(\s*(.+?)\s*\)"
    r"(?:\s+(by|without)\s*\(\s*([\w,\s]+)\s*\))?"
    r"$",
    re.DOTALL,
)

# 匹配范围向量函数: func(metric[dur])
_RANGE_FUNC_RE = re.compile(
    r"^(rate|increase|avg_over_time|max_over_time|min_over_time)"
    r"\s*\(\s*(.+?)\s*\)$",
    re.DOTALL,
)

# 匹配算术表达式: expr OP scalar  或  scalar OP expr
_ARITH_RE = re.compile(
    r"^(.+?)\s*([+\-*/])\s*(\d+(?:\.\d+)?)\s*$"
)
_ARITH_LEFT_RE = re.compile(
    r"^(\d+(?:\.\d+)?)\s*([+\-*/])\s*(.+?)\s*$"
)


class ParsedQuery:
    """
    解析后的 PromQL 查询 (Parsed PromQL Query)

    存储解析后的查询结构，包括指标名称、标签匹配器、时间范围、
    聚合函数、范围向量函数和算术操作。

    Stores the parsed query structure, including metric name, label matchers,
    time range, aggregation functions, range vector functions, and arithmetic operations.
    """

    def __init__(self):
        self.metric_name: str = ""
        self.label_matchers: list[LabelMatcher] = []
        self.range_duration: timedelta | None = None
        # 聚合 (Aggregation)
        self.agg_func: str | None = None
        self.agg_grouping: str | None = None  # "by" or "without"
        self.agg_labels: list[str] = []
        # 范围向量函数 (Range vector function)
        self.range_func: str | None = None
        # 算术 (Arithmetic)
        self.arith_op: str | None = None
        self.arith_scalar: float | None = None
        self.arith_scalar_left: bool = False


def parse_promql(expr: str) -> ParsedQuery:
    """
    解析 PromQL 表达式 (Parse PromQL expression)

    使用基于正则的分层解析策略，支持常见的 PromQL 查询模式。
    解析优先级: 算术 > 聚合 > 范围向量函数 > 向量选择器

    Uses a regex-based layered parsing strategy supporting common PromQL query patterns.
    Parsing priority: arithmetic > aggregation > range vector function > vector selector.

    Args:
        expr: PromQL 表达式字符串 (PromQL expression string)

    Returns:
        ParsedQuery: 解析后的查询对象 (Parsed query object)

    Raises:
        ValueError: 无法解析的表达式 (Unparseable expression)
    """
    expr = expr.strip()
    pq = ParsedQuery()

    # ── 1. 检测算术运算 (Detect arithmetic) ──────────────────────────────────
    inner_expr = expr
    arith_m = _ARITH_RE.match(expr)
    arith_left_m = _ARITH_LEFT_RE.match(expr) if not arith_m else None
    if arith_m:
        inner_expr = arith_m.group(1).strip()
        pq.arith_op = arith_m.group(2)
        pq.arith_scalar = float(arith_m.group(3))
        pq.arith_scalar_left = False
    elif arith_left_m:
        pq.arith_scalar = float(arith_left_m.group(1))
        pq.arith_op = arith_left_m.group(2)
        inner_expr = arith_left_m.group(3).strip()
        pq.arith_scalar_left = True

    # ── 2. 检测聚合函数 (Detect aggregation function) ────────────────────────
    agg_m = _AGGREGATION_RE.match(inner_expr)
    if agg_m:
        pq.agg_func = agg_m.group(1)
        inner_expr = agg_m.group(2).strip()
        if agg_m.group(3):
            pq.agg_grouping = agg_m.group(3)
            pq.agg_labels = [l.strip() for l in agg_m.group(4).split(",")]

    # ── 3. 检测范围向量函数 (Detect range vector function) ────────────────────
    range_m = _RANGE_FUNC_RE.match(inner_expr)
    if range_m:
        pq.range_func = range_m.group(1)
        inner_expr = range_m.group(2).strip()

    # ── 4. 解析向量选择器 (Parse vector selector) ────────────────────────────
    vs_m = _VECTOR_SELECTOR_RE.match(inner_expr)
    if not vs_m:
        raise ValueError(f"Cannot parse PromQL expression: {expr}")

    pq.metric_name = vs_m.group(1)
    if pq.metric_name not in METRIC_FIELD_MAP:
        raise ValueError(
            f"Unknown metric: {pq.metric_name}. "
            f"Supported metrics: {', '.join(sorted(METRIC_FIELD_MAP.keys()))}"
        )

    if vs_m.group(2):
        pq.label_matchers = _parse_label_matchers(vs_m.group(2))

    if vs_m.group(3):
        pq.range_duration = parse_duration(vs_m.group(3))

    # 范围向量函数需要范围选择器 (Range vector functions require a range selector)
    if pq.range_func and pq.range_duration is None:
        raise ValueError(
            f"Range vector function {pq.range_func}() requires a range selector, "
            f"e.g. {pq.metric_name}[5m]"
        )

    return pq


# ─── 数据库查询执行 (Database Query Execution) ────────────────────────────────────

# 标签名到模型/关联字段的映射 (Label name to model/join field mapping)
_LABEL_COLUMN_MAP: dict[str, str] = {
    "hostname": "hostname",
    "host_ip": "ip_address",
    "group": "group_name",
    "host_id": "host_id",
}


def _apply_label_filter(query, matchers: list[LabelMatcher]):
    """
    将标签匹配器应用为 SQLAlchemy WHERE 条件 (Apply label matchers as SQLAlchemy WHERE clauses)

    对精确匹配 (=, !=) 使用 SQL 条件，正则匹配 (=~, !~) 使用 PostgreSQL
    的 ~ 操作符。

    Args:
        query: SQLAlchemy select 查询 (SQLAlchemy select query)
        matchers: 标签匹配器列表 (List of label matchers)

    Returns:
        修改后的查询 (Modified query)
    """
    for m in matchers:
        if m.label == "host_id":
            col = HostMetric.host_id
            if m.op == "=":
                query = query.where(col == int(m.value))
            elif m.op == "!=":
                query = query.where(col != int(m.value))
            continue

        # Host 表上的标签 (Labels on the Host table)
        col_name = _LABEL_COLUMN_MAP.get(m.label)
        if col_name is None:
            continue

        col = getattr(Host, col_name, None)
        if col is None:
            continue

        if m.op == "=":
            query = query.where(col == m.value)
        elif m.op == "!=":
            query = query.where(col != m.value)
        elif m.op == "=~":
            # PostgreSQL 正则匹配 (PostgreSQL regex match)
            query = query.where(col.op("~")(m.value))
        elif m.op == "!~":
            query = query.where(~col.op("~")(m.value))

    return query


def _build_base_query(pq: ParsedQuery):
    """
    构建基础查询，联接 HostMetric 和 Host 表 (Build base query joining HostMetric and Host)

    Args:
        pq: 解析后的查询 (Parsed query)

    Returns:
        (query, metric_col): 基础查询和指标字段 (Base query and metric column)
    """
    field_name = METRIC_FIELD_MAP[pq.metric_name]
    metric_col = getattr(HostMetric, field_name)

    query = (
        select(
            HostMetric.host_id,
            Host.hostname.label("hostname"),
            Host.ip_address.label("host_ip"),
            Host.group_name.label("group"),
            metric_col.label("value"),
            HostMetric.recorded_at,
        )
        .select_from(HostMetric.__table__.join(Host.__table__, HostMetric.host_id == Host.id))
        .where(metric_col.isnot(None))
    )

    query = _apply_label_filter(query, pq.label_matchers)
    return query, metric_col


def _apply_arithmetic(value: float, pq: ParsedQuery) -> float:
    """
    对标量执行算术运算 (Apply arithmetic operation to a scalar value)

    Args:
        value: 原始值 (Original value)
        pq: 解析后的查询（含算术信息）(Parsed query with arithmetic info)

    Returns:
        float: 运算后的值 (Computed value)
    """
    if pq.arith_op is None or pq.arith_scalar is None:
        return value
    a, b = (pq.arith_scalar, value) if pq.arith_scalar_left else (value, pq.arith_scalar)
    if pq.arith_op == "+":
        return a + b
    elif pq.arith_op == "-":
        return a - b
    elif pq.arith_op == "*":
        return a * b
    elif pq.arith_op == "/":
        return a / b if b != 0 else 0.0
    return value


def _build_labels(row) -> dict[str, str]:
    """
    从数据库行构建标签字典 (Build label dict from database row)

    Args:
        row: 数据库结果映射行 (Database result mapping row)

    Returns:
        dict: 标签字典 (Label dictionary)
    """
    return {
        "hostname": row["hostname"] or "",
        "host_ip": row["host_ip"] or "",
        "group": row["group"] or "default",
        "host_id": str(row["host_id"]),
    }


# ─── 即时查询 (Instant Query) ────────────────────────────────────────────────────

async def execute_instant_query(
    db: AsyncSession,
    expr: str,
    eval_time: datetime | None = None,
) -> dict[str, Any]:
    """
    执行即时查询，返回指定时间点的指标值 (Execute instant query returning metric values at a point in time)

    类似 Prometheus 的 /api/v1/query 端点。对于每个时间序列，返回
    最近一条记录的值。支持聚合函数和算术运算。

    Similar to the Prometheus /api/v1/query endpoint. For each time series,
    returns the value of the most recent record. Supports aggregation functions
    and arithmetic operations.

    Args:
        db: 异步数据库会话 (Async database session)
        expr: PromQL 表达式 (PromQL expression)
        eval_time: 评估时间点，默认当前时间 (Evaluation time, defaults to now)

    Returns:
        dict: Prometheus 格式的响应数据 (Prometheus-format response data)

    Raises:
        ValueError: 查询解析或执行失败 (Query parse or execution failure)
    """
    pq = parse_promql(expr)
    if eval_time is None:
        eval_time = datetime.now(timezone.utc)

    field_name = METRIC_FIELD_MAP[pq.metric_name]
    metric_col = getattr(HostMetric, field_name)

    # 范围向量函数在即时查询中也需要处理 (Range vector functions need handling in instant queries too)
    if pq.range_func and pq.range_duration:
        return await _execute_range_function_instant(db, pq, eval_time)

    # ── 获取每个主机的最新值 (Get latest value per host) ───────────────────
    # 子查询: 每个 host 的最新记录 ID (Subquery: latest record ID per host)
    latest_subq = (
        select(func.max(HostMetric.id).label("max_id"))
        .where(HostMetric.recorded_at <= eval_time)
        .where(metric_col.isnot(None))
        .group_by(HostMetric.host_id)
        .subquery()
    )

    query = (
        select(
            HostMetric.host_id,
            Host.hostname.label("hostname"),
            Host.ip_address.label("host_ip"),
            Host.group_name.label("group"),
            metric_col.label("value"),
            HostMetric.recorded_at,
        )
        .select_from(HostMetric.__table__.join(Host.__table__, HostMetric.host_id == Host.id))
        .where(HostMetric.id.in_(select(latest_subq.c.max_id)))
    )

    query = _apply_label_filter(query, pq.label_matchers)

    result = await db.execute(query)
    rows = result.mappings().all()

    # ── 聚合处理 (Aggregation processing) ────────────────────────────────
    if pq.agg_func:
        return _aggregate_instant(rows, pq)

    # ── 普通向量结果 (Normal vector result) ──────────────────────────────
    vector_result = []
    for row in rows:
        val = float(row["value"]) if row["value"] is not None else 0.0
        val = _apply_arithmetic(val, pq)
        ts = row["recorded_at"].timestamp() if row["recorded_at"] else eval_time.timestamp()
        vector_result.append({
            "metric": {
                "__name__": pq.metric_name,
                **_build_labels(row),
            },
            "value": [ts, str(val)],
        })

    return {"resultType": "vector", "result": vector_result}


def _aggregate_instant(rows, pq: ParsedQuery) -> dict[str, Any]:
    """
    对即时查询结果执行聚合 (Perform aggregation on instant query results)

    支持 by(label)/without(label) 分组，以及 sum/avg/min/max/count 聚合函数。

    Args:
        rows: 数据库结果行列表 (List of database result rows)
        pq: 解析后的查询 (Parsed query)

    Returns:
        dict: 聚合后的向量结果 (Aggregated vector result)
    """
    # 确定分组标签 (Determine grouping labels)
    all_labels = ["hostname", "host_ip", "group", "host_id"]
    if pq.agg_grouping == "by":
        group_labels = [l for l in pq.agg_labels if l in all_labels]
    elif pq.agg_grouping == "without":
        group_labels = [l for l in all_labels if l not in pq.agg_labels]
    else:
        group_labels = []

    # 按标签分组 (Group by labels)
    groups: dict[tuple, list] = {}
    group_label_vals: dict[tuple, dict] = {}
    for row in rows:
        labels = _build_labels(row)
        key = tuple(labels.get(l, "") for l in group_labels)
        groups.setdefault(key, []).append(float(row["value"]) if row["value"] is not None else 0.0)
        if key not in group_label_vals:
            group_label_vals[key] = {l: labels.get(l, "") for l in group_labels}

    # 计算聚合值 (Compute aggregated values)
    vector_result = []
    now_ts = datetime.now(timezone.utc).timestamp()
    for key, values in groups.items():
        if pq.agg_func == "sum":
            agg_val = sum(values)
        elif pq.agg_func == "avg":
            agg_val = sum(values) / len(values) if values else 0.0
        elif pq.agg_func == "min":
            agg_val = min(values) if values else 0.0
        elif pq.agg_func == "max":
            agg_val = max(values) if values else 0.0
        elif pq.agg_func == "count":
            agg_val = float(len(values))
        else:
            agg_val = 0.0

        agg_val = _apply_arithmetic(agg_val, pq)

        metric_labels = {"__name__": pq.metric_name}
        metric_labels.update(group_label_vals.get(key, {}))
        vector_result.append({
            "metric": metric_labels,
            "value": [now_ts, str(agg_val)],
        })

    return {"resultType": "vector", "result": vector_result}


async def _execute_range_function_instant(
    db: AsyncSession,
    pq: ParsedQuery,
    eval_time: datetime,
) -> dict[str, Any]:
    """
    在即时查询中执行范围向量函数 (Execute range vector function in instant query context)

    对范围窗口内的数据执行 rate/increase/avg_over_time 等计算，
    返回每个时间序列的单个值。

    Args:
        db: 异步数据库会话 (Async database session)
        pq: 解析后的查询 (Parsed query)
        eval_time: 评估时间 (Evaluation time)

    Returns:
        dict: 向量结果 (Vector result)
    """
    start = eval_time - pq.range_duration
    query, _ = _build_base_query(pq)
    query = query.where(
        HostMetric.recorded_at >= start,
        HostMetric.recorded_at <= eval_time,
    ).order_by(HostMetric.host_id, HostMetric.recorded_at.asc())

    result = await db.execute(query)
    rows = result.mappings().all()

    # 按 host_id 分组 (Group by host_id)
    series: dict[int, list] = {}
    series_labels: dict[int, dict] = {}
    for row in rows:
        hid = row["host_id"]
        series.setdefault(hid, []).append(row)
        if hid not in series_labels:
            series_labels[hid] = _build_labels(row)

    vector_result = []
    for hid, data_rows in series.items():
        val = _compute_range_function(pq.range_func, data_rows, pq.range_duration)
        val = _apply_arithmetic(val, pq)
        vector_result.append({
            "metric": {
                "__name__": pq.metric_name,
                **series_labels[hid],
            },
            "value": [eval_time.timestamp(), str(val)],
        })

    # 聚合 (Aggregation)
    if pq.agg_func:
        fake_rows = []
        for item in vector_result:
            v = float(item["value"][1])
            labels = {k: v2 for k, v2 in item["metric"].items() if k != "__name__"}
            fake_rows.append({"value": v, **labels})
        return _aggregate_instant(fake_rows, pq)

    return {"resultType": "vector", "result": vector_result}


def _compute_range_function(func_name: str, rows: list, duration: timedelta) -> float:
    """
    计算范围向量函数的值 (Compute range vector function value)

    Args:
        func_name: 函数名 (Function name): rate, increase, avg_over_time, max_over_time, min_over_time
        rows: 时间范围内的数据行 (Data rows within the time range)
        duration: 时间范围 (Time range duration)

    Returns:
        float: 计算结果 (Computed result)
    """
    if not rows:
        return 0.0

    values = [float(r["value"]) if r["value"] is not None else 0.0 for r in rows]

    if func_name == "avg_over_time":
        return sum(values) / len(values)
    elif func_name == "max_over_time":
        return max(values)
    elif func_name == "min_over_time":
        return min(values)
    elif func_name in ("rate", "increase"):
        if len(values) < 2:
            return 0.0
        diff = values[-1] - values[0]
        # 处理计数器重置 (Handle counter reset)
        if diff < 0:
            diff = values[-1]
        if func_name == "rate":
            dur_seconds = duration.total_seconds()
            return diff / dur_seconds if dur_seconds > 0 else 0.0
        else:
            return diff

    return 0.0


# ─── 范围查询 (Range Query) ──────────────────────────────────────────────────────

async def execute_range_query(
    db: AsyncSession,
    expr: str,
    start: datetime,
    end: datetime,
    step: timedelta,
) -> dict[str, Any]:
    """
    执行范围查询，返回时间范围内的指标矩阵 (Execute range query returning metric matrix over time)

    类似 Prometheus 的 /api/v1/query_range 端点。在 [start, end] 区间内
    以 step 为步长获取数据，返回矩阵格式结果。

    Similar to the Prometheus /api/v1/query_range endpoint. Retrieves data within
    the [start, end] interval at step intervals, returning matrix format results.

    Args:
        db: 异步数据库会话 (Async database session)
        expr: PromQL 表达式 (PromQL expression)
        start: 起始时间 (Start time)
        end: 结束时间 (End time)
        step: 步长 (Step interval)

    Returns:
        dict: Prometheus 格式的矩阵响应数据 (Prometheus-format matrix response data)

    Raises:
        ValueError: 查询解析或执行失败 (Query parse or execution failure)
    """
    pq = parse_promql(expr)

    # 范围向量函数的特殊处理 (Special handling for range vector functions)
    if pq.range_func and pq.range_duration:
        return await _execute_range_function_range(db, pq, start, end, step)

    query, _ = _build_base_query(pq)
    query = query.where(
        HostMetric.recorded_at >= start,
        HostMetric.recorded_at <= end,
    ).order_by(HostMetric.host_id, HostMetric.recorded_at.asc())

    result = await db.execute(query)
    rows = result.mappings().all()

    # 按 host_id 分组 (Group by host_id)
    series: dict[int, list] = {}
    series_labels: dict[int, dict] = {}
    for row in rows:
        hid = row["host_id"]
        series.setdefault(hid, []).append(row)
        if hid not in series_labels:
            series_labels[hid] = _build_labels(row)

    # 对齐到步长 (Align to step)
    matrix_result = []
    for hid, data_rows in series.items():
        values = []
        for row in data_rows:
            ts = row["recorded_at"].timestamp() if row["recorded_at"] else 0
            val = float(row["value"]) if row["value"] is not None else 0.0
            val = _apply_arithmetic(val, pq)
            values.append([ts, str(val)])

        matrix_result.append({
            "metric": {
                "__name__": pq.metric_name,
                **series_labels[hid],
            },
            "values": values,
        })

    # 聚合处理 (Aggregation processing)
    if pq.agg_func:
        return _aggregate_matrix(matrix_result, pq, start, end, step)

    return {"resultType": "matrix", "result": matrix_result}


async def _execute_range_function_range(
    db: AsyncSession,
    pq: ParsedQuery,
    start: datetime,
    end: datetime,
    step: timedelta,
) -> dict[str, Any]:
    """
    在范围查询中执行范围向量函数 (Execute range vector function in range query context)

    对每个步长时间点，取其前 range_duration 窗口的数据计算范围函数值。

    For each step time point, compute range function value using data from
    the preceding range_duration window.

    Args:
        db: 异步数据库会话 (Async database session)
        pq: 解析后的查询 (Parsed query)
        start: 起始时间 (Start time)
        end: 结束时间 (End time)
        step: 步长 (Step interval)

    Returns:
        dict: 矩阵结果 (Matrix result)
    """
    # 扩大查询范围以包含第一个窗口所需数据 (Expand query range for first window)
    expanded_start = start - pq.range_duration
    query, _ = _build_base_query(pq)
    query = query.where(
        HostMetric.recorded_at >= expanded_start,
        HostMetric.recorded_at <= end,
    ).order_by(HostMetric.host_id, HostMetric.recorded_at.asc())

    result = await db.execute(query)
    rows = result.mappings().all()

    # 按 host_id 分组 (Group by host_id)
    series: dict[int, list] = {}
    series_labels: dict[int, dict] = {}
    for row in rows:
        hid = row["host_id"]
        series.setdefault(hid, []).append(row)
        if hid not in series_labels:
            series_labels[hid] = _build_labels(row)

    # 计算每个步长的值 (Compute value at each step)
    matrix_result = []
    for hid, data_rows in series.items():
        values = []
        current = start
        while current <= end:
            window_start = current - pq.range_duration
            window_rows = [
                r for r in data_rows
                if window_start <= r["recorded_at"] <= current
            ]
            val = _compute_range_function(pq.range_func, window_rows, pq.range_duration)
            val = _apply_arithmetic(val, pq)
            values.append([current.timestamp(), str(val)])
            current += step

        matrix_result.append({
            "metric": {
                "__name__": pq.metric_name,
                **series_labels[hid],
            },
            "values": values,
        })

    if pq.agg_func:
        return _aggregate_matrix(matrix_result, pq, start, end, step)

    return {"resultType": "matrix", "result": matrix_result}


def _aggregate_matrix(
    matrix_result: list[dict],
    pq: ParsedQuery,
    start: datetime,
    end: datetime,
    step: timedelta,
) -> dict[str, Any]:
    """
    对矩阵结果执行聚合 (Perform aggregation on matrix results)

    按步长时间点对齐，分组后计算聚合值。

    Args:
        matrix_result: 原始矩阵结果列表 (Original matrix result list)
        pq: 解析后的查询 (Parsed query)
        start: 起始时间 (Start time)
        end: 结束时间 (End time)
        step: 步长 (Step interval)

    Returns:
        dict: 聚合后的矩阵结果 (Aggregated matrix result)
    """
    all_labels = ["hostname", "host_ip", "group", "host_id"]
    if pq.agg_grouping == "by":
        group_labels = [l for l in pq.agg_labels if l in all_labels]
    elif pq.agg_grouping == "without":
        group_labels = [l for l in all_labels if l not in pq.agg_labels]
    else:
        group_labels = []

    # 按分组标签聚合 (Aggregate by group labels)
    # key -> timestamp -> [values]
    groups: dict[tuple, dict[float, list[float]]] = {}
    group_label_vals: dict[tuple, dict] = {}

    for series in matrix_result:
        labels = {k: v for k, v in series["metric"].items() if k != "__name__"}
        key = tuple(labels.get(l, "") for l in group_labels)
        if key not in groups:
            groups[key] = {}
            group_label_vals[key] = {l: labels.get(l, "") for l in group_labels}
        for ts, val_str in series["values"]:
            groups[key].setdefault(ts, []).append(float(val_str))

    # 计算聚合 (Compute aggregation)
    result = []
    for key, ts_values in groups.items():
        values = []
        for ts in sorted(ts_values.keys()):
            vals = ts_values[ts]
            if pq.agg_func == "sum":
                agg_val = sum(vals)
            elif pq.agg_func == "avg":
                agg_val = sum(vals) / len(vals) if vals else 0.0
            elif pq.agg_func == "min":
                agg_val = min(vals) if vals else 0.0
            elif pq.agg_func == "max":
                agg_val = max(vals) if vals else 0.0
            elif pq.agg_func == "count":
                agg_val = float(len(vals))
            else:
                agg_val = 0.0
            values.append([ts, str(agg_val)])

        metric_labels = {"__name__": pq.metric_name}
        metric_labels.update(group_label_vals.get(key, {}))
        result.append({
            "metric": metric_labels,
            "values": values,
        })

    return {"resultType": "matrix", "result": result}
