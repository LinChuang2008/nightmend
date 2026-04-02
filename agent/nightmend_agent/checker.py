"""
服务健康检查模块。

支持 HTTP 和 TCP 两种协议的服务可用性检测，返回状态、响应时间等指标。
"""
import asyncio
import logging
import socket
import time

import httpx

from nightmend_agent.config import ServiceCheckConfig

logger = logging.getLogger(__name__)


async def check_http(svc: ServiceCheckConfig) -> dict:
    """执行 HTTP 健康检查。

    向目标 URL 发送 GET 请求，根据状态码判断服务状态：
    - 2xx/3xx/4xx 视为 up（服务可达）
    - 5xx 或异常视为 down

    Returns:
        包含 status、response_time_ms、status_code、error 的字典。
    """
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=svc.timeout) as client:
            resp = await client.get(svc.url)
        elapsed_ms = round((time.monotonic() - start) * 1000, 1)
        status = "up" if 200 <= resp.status_code < 500 else "down"
        return {
            "status": status,
            "response_time_ms": elapsed_ms,
            "status_code": resp.status_code,
            "error": None,
        }
    except Exception as e:
        elapsed_ms = round((time.monotonic() - start) * 1000, 1)
        return {
            "status": "down",
            "response_time_ms": elapsed_ms,
            "status_code": None,
            "error": str(e)[:500],
        }


async def check_tcp(svc: ServiceCheckConfig) -> dict:
    """执行 TCP 连接检查。

    尝试建立 TCP 连接，连接成功即视为服务可用。

    Returns:
        包含 status、response_time_ms、status_code、error 的字典。
    """
    host = svc.host or "localhost"
    port = svc.port
    if not port:
        return {"status": "down", "response_time_ms": 0, "status_code": None, "error": "No port configured"}

    start = time.monotonic()
    try:
        # 在线程池中执行阻塞式 TCP 连接，外层加超时控制
        loop = asyncio.get_event_loop()
        await asyncio.wait_for(
            loop.run_in_executor(None, _tcp_connect, host, port, svc.timeout),
            timeout=svc.timeout,
        )
        elapsed_ms = round((time.monotonic() - start) * 1000, 1)
        return {"status": "up", "response_time_ms": elapsed_ms, "status_code": None, "error": None}
    except Exception as e:
        elapsed_ms = round((time.monotonic() - start) * 1000, 1)
        return {"status": "down", "response_time_ms": elapsed_ms, "status_code": None, "error": str(e)[:500]}


def _tcp_connect(host: str, port: int, timeout: int):
    """同步 TCP 连接（供线程池调用）。"""
    sock = socket.create_connection((host, port), timeout=timeout)
    sock.close()


async def run_check(svc: ServiceCheckConfig) -> dict:
    """根据服务类型分派执行对应的健康检查。

    Args:
        svc: 服务检查配置。

    Returns:
        检查结果字典。
    """
    if svc.type == "http":
        return await check_http(svc)
    elif svc.type == "tcp":
        return await check_tcp(svc)
    else:
        return {"status": "down", "response_time_ms": 0, "status_code": None, "error": f"Unknown type: {svc.type}"}
