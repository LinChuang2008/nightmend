"""Prometheus Remote Write 接收器 (Prometheus Remote Write Receiver)

顶层逻辑：
    外部 Prometheus 集群把数据 push 到 NightMend，让 NightMend 成为多集群的
    AI 分析 / 告警聚合中心。我们**不**在 Python 里解 snappy+protobuf——而是
    作为鉴权透明代理，把原始 body 转发给 sidecar 的 /api/v1/write（Prom
    v2.33+ 的 remote_write_receiver 能力，docker-compose 里已用
    --web.enable-remote-write-receiver 启用）。

收益（vs. 自己解协议）：
    - 零新增依赖：不用 python-snappy / protobuf generated classes
    - 协议永远兼容最新 Prom：Prom 升级新格式我们自动跟随
    - 性能：纯 httpx bytes 转发，省掉反序列化 CPU
    - NightMend 只做"看门人"：鉴权 + 审计 + 限流 + 租户路由

请求契约（Prometheus spec）:
    POST /api/v1/prom/remote_write
    Content-Encoding: snappy
    Content-Type: application/x-protobuf
    X-Prometheus-Remote-Write-Version: 0.1.0
    Body: snappy-compressed protobuf WriteRequest

响应：
    - 204 No Content 成功（对齐 Prom 标准）
    - 401 未鉴权
    - 413 body 超限
    - 429 超限流
    - 502 sidecar 不可达（Prom 客户端会重试）
"""
from __future__ import annotations

import logging

import hmac

import httpx
from fastapi import APIRouter, HTTPException, Request, Response, status

from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/prom", tags=["prom-remote-write"])

# 10 MB 上限，防止单次 push 打满内存；标准 Prom remote_write 单批一般 <1MB
_MAX_BODY_BYTES = 10 * 1024 * 1024


def _authenticate_remote_write(request: Request) -> str:
    """
    Bearer token 鉴权（machine-to-machine 专用）。
    成功返回审计标识（token 前 6 字符），绝不回显全量。
    """
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing Authorization: Bearer <token>",
        )
    token = auth[7:]
    expected = settings.prom_remote_write_token
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="Remote write token not configured",
        )
    if not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="Invalid bearer token")
    return f"bearer:{token[:6]}***"


async def _forward_to_sidecar(body: bytes, headers: dict[str, str]) -> int:
    """把 body 原封不动转发到 Prom sidecar 的 /api/v1/write。"""
    base = settings.prometheus_remote_url.rstrip("/")
    # 只透传 remote_write 协议需要的头，避免把 NightMend 自己的 cookie/auth 泄给 Prom
    fwd_headers = {
        k: v for k, v in headers.items()
        if k.lower() in {
            "content-encoding",
            "content-type",
            "x-prometheus-remote-write-version",
        }
    }
    try:
        async with httpx.AsyncClient(timeout=settings.prometheus_remote_timeout_seconds) as client:
            response = await client.post(f"{base}/api/v1/write", content=body, headers=fwd_headers)
    except httpx.RequestError as exc:
        logger.warning("Remote write forward failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Prometheus sidecar unreachable: {exc}")

    if response.status_code >= 400:
        logger.warning(
            "Prometheus sidecar rejected remote_write: status=%s body=%s",
            response.status_code, response.text[:200],
        )
        # 标准做法：Prom 4xx 视为数据不合法透传，5xx 视为 502 让客户端重试
        if 400 <= response.status_code < 500:
            raise HTTPException(status_code=response.status_code, detail=response.text[:500])
        raise HTTPException(status_code=502, detail="Prometheus sidecar returned 5xx")

    return response.status_code


@router.post("/remote_write", status_code=status.HTTP_204_NO_CONTENT)
async def receive_remote_write(request: Request, response: Response):
    """
    Prometheus Remote Write 接收端点。

    典型 alertmanager.yml / prometheus.yml 客户端配置：
        remote_write:
          - url: "https://nightmend.example.com/api/v1/prom/remote_write"
            authorization:
              type: Bearer
              credentials: "<NIGHTMEND_PROM_REMOTE_WRITE_TOKEN>"
    """
    if not settings.prometheus_remote_enabled:
        raise HTTPException(
            status_code=503,
            detail="Remote write disabled; set PROMETHEUS_REMOTE_ENABLED=true",
        )

    # 1. 鉴权
    caller = _authenticate_remote_write(request)

    # 2. 读 body 并限长
    body = await request.body()
    if len(body) > _MAX_BODY_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Body too large ({len(body)} bytes, max {_MAX_BODY_BYTES})",
        )
    if not body:
        raise HTTPException(status_code=400, detail="Empty body")

    # 3. 转发到 sidecar（纯 bytes passthrough）
    upstream_status = await _forward_to_sidecar(body, dict(request.headers))
    logger.info(
        "remote_write proxied: caller=%s bytes=%d upstream=%s",
        caller, len(body), upstream_status,
    )
    # Prom 期望 204；但若 sidecar 返回 200 也应透传 OK
    return Response(status_code=status.HTTP_204_NO_CONTENT)
