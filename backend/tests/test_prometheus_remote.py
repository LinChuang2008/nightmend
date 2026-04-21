"""Prometheus sidecar 转发客户端 + promql_service 分发行为测试。

覆盖点：
  1. sidecar 成功：返回 Prometheus data 对象
  2. sidecar 4xx / status=error：抛 PrometheusRemoteError → 对应 400
  3. sidecar 不可达：抛 PrometheusRemoteUnavailable → promql_service 降级到本地引擎
  4. feature flag off：不访问 sidecar，直接走本地引擎
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.core.config import settings
from app.services import prometheus_remote


# ─── prometheus_remote 客户端单元测试 ──────────────────────────────────────────


class _FakeResponse:
    def __init__(self, status_code: int, body: dict | str):
        self.status_code = status_code
        self._body = body
        self.text = body if isinstance(body, str) else ""

    def json(self):
        if isinstance(self._body, str):
            raise ValueError("not json")
        return self._body


class _FakeClient:
    """上下文管理器 mock，模拟 httpx.AsyncClient。"""

    def __init__(self, response=None, exc=None):
        self._response = response
        self._exc = exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, params=None):
        if self._exc is not None:
            raise self._exc
        return self._response


@pytest.mark.asyncio
async def test_instant_query_success():
    resp = _FakeResponse(
        200,
        {"status": "success", "data": {"resultType": "vector", "result": [{"metric": {}, "value": [1.0, "42"]}]}},
    )
    with patch("app.services.prometheus_remote.httpx.AsyncClient", return_value=_FakeClient(response=resp)):
        data = await prometheus_remote.instant_query("up")
    assert data["resultType"] == "vector"
    assert data["result"][0]["value"] == [1.0, "42"]


@pytest.mark.asyncio
async def test_instant_query_user_error_raises_remote_error():
    resp = _FakeResponse(
        400,
        {"status": "error", "errorType": "bad_data", "error": "invalid expression"},
    )
    with patch("app.services.prometheus_remote.httpx.AsyncClient", return_value=_FakeClient(response=resp)):
        with pytest.raises(prometheus_remote.PrometheusRemoteError) as exc_info:
            await prometheus_remote.instant_query("bad!!!query")
    assert "invalid expression" in str(exc_info.value)


@pytest.mark.asyncio
async def test_instant_query_server_error_raises_unavailable():
    resp = _FakeResponse(503, "service unavailable")
    with patch("app.services.prometheus_remote.httpx.AsyncClient", return_value=_FakeClient(response=resp)):
        with pytest.raises(prometheus_remote.PrometheusRemoteUnavailable):
            await prometheus_remote.instant_query("up")


@pytest.mark.asyncio
async def test_instant_query_connection_error_raises_unavailable():
    fake_client = _FakeClient(exc=httpx.ConnectError("dns fail"))
    with patch("app.services.prometheus_remote.httpx.AsyncClient", return_value=fake_client):
        with pytest.raises(prometheus_remote.PrometheusRemoteUnavailable):
            await prometheus_remote.instant_query("up")


@pytest.mark.asyncio
async def test_range_query_passes_correct_params():
    resp = _FakeResponse(200, {"status": "success", "data": {"resultType": "matrix", "result": []}})
    captured: dict = {}

    class _CaptureClient(_FakeClient):
        async def get(self, url, params=None):
            captured["url"] = url
            captured["params"] = params
            return resp

    with patch("app.services.prometheus_remote.httpx.AsyncClient", return_value=_CaptureClient(response=resp)):
        start = datetime(2026, 4, 21, 0, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 4, 21, 1, 0, 0, tzinfo=timezone.utc)
        step = timedelta(seconds=60)
        await prometheus_remote.range_query("up", start, end, step)

    assert captured["url"].endswith("/api/v1/query_range")
    assert captured["params"]["query"] == "up"
    assert captured["params"]["start"] == start.timestamp()
    assert captured["params"]["end"] == end.timestamp()
    assert captured["params"]["step"] == 60.0


# ─── promql_service 分发行为测试 ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_promql_service_dispatches_to_sidecar_when_enabled():
    """feature flag 开启 → 调用 sidecar，不触碰 HostMetric 本地引擎。"""
    from app.services import promql_service

    mock_result = {"resultType": "vector", "result": [{"metric": {"job": "nightmend"}, "value": [1.0, "3.14"]}]}
    with patch.object(settings, "prometheus_remote_enabled", True), \
         patch.object(prometheus_remote, "instant_query", new=AsyncMock(return_value=mock_result)) as m:
        data = await promql_service.execute_instant_query(db=None, expr="up")  # db 不会被用到
    assert data == mock_result
    m.assert_awaited_once()


@pytest.mark.asyncio
async def test_promql_service_fallback_when_sidecar_unavailable():
    """sidecar 不可达 → 降级到本地引擎（走 parse_promql 路径）。"""
    from app.services import promql_service

    async def _raise_unavailable(*args, **kwargs):
        raise prometheus_remote.PrometheusRemoteUnavailable("network down")

    with patch.object(settings, "prometheus_remote_enabled", True), \
         patch.object(prometheus_remote, "instant_query", new=_raise_unavailable), \
         patch.object(promql_service, "parse_promql", side_effect=ValueError("fallback reached")):
        with pytest.raises(ValueError, match="fallback reached"):
            await promql_service.execute_instant_query(db=None, expr="up")


@pytest.mark.asyncio
async def test_promql_service_user_error_from_sidecar_raises_valueerror():
    """sidecar 回 4xx → PrometheusRemoteError，为 ValueError 子类，router 会转 400。"""
    from app.services import promql_service

    async def _raise_user_err(*args, **kwargs):
        raise prometheus_remote.PrometheusRemoteError("bad query")

    with patch.object(settings, "prometheus_remote_enabled", True), \
         patch.object(prometheus_remote, "instant_query", new=_raise_user_err):
        with pytest.raises(ValueError):  # PrometheusRemoteError 继承自 ValueError
            await promql_service.execute_instant_query(db=None, expr="bad!!!")


@pytest.mark.asyncio
async def test_promql_service_flag_off_does_not_call_sidecar():
    """flag off → 根本不调 sidecar；走本地引擎。"""
    from app.services import promql_service

    sidecar_called = False

    async def _spy(*args, **kwargs):
        nonlocal sidecar_called
        sidecar_called = True
        return {}

    with patch.object(settings, "prometheus_remote_enabled", False), \
         patch.object(prometheus_remote, "instant_query", new=_spy), \
         patch.object(promql_service, "parse_promql", side_effect=ValueError("local reached")):
        with pytest.raises(ValueError, match="local reached"):
            await promql_service.execute_instant_query(db=None, expr="up")

    assert sidecar_called is False
