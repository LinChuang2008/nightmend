"""
日志广播器 (Log Broadcaster)
独立模块，避免 routers/logs.py 和 services/log_service.py 之间的循环导入。
"""
import asyncio
import logging
from typing import List

logger = logging.getLogger(__name__)


class LogBroadcaster:
    """
    基于内存队列实现的发布-订阅模式，用于向多个 WebSocket 客户端实时推送日志数据。
    """

    def __init__(self):
        self._subscribers: List[asyncio.Queue] = []

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue):
        if queue in self._subscribers:
            self._subscribers.remove(queue)

    async def publish(self, message):
        for queue in self._subscribers:
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                # 队列已满：丢弃最旧的消息腾出空间，并记录警告
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                logger.warning(
                    "Log broadcast queue full, dropped oldest message to make room"
                )
                try:
                    queue.put_nowait(message)
                except asyncio.QueueFull:
                    pass


log_broadcaster = LogBroadcaster()
