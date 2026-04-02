"""
告警诊断 SSE 流端点 (Alert Diagnosis SSE Stream Endpoint)

为 Prometheus Bridge 诊断模式提供实时事件流。
无需认证，供公开 Demo 页面使用。

架构:
    Redis SUBSCRIBE "nightmend:alert:diagnosis"
        → SSE event: diagnosis {JSON}
        → Browser EventSource
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import defaultdict
from datetime import datetime, timezone

import random

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.responses import StreamingResponse

from app.core.config import settings
from app.core.redis import get_redis

logger = logging.getLogger("nightmend.alert_stream")

router = APIRouter(prefix="/api/v1/demo", tags=["Demo"])

DIAGNOSIS_CHANNEL = "nightmend:alert:diagnosis"

_connection_count = 0
_connection_lock = asyncio.Lock()
_ip_connections: dict[str, int] = defaultdict(int)
_MAX_PER_IP = 5


async def _sse_generator(request: Request):
    """SSE async generator: subscribe to Redis and yield events."""
    global _connection_count
    client_ip = request.client.host if request.client else "unknown"
    pubsub = None

    try:
        # Send connected event
        now = datetime.now(timezone.utc).isoformat()
        yield f"event: connected\ndata: {json.dumps({'time': now})}\n\n"

        redis = await get_redis()
        pubsub = redis.pubsub()
        await pubsub.subscribe(DIAGNOSIS_CHANNEL)

        last_keepalive = time.monotonic()

        while True:
            if await request.is_disconnected():
                break

            message = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=1.0
            )

            if message and message["type"] == "message":
                data = message["data"]
                if isinstance(data, bytes):
                    data = data.decode("utf-8")
                yield f"event: diagnosis\ndata: {data}\n\n"
                last_keepalive = time.monotonic()
            elif time.monotonic() - last_keepalive >= 15.0:
                yield ": keepalive\n\n"
                last_keepalive = time.monotonic()

    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"SSE stream error for {client_ip}: {e}")
    finally:
        if pubsub:
            try:
                await pubsub.unsubscribe(DIAGNOSIS_CHANNEL)
                await pubsub.aclose()
            except Exception:
                pass
        async with _connection_lock:
            _connection_count -= 1
            _ip_connections[client_ip] = max(0, _ip_connections[client_ip] - 1)
            if _ip_connections[client_ip] == 0:
                _ip_connections.pop(client_ip, None)


@router.get("/alerts/stream")
async def stream_diagnoses(request: Request):
    """实时告警诊断 SSE 流 (Real-time Alert Diagnosis SSE Stream)

    无需认证。供 Demo 页面使用。
    """
    global _connection_count
    client_ip = request.client.host if request.client else "unknown"

    async with _connection_lock:
        if _connection_count >= settings.demo_sse_max_clients:
            return StreamingResponse(
                iter([json.dumps({"error": "Too many connections"})]),
                status_code=503,
                media_type="application/json",
            )
        if _ip_connections[client_ip] >= _MAX_PER_IP:
            return StreamingResponse(
                iter([json.dumps({"error": "Too many connections from this IP"})]),
                status_code=503,
                media_type="application/json",
            )
        _connection_count += 1
        _ip_connections[client_ip] += 1

    return StreamingResponse(
        _sse_generator(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        },
    )


# Demo trigger rate limiting: per-IP, 1 request per 5 seconds
_trigger_last: dict[str, float] = {}

_DEMO_SCENARIOS = [
    {
        "alertname": "HighCPUUsage",
        "instance": "192.168.1.100:9100",
        "severity": "warning",
        "summary": "CPU 使用率超过 85%",
        "diagnosis": {
            "root_cause": "Java 进程 PID 12345 (spring-boot-app) 占用 CPU 92%，GC 频繁触发导致 CPU 持续高位",
            "confidence": 0.87,
            "evidence": ["top 输出: java 92% CPU", "GC 日志: Full GC 每 30 秒触发一次", "heap 使用率 95%"],
            "recommendations": [
                "检查 JVM 堆内存配置: jmap -heap 12345",
                "分析 GC 日志: jstat -gcutil 12345 1000",
                "检查是否有内存泄漏: jmap -histo 12345 | head -20",
            ],
        },
    },
    {
        "alertname": "DiskSpaceCritical",
        "instance": "192.168.1.101:9100",
        "severity": "critical",
        "summary": "磁盘 /data 使用率 96%",
        "diagnosis": {
            "root_cause": "/data/logs 目录占用 180GB，应用日志未配置轮转，最早日志可追溯至 90 天前",
            "confidence": 0.95,
            "evidence": ["df -h: /data 96% used", "du -sh /data/logs: 180G", "ls -lt: oldest log 90 days"],
            "recommendations": [
                "立即清理过期日志: find /data/logs -mtime +30 -delete",
                "配置 logrotate: /etc/logrotate.d/app",
                "设置日志保留策略: 最多保留 7 天",
            ],
        },
    },
    {
        "alertname": "ServiceDown",
        "instance": "192.168.1.102:9100",
        "severity": "critical",
        "summary": "nginx 服务停止运行",
        "diagnosis": {
            "root_cause": "nginx 配置语法错误导致重启失败，最近一次配置变更在 15 分钟前",
            "confidence": 0.92,
            "evidence": ["systemctl status nginx: dead", "nginx -t: syntax error on line 47", "git log: config changed 15min ago"],
            "recommendations": [
                "检查配置语法: nginx -t",
                "查看最近变更: git diff HEAD~1 /etc/nginx/",
                "回滚配置: git checkout HEAD~1 -- /etc/nginx/nginx.conf && systemctl restart nginx",
            ],
        },
    },
    {
        "alertname": "OOMKiller",
        "instance": "192.168.1.103:9100",
        "severity": "critical",
        "summary": "进程被 OOM Killer 终止",
        "diagnosis": {
            "root_cause": "Redis 进程内存使用超过 maxmemory 限制 (2GB)，触发 OOM Killer。数据集增长超出预期。",
            "confidence": 0.89,
            "evidence": ["dmesg: Out of memory: Kill process redis-server", "redis-cli info memory: used 2.1GB", "maxmemory: 2GB"],
            "recommendations": [
                "调整 maxmemory: redis-cli config set maxmemory 4gb",
                "配置淘汰策略: redis-cli config set maxmemory-policy allkeys-lru",
                "分析大 key: redis-cli --bigkeys",
            ],
        },
    },
]


@router.post("/trigger")
async def trigger_demo_alert(request: Request):
    """触发一条模拟告警诊断事件 (Trigger a simulated alert diagnosis)

    无需认证。供 Demo 页面测试使用。每个 IP 5 秒内只能触发一次。
    """
    client_ip = request.client.host if request.client else "unknown"
    now = time.monotonic()

    last = _trigger_last.get(client_ip, 0)
    if now - last < 5.0:
        return JSONResponse(
            {"error": "请等待 5 秒后再试", "retry_after": 5},
            status_code=429,
        )
    _trigger_last[client_ip] = now

    scenario = random.choice(_DEMO_SCENARIOS)
    event = {
        **scenario,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "alert_id": None,
    }

    try:
        redis = await get_redis()
        await redis.publish(DIAGNOSIS_CHANNEL, json.dumps(event, ensure_ascii=False))
    except Exception as e:
        logger.error(f"Demo trigger failed to publish to Redis: {e}")
        return JSONResponse(
            {"error": "Redis 服务不可用，请稍后重试"},
            status_code=503,
        )

    return JSONResponse({"status": "ok", "event": event})
