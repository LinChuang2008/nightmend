"""
服务健康检查后台任务 (Service Health Check Background Task)

定期检查所有 is_active=True 的服务，确保即使是手动创建的服务也能被检查。
适用于只能通过 localhost 访问的内部服务。

Periodically checks all active services, ensuring even manually created services are checked.
Suitable for internal services only accessible via localhost.
"""
import asyncio
import logging
import time
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session
from app.models.service import Service, ServiceCheck

logger = logging.getLogger(__name__)

# 检查间隔（秒）
CHECK_INTERVAL = 30


async def check_http_service(url: str, timeout: int = 10, expected_status: int = None) -> dict:
    """检查 HTTP 服务"""
    start_time = time.time()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, follow_redirects=True)
            response_time_ms = int((time.time() - start_time) * 1000)

            if expected_status and resp.status_code != expected_status:
                return {
                    "healthy": False,
                    "response_time_ms": response_time_ms,
                    "status_code": resp.status_code,
                    "error": f"Expected status {expected_status}, got {resp.status_code}"
                }

            return {
                "healthy": 200 <= resp.status_code < 400,
                "response_time_ms": response_time_ms,
                "status_code": resp.status_code,
                "error": None
            }
    except Exception as e:
        return {
            "healthy": False,
            "response_time_ms": int((time.time() - start_time) * 1000),
            "status_code": None,
            "error": str(e)
        }


async def check_tcp_service(host: str, port: int, timeout: int = 10) -> dict:
    """检查 TCP 服务"""
    start_time = time.time()
    try:
        # 使用 asyncio 打开 TCP 连接
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout
        )
        writer.close()
        await writer.wait_closed()
        response_time_ms = int((time.time() - start_time) * 1000)
        return {
            "healthy": True,
            "response_time_ms": response_time_ms,
            "error": None
        }
    except Exception as e:
        return {
            "healthy": False,
            "response_time_ms": int((time.time() - start_time) * 1000),
            "error": str(e)
        }


async def check_single_service(db: AsyncSession, service: Service) -> dict:
    """检查单个服务的健康状态

    Args:
        db: 数据库会话
        service: 服务对象

    Returns:
        检查结果字典
    """
    target = service.target or ""
    service_type = service.type or "tcp"

    # HTTP 检查
    if service_type == "http" or target.startswith("http://") or target.startswith("https://"):
        result = await check_http_service(
            url=target,
            timeout=service.timeout or 10,
            expected_status=service.expected_status
        )
        return {
            "status": "up" if result["healthy"] else "down",
            "response_time_ms": result.get("response_time_ms"),
            "status_code": result.get("status_code"),
            "error": result.get("error"),
        }

    # TCP 检查
    try:
        # 解析 host:port
        if ":" in target:
            host, port_str = target.rsplit(":", 1)
            port = int(port_str)
        else:
            host = "localhost"
            port = int(target)

        result = await check_tcp_service(
            host=host or "localhost",
            port=port,
            timeout=service.timeout or 10
        )
        return {
            "status": "up" if result["healthy"] else "down",
            "response_time_ms": result.get("response_time_ms"),
            "status_code": None,
            "error": result.get("error"),
        }
    except Exception as e:
        return {
            "status": "down",
            "response_time_ms": None,
            "status_code": None,
            "error": str(e),
        }


async def check_all_services():
    """检查所有活跃的服务

    从数据库获取所有 is_active=True 的服务，逐个检查并记录结果。
    """
    async with async_session() as db:
        # 获取所有活跃服务
        result = await db.execute(
            select(Service).where(Service.is_active == True)
        )
        services = result.scalars().all()

        if not services:
            logger.debug("No active services to check")
            return

        logger.info(f"Checking {len(services)} active services")

        now = datetime.now(timezone.utc)
        checked_count = 0
        up_count = 0

        for service in services:
            try:
                # 检查服务
                check_result = await check_single_service(db, service)

                # 创建检查记录
                service_check = ServiceCheck(
                    service_id=service.id,
                    status=check_result["status"],
                    response_time_ms=check_result.get("response_time_ms"),
                    status_code=check_result.get("status_code"),
                    error=check_result.get("error"),
                    checked_at=now,
                )
                db.add(service_check)

                # 更新服务状态
                service.status = check_result["status"]

                checked_count += 1
                if check_result["status"] == "up":
                    up_count += 1

            except Exception as e:
                logger.warning(f"Failed to check service {service.id} ({service.name}): {e}")

        # 提交所有更改
        await db.commit()

        logger.info(f"Service check completed: {checked_count} checked, {up_count} up, {checked_count - up_count} down")


async def service_checker_loop():
    """服务检查主循环"""
    logger.info("Service checker task started")

    while True:
        try:
            await check_all_services()
        except Exception as e:
            logger.error(f"Service checker error: {e}", exc_info=True)

        await asyncio.sleep(CHECK_INTERVAL)


async def start_service_checker():
    """启动服务检查任务"""
    asyncio.create_task(service_checker_loop())
