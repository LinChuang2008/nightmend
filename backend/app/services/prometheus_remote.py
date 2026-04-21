"""Prometheus sidecar 转发客户端 (Prometheus Sidecar Forwarding Client)

底层逻辑：
    当 settings.prometheus_remote_enabled=True 时，PromQL 查询从 NightMend 内置
    mini 引擎（基于 HostMetric 表）切换到真正的 Prometheus sidecar HTTP API。
    保持响应结构兼容既有 router 调用方，前端零感知。

响应格式契约：
    {
        "resultType": "vector" | "matrix" | "scalar" | "string",
        "result": [...],
    }

失败路径：
    - sidecar 不可达：抛 PrometheusRemoteUnavailable，上层决定是否 fallback 或透传 500
    - sidecar 返回 4xx/5xx：封装 message 抛出，保留上游错误链路
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class PrometheusRemoteUnavailable(RuntimeError):
    """sidecar 网络不可达或 >=500 时抛出，调用方可决定 fallback 或 503。"""


class PrometheusRemoteError(ValueError):
    """sidecar 返回 status=error 或 4xx 时抛出，通常是用户 query 不合法。"""


async def _request(
    path: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    base = settings.prometheus_remote_url.rstrip("/")
    url = f"{base}{path}"
    timeout = settings.prometheus_remote_timeout_seconds
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, params=params)
    except httpx.RequestError as exc:
        # 连接级错误：DNS 失败、超时、TCP 重置
        logger.warning("Prometheus sidecar unreachable: %s", exc)
        raise PrometheusRemoteUnavailable(f"Prometheus sidecar unreachable: {exc}") from exc

    if response.status_code >= 500:
        raise PrometheusRemoteUnavailable(
            f"Prometheus returned {response.status_code}: {response.text[:200]}"
        )

    try:
        body = response.json()
    except ValueError as exc:
        raise PrometheusRemoteUnavailable(f"Prometheus returned non-JSON: {exc}") from exc

    status = body.get("status")
    if status == "error" or response.status_code >= 400:
        error_type = body.get("errorType", "execution")
        error_msg = body.get("error", response.text[:200])
        raise PrometheusRemoteError(f"{error_type}: {error_msg}")

    data = body.get("data")
    if not isinstance(data, dict):
        raise PrometheusRemoteUnavailable("Prometheus response missing data field")
    return data


async def instant_query(query: str, eval_time: datetime | None = None) -> dict[str, Any]:
    """转发 /api/v1/query 到 sidecar。返回 Prometheus data 对象。"""
    params: dict[str, Any] = {"query": query}
    if eval_time is not None:
        params["time"] = eval_time.timestamp()
    return await _request("/api/v1/query", params)


async def range_query(
    query: str,
    start: datetime,
    end: datetime,
    step: timedelta,
) -> dict[str, Any]:
    """转发 /api/v1/query_range 到 sidecar。"""
    params = {
        "query": query,
        "start": start.timestamp(),
        "end": end.timestamp(),
        # Prometheus 接受数字秒或 duration 字符串，数字更安全
        "step": step.total_seconds(),
    }
    return await _request("/api/v1/query_range", params)


async def is_healthy() -> bool:
    """用于启动期/健康检查；/-/healthy 200 即视为可用。"""
    base = settings.prometheus_remote_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"{base}/-/healthy")
        return response.status_code == 200
    except httpx.RequestError:
        return False
