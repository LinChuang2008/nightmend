"""Alertmanager 反向路由（silence）客户端 + 端点测试。

覆盖：
  client 单元:
    - _iso 把 naive / aware datetime 转成 UTC RFC3339
    - create_silence 成功 / 4xx / 连接失败
    - delete_silence 404 视为成功；5xx 抛
    - list_silences active_only 过滤
  路由集成（带 client fixture）：
    - POST /silences 透传参数 + 返回 silence_id
    - DELETE /silences/{id} 204
    - viewer 调 POST/DELETE → 403
    - alertmanager 不可达 → 502
    - list 活跃过滤
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import httpx
import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.services import alertmanager_client as am


# ─── pure function tests ────────────────────────────────────────────


def test_iso_naive_datetime_converts_to_utc():
    dt = datetime(2026, 4, 21, 12, 0, 0)  # naive
    result = am._iso(dt)
    assert result.endswith("Z")
    assert "2026-04-21T12:00:00" in result


def test_iso_aware_datetime_preserves_utc():
    dt = datetime(2026, 4, 21, 4, 0, 0, tzinfo=timezone(timedelta(hours=8)))
    result = am._iso(dt)
    # 8 点 UTC+8 → 00 点 UTC
    assert "2026-04-20T20:00:00" in result
    assert result.endswith("Z")


# ─── client httpx-mocked ───────────────────────────────────────────


class _Resp:
    def __init__(self, status_code: int, body: dict | str):
        self.status_code = status_code
        self._body = body
        self.text = body if isinstance(body, str) else ""

    def json(self):
        if isinstance(self._body, str):
            raise ValueError("not json")
        return self._body


class _Client:
    def __init__(self, response=None, exc=None, captured=None):
        self._response = response
        self._exc = exc
        self._captured = captured if captured is not None else {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json=None):
        self._captured["url"] = url
        self._captured["json"] = json
        if self._exc:
            raise self._exc
        return self._response

    async def delete(self, url):
        self._captured["url"] = url
        if self._exc:
            raise self._exc
        return self._response

    async def get(self, url):
        self._captured["url"] = url
        if self._exc:
            raise self._exc
        return self._response


@pytest.mark.asyncio
async def test_create_silence_success():
    captured: dict = {}
    resp = _Resp(200, {"silenceID": "ab-12"})
    with patch.object(settings, "alertmanager_url", "http://alertmanager:9093"), \
         patch("app.services.alertmanager_client.httpx.AsyncClient", return_value=_Client(response=resp, captured=captured)):
        sid = await am.create_silence(
            [{"name": "alertname", "value": "HighCPU", "isRegex": False, "isEqual": True}],
            duration=timedelta(minutes=10),
            created_by="test",
            comment="unit test",
        )
    assert sid == "ab-12"
    assert captured["url"].endswith("/api/v2/silences")
    sent = captured["json"]
    assert sent["createdBy"] == "test"
    assert sent["comment"] == "unit test"
    assert sent["matchers"][0]["name"] == "alertname"


@pytest.mark.asyncio
async def test_create_silence_returns_silenceid_alt_key():
    """AM 不同版本键名可能是 silenceId / id，客户端要容错。"""
    resp = _Resp(200, {"id": "xx-77"})
    with patch.object(settings, "alertmanager_url", "http://alertmanager:9093"), \
         patch("app.services.alertmanager_client.httpx.AsyncClient", return_value=_Client(response=resp)):
        sid = await am.create_silence(
            [{"name": "alertname", "value": "x", "isRegex": False, "isEqual": True}],
            duration=timedelta(minutes=5), created_by="t", comment="c",
        )
    assert sid == "xx-77"


@pytest.mark.asyncio
async def test_create_silence_4xx_raises_unavailable():
    resp = _Resp(400, "bad matchers")
    with patch.object(settings, "alertmanager_url", "http://alertmanager:9093"), \
         patch("app.services.alertmanager_client.httpx.AsyncClient", return_value=_Client(response=resp)):
        with pytest.raises(am.AlertmanagerUnavailable):
            await am.create_silence(
                [{"name": "alertname", "value": "x", "isRegex": False, "isEqual": True}],
                duration=timedelta(minutes=5), created_by="t", comment="c",
            )


@pytest.mark.asyncio
async def test_create_silence_connection_error_raises_unavailable():
    with patch.object(settings, "alertmanager_url", "http://alertmanager:9093"), \
         patch("app.services.alertmanager_client.httpx.AsyncClient",
               return_value=_Client(exc=httpx.ConnectError("dns fail"))):
        with pytest.raises(am.AlertmanagerUnavailable):
            await am.create_silence(
                [{"name": "alertname", "value": "x", "isRegex": False, "isEqual": True}],
                duration=timedelta(minutes=5), created_by="t", comment="c",
            )


@pytest.mark.asyncio
async def test_delete_silence_404_is_success():
    """已删除的 silence 再删应视为成功。"""
    resp = _Resp(404, "not found")
    with patch.object(settings, "alertmanager_url", "http://alertmanager:9093"), \
         patch("app.services.alertmanager_client.httpx.AsyncClient", return_value=_Client(response=resp)):
        # 不抛
        await am.delete_silence("some-id")


@pytest.mark.asyncio
async def test_delete_silence_5xx_raises():
    resp = _Resp(500, "boom")
    with patch.object(settings, "alertmanager_url", "http://alertmanager:9093"), \
         patch("app.services.alertmanager_client.httpx.AsyncClient", return_value=_Client(response=resp)):
        with pytest.raises(am.AlertmanagerUnavailable):
            await am.delete_silence("some-id")


@pytest.mark.asyncio
async def test_list_silences_active_only_filters():
    resp = _Resp(200, [
        {"id": "a1", "status": {"state": "active"}},
        {"id": "a2", "status": {"state": "expired"}},
        {"id": "a3", "status": {"state": "pending"}},
    ])
    with patch.object(settings, "alertmanager_url", "http://alertmanager:9093"), \
         patch("app.services.alertmanager_client.httpx.AsyncClient", return_value=_Client(response=resp)):
        active = await am.list_silences(active_only=True)
    assert [s["id"] for s in active] == ["a1"]


@pytest.mark.asyncio
async def test_unconfigured_url_raises_unavailable():
    with patch.object(settings, "alertmanager_url", ""):
        with pytest.raises(am.AlertmanagerUnavailable):
            await am.create_silence(
                [{"name": "alertname", "value": "x", "isRegex": False, "isEqual": True}],
                duration=timedelta(minutes=5), created_by="t", comment="c",
            )
        assert await am.is_healthy() is False


# ─── Router integration ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_post_silence_endpoint(client: AsyncClient, auth_headers):
    resp = _Resp(200, {"silenceID": "id-1"})
    with patch.object(settings, "alertmanager_url", "http://alertmanager:9093"), \
         patch("app.services.alertmanager_client.httpx.AsyncClient", return_value=_Client(response=resp)):
        response = await client.post(
            "/api/v1/alertmanager/silences",
            headers=auth_headers,
            json={
                "matchers": [{"name": "alertname", "value": "x", "isRegex": False, "isEqual": True}],
                "duration_seconds": 600,
                "comment": "maintenance",
            },
        )
    assert response.status_code == 200
    assert response.json()["silence_id"] == "id-1"


@pytest.mark.asyncio
async def test_post_silence_viewer_forbidden(client: AsyncClient, viewer_headers):
    response = await client.post(
        "/api/v1/alertmanager/silences",
        headers=viewer_headers,
        json={
            "matchers": [{"name": "alertname", "value": "x", "isRegex": False, "isEqual": True}],
            "duration_seconds": 600,
            "comment": "maintenance",
        },
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_post_silence_alertmanager_unavailable_returns_502(client: AsyncClient, auth_headers):
    with patch.object(settings, "alertmanager_url", "http://alertmanager:9093"), \
         patch("app.services.alertmanager_client.httpx.AsyncClient",
               return_value=_Client(exc=httpx.ConnectError("dns fail"))):
        response = await client.post(
            "/api/v1/alertmanager/silences",
            headers=auth_headers,
            json={
                "matchers": [{"name": "alertname", "value": "x", "isRegex": False, "isEqual": True}],
                "duration_seconds": 600,
                "comment": "maintenance",
            },
        )
    assert response.status_code == 502


@pytest.mark.asyncio
async def test_delete_silence_endpoint(client: AsyncClient, auth_headers):
    resp = _Resp(200, {})
    with patch.object(settings, "alertmanager_url", "http://alertmanager:9093"), \
         patch("app.services.alertmanager_client.httpx.AsyncClient", return_value=_Client(response=resp)):
        response = await client.delete(
            "/api/v1/alertmanager/silences/the-id",
            headers=auth_headers,
        )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_list_silences_endpoint(client: AsyncClient, auth_headers):
    resp = _Resp(200, [{"id": "a1", "status": {"state": "active"}}])
    with patch.object(settings, "alertmanager_url", "http://alertmanager:9093"), \
         patch("app.services.alertmanager_client.httpx.AsyncClient", return_value=_Client(response=resp)):
        response = await client.get(
            "/api/v1/alertmanager/silences",
            headers=auth_headers,
        )
    assert response.status_code == 200
    assert response.json()[0]["id"] == "a1"


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient, auth_headers):
    resp = _Resp(200, "")
    with patch.object(settings, "alertmanager_url", "http://alertmanager:9093"), \
         patch("app.services.alertmanager_client.httpx.AsyncClient", return_value=_Client(response=resp)):
        response = await client.get("/api/v1/alertmanager/health", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["healthy"] is True


@pytest.mark.asyncio
async def test_silence_rejects_absurd_duration(client: AsyncClient, auth_headers):
    # <60s 被 Pydantic 拒绝
    response = await client.post(
        "/api/v1/alertmanager/silences",
        headers=auth_headers,
        json={
            "matchers": [{"name": "alertname", "value": "x", "isRegex": False, "isEqual": True}],
            "duration_seconds": 5,
            "comment": "too short",
        },
    )
    assert response.status_code == 422
