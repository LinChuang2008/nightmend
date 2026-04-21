"""Prometheus Remote Write 接收器测试。

覆盖：
  - 禁用 flag → 503
  - 无鉴权 → 401
  - token 不匹配 → 401
  - token 未配置但客户端发 Bearer → 503
  - body 超限 → 413
  - 空 body → 400
  - 正常流程 → 204，sidecar 收到原样 bytes + 白名单头
  - sidecar 4xx → 透传；sidecar 5xx → 502；sidecar 连接失败 → 502
"""
from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from app.core.config import settings


VALID_TOKEN = "test-rw-token-0123"


class _UpstreamResp:
    def __init__(self, status_code: int, text: str = "ok"):
        self.status_code = status_code
        self.text = text


class _UpstreamClient:
    """Mock httpx.AsyncClient 捕获 forward 调用。"""

    def __init__(self, response=None, exc=None, captured: dict | None = None):
        self._response = response
        self._exc = exc
        self._captured = captured if captured is not None else {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, content=None, headers=None):
        self._captured["url"] = url
        self._captured["content"] = content
        self._captured["headers"] = headers
        if self._exc is not None:
            raise self._exc
        return self._response


@pytest.mark.asyncio
async def test_disabled_when_flag_off(client):
    with patch.object(settings, "prometheus_remote_enabled", False):
        response = await client.post(
            "/api/v1/prom/remote_write",
            headers={"authorization": f"Bearer {VALID_TOKEN}"},
            content=b"payload",
        )
    assert response.status_code == 503
    assert "PROMETHEUS_REMOTE_ENABLED" in response.text


@pytest.mark.asyncio
async def test_missing_auth_returns_401(client):
    with patch.object(settings, "prometheus_remote_enabled", True), \
         patch.object(settings, "prom_remote_write_token", VALID_TOKEN):
        response = await client.post("/api/v1/prom/remote_write", content=b"x")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_wrong_bearer_returns_401(client):
    with patch.object(settings, "prometheus_remote_enabled", True), \
         patch.object(settings, "prom_remote_write_token", VALID_TOKEN):
        response = await client.post(
            "/api/v1/prom/remote_write",
            headers={"authorization": "Bearer wrong-token"},
            content=b"x",
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_bearer_sent_but_token_unconfigured_returns_503(client):
    with patch.object(settings, "prometheus_remote_enabled", True), \
         patch.object(settings, "prom_remote_write_token", ""):
        response = await client.post(
            "/api/v1/prom/remote_write",
            headers={"authorization": "Bearer anything"},
            content=b"x",
        )
    assert response.status_code == 503
    assert "Remote write token" in response.text


@pytest.mark.asyncio
async def test_empty_body_returns_400(client):
    with patch.object(settings, "prometheus_remote_enabled", True), \
         patch.object(settings, "prom_remote_write_token", VALID_TOKEN):
        response = await client.post(
            "/api/v1/prom/remote_write",
            headers={"authorization": f"Bearer {VALID_TOKEN}"},
            content=b"",
        )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_body_too_large_returns_413(client):
    # 11 MB > 10 MB 上限
    big_body = b"\x00" * (11 * 1024 * 1024)
    with patch.object(settings, "prometheus_remote_enabled", True), \
         patch.object(settings, "prom_remote_write_token", VALID_TOKEN):
        response = await client.post(
            "/api/v1/prom/remote_write",
            headers={"authorization": f"Bearer {VALID_TOKEN}"},
            content=big_body,
        )
    assert response.status_code == 413


@pytest.mark.asyncio
async def test_happy_path_forwards_to_sidecar_and_returns_204(client):
    captured: dict = {}
    upstream = _UpstreamClient(response=_UpstreamResp(204), captured=captured)

    # Prom 客户端会带 Content-Encoding 和 Content-Type，验证白名单通过
    send_body = b"fake-snappy-bytes"
    send_headers = {
        "authorization": f"Bearer {VALID_TOKEN}",
        "content-encoding": "snappy",
        "content-type": "application/x-protobuf",
        "x-prometheus-remote-write-version": "0.1.0",
        "cookie": "access_token=should-not-forward",  # 敏感头必须过滤
    }
    with patch.object(settings, "prometheus_remote_enabled", True), \
         patch.object(settings, "prom_remote_write_token", VALID_TOKEN), \
         patch.object(settings, "prometheus_remote_url", "http://prometheus:9090"), \
         patch("app.routers.prom_remote_write.httpx.AsyncClient", return_value=upstream):
        response = await client.post(
            "/api/v1/prom/remote_write",
            headers=send_headers,
            content=send_body,
        )

    assert response.status_code == 204
    # 原样 bytes 转发
    assert captured["content"] == send_body
    assert captured["url"] == "http://prometheus:9090/api/v1/write"
    fwd = {k.lower(): v for k, v in captured["headers"].items()}
    # 协议头透传
    assert fwd["content-encoding"] == "snappy"
    assert fwd["content-type"] == "application/x-protobuf"
    assert fwd["x-prometheus-remote-write-version"] == "0.1.0"
    # cookie/authorization 不能泄给 Prom
    assert "cookie" not in fwd
    assert "authorization" not in fwd


@pytest.mark.asyncio
async def test_sidecar_connection_error_returns_502(client):
    upstream = _UpstreamClient(exc=httpx.ConnectError("dns fail"))
    with patch.object(settings, "prometheus_remote_enabled", True), \
         patch.object(settings, "prom_remote_write_token", VALID_TOKEN), \
         patch("app.routers.prom_remote_write.httpx.AsyncClient", return_value=upstream):
        response = await client.post(
            "/api/v1/prom/remote_write",
            headers={"authorization": f"Bearer {VALID_TOKEN}"},
            content=b"payload",
        )
    assert response.status_code == 502


@pytest.mark.asyncio
async def test_sidecar_4xx_passes_through(client):
    upstream = _UpstreamClient(response=_UpstreamResp(400, text="bad samples"))
    with patch.object(settings, "prometheus_remote_enabled", True), \
         patch.object(settings, "prom_remote_write_token", VALID_TOKEN), \
         patch("app.routers.prom_remote_write.httpx.AsyncClient", return_value=upstream):
        response = await client.post(
            "/api/v1/prom/remote_write",
            headers={"authorization": f"Bearer {VALID_TOKEN}"},
            content=b"payload",
        )
    assert response.status_code == 400
    assert "bad samples" in response.text


@pytest.mark.asyncio
async def test_sidecar_5xx_becomes_502(client):
    upstream = _UpstreamClient(response=_UpstreamResp(500, text="boom"))
    with patch.object(settings, "prometheus_remote_enabled", True), \
         patch.object(settings, "prom_remote_write_token", VALID_TOKEN), \
         patch("app.routers.prom_remote_write.httpx.AsyncClient", return_value=upstream):
        response = await client.post(
            "/api/v1/prom/remote_write",
            headers={"authorization": f"Bearer {VALID_TOKEN}"},
            content=b"payload",
        )
    assert response.status_code == 502
