"""Prometheus file_sd 后台同步任务。

每 SYNC_INTERVAL 秒把 Host / Service 表导出到 targets 目录。
Host 新增/下线只要在下次刷新窗口内即可被 sidecar 感知，无需重启。

任务注册：由 main.py lifespan 按 PROMETHEUS_REMOTE_ENABLED 条件启动。
"""
import asyncio
import logging

from app.core.config import settings
from app.core.database import async_session
from app.services.prom_file_sd import sync_file_sd

logger = logging.getLogger(__name__)

SYNC_INTERVAL = 60  # 秒；Prom file_sd refresh_interval 是 30s，导出 60s 就能覆盖


async def prom_file_sd_loop() -> None:
    """Loop 本体；异常不上抛，任务 monitor 会用 30s 健康检查兜底。"""
    logger.info("Prometheus file_sd sync task started (interval=%ss)", SYNC_INTERVAL)
    while True:
        try:
            if settings.prometheus_remote_enabled:
                async with async_session() as db:
                    await sync_file_sd(db)
        except Exception:
            logger.exception("Error syncing Prometheus file_sd targets")
        await asyncio.sleep(SYNC_INTERVAL)
