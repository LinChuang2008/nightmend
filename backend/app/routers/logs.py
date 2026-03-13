"""
日志管理路由 (Log Management Router)

功能说明：提供完整的日志管理功能，包括搜索查询、统计分析和实时推送
核心职责：
  - 多维度日志搜索和过滤（关键字、主机、服务、级别、时间范围）
  - 日志统计分析（按级别和时间分桶聚合）
  - WebSocket 实时日志流推送和客户端订阅管理
  - 基于内存的发布-订阅模式实现高性能日志广播
依赖关系：依赖 LogEntry 和 Host 数据模型，集成 WebSocket 通信
API端点：GET /api/v1/logs, GET /api/v1/logs/stats, WebSocket /ws/logs

Author: VigilOps Team
"""

import asyncio
import json
from datetime import datetime

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.security import decode_token
from app.models.host import Host
from app.models.log_entry import LogEntry
from app.models.user import User
from app.schemas.log_entry import (
    LogEntryResponse,
    LogSearchResponse,
    LogStatsResponse,
    LevelCount,
    TimeCount,
)
from app.services.log_service import get_log_service

router = APIRouter(prefix="/api/v1/logs", tags=["logs"])


# ── 日志广播器从独立模块导入，避免循环导入 (F052) ──────────────────
from app.services.log_broadcaster import log_broadcaster  # noqa: E402


class _LogBroadcasterLegacy:
    """
    日志广播器 (Log Broadcaster)
    
    基于内存队列实现的发布-订阅模式，用于向多个 WebSocket 客户端实时推送日志数据。
    采用异步非阻塞设计，当客户端消费速度过慢时会自动丢弃消息，避免内存溢出。
    
    特性：
    - 支持多订阅者同时接收日志流
    - 队列满时自动丢弃消息，保护服务器资源
    - 线程安全的订阅者管理
    """

    def __init__(self):
        self._subscribers: list[asyncio.Queue] = []  # 维护所有活跃的订阅队列

    def subscribe(self) -> asyncio.Queue:
        """
        创建新的订阅队列 (Create New Subscription)
        
        为每个 WebSocket 连接创建独立的异步队列，用于接收广播消息。
        队列设置最大容量以防止内存无限增长。
        
        Returns:
            asyncio.Queue: 新创建的订阅队列，最大容量 256 条消息
        """
        q: asyncio.Queue = asyncio.Queue(maxsize=256)  # 限制队列大小防止内存泄漏
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        """
        移除订阅队列 (Remove Subscription)
        
        当 WebSocket 连接断开时，清理对应的订阅队列，释放资源。
        
        Args:
            q: 要移除的订阅队列
        """
        if q in self._subscribers:  # 防止重复移除导致异常
            self._subscribers.remove(q)

    async def publish(self, entries: list[dict]):
        """
        向所有订阅者广播日志条目 (Broadcast Log Entries)
        
        将新的日志条目推送给所有活跃的订阅者。采用非阻塞策略，
        如果某个订阅者的队列已满（通常是客户端处理过慢），则丢弃该条目。
        
        Args:
            entries: 要广播的日志条目列表，每个条目为字典格式
        """
        # 使用 list() 创建快照，避免迭代过程中列表被修改
        for q in list(self._subscribers):
            for entry in entries:
                try:
                    q.put_nowait(entry)  # 非阻塞放入队列
                except asyncio.QueueFull:
                    pass  # 消费者处理过慢，丢弃该条目避免阻塞整个广播流程


# log_broadcaster 已从 app.services.log_broadcaster 导入


# ── 日志搜索与筛选 (F049 + F050) ─────────────────────────────────────
@router.get("", response_model=LogSearchResponse)
async def search_logs(
    q: str | None = Query(None, description="Full-text search keyword"),
    host_id: int | None = Query(None),
    service: str | None = Query(None),
    level: str | None = Query(None, description="Comma-separated levels, e.g. ERROR,WARN"),
    start_time: datetime | None = Query(None),
    end_time: datetime | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    搜索日志条目 (Search Log Entries)
    
    支持多维度日志检索和过滤，用于日志分析和故障排查。
    提供全文搜索、精确匹配和时间范围筛选，支持分页查询大量日志数据。
    
    Args:
        q: 全文搜索关键字，在日志消息中模糊匹配
        host_id: 按主机ID精确筛选
        service: 按服务名筛选（如 nginx, mysql 等）
        level: 日志级别筛选，支持多值逗号分隔（如 "ERROR,WARN"）
        start_time: 查询起始时间
        end_time: 查询结束时间
        page: 页码，从1开始
        page_size: 每页条数，限制1-200条
        _user: 当前认证用户
        db: 数据库会话
        
    Returns:
        LogSearchResponse: 包含日志条目列表、总数和分页信息
    """
    # 使用新的日志服务进行搜索
    log_service = await get_log_service(db)
    log_items, total = await log_service.search_logs(
        q=q, host_id=host_id, service=service, level=level,
        start_time=start_time, end_time=end_time,
        page=page, page_size=page_size
    )
    
    # 转换为API响应格式
    items = []
    for log_item in log_items:
        # 如果是字典格式（来自新后端），转换为LogEntryResponse
        if isinstance(log_item, dict):
            item = LogEntryResponse(
                id=log_item.get('id'),
                host_id=log_item.get('host_id'),
                service=log_item.get('service'),
                source=log_item.get('source'),
                level=log_item.get('level'),
                message=log_item.get('message'),
                timestamp=log_item.get('timestamp'),
                created_at=log_item.get('created_at'),
                hostname=log_item.get('hostname')
            )
            items.append(item)
        else:
            # 兼容旧格式
            items.append(log_item)

    return LogSearchResponse(items=items, total=total, page=page, page_size=page_size)


# ── 日志统计 (F053) ──────────────────────────────────────────────────
@router.get("/stats", response_model=LogStatsResponse)
async def log_stats(
    host_id: int | None = Query(None),
    service: str | None = Query(None),
    period: str = Query("1h", description="Time bucket: 1h or 1d"),
    start_time: datetime | None = Query(None),
    end_time: datetime | None = Query(None),
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    获取日志统计数据 (Get Log Statistics)
    
    提供日志数据的聚合统计分析，支持按日志级别分组和时间分桶统计。
    用于日志监控仪表盘的图表展示和趋势分析。
    
    Args:
        host_id: 可选的主机ID筛选
        service: 可选的服务名筛选
        period: 时间分桶粒度，支持 "1h"（按小时）或 "1d"（按天）
        start_time: 统计起始时间
        end_time: 统计结束时间
        _user: 当前认证用户
        db: 数据库会话
        
    Returns:
        LogStatsResponse: 包含按级别统计和时间序列统计的响应对象
    """
    # 使用新的日志服务进行统计
    log_service = await get_log_service(db)
    stats_data = await log_service.get_stats(
        host_id=host_id, service=service, period=period,
        start_time=start_time, end_time=end_time
    )
    
    # 转换为API响应格式
    by_level = [LevelCount(level=item.get("level", "UNKNOWN"), count=item.get("count", 0)) 
                for item in stats_data.get("by_level", [])]
    by_time = [TimeCount(time_bucket=item.get("time_bucket"), count=item.get("count", 0)) 
               for item in stats_data.get("by_time", [])]

    return LogStatsResponse(by_level=by_level, by_time=by_time)


# ── WebSocket 实时日志流 (F052) ───────────────────────────────────────
ws_router = APIRouter()  # 独立的 WebSocket 路由器


@ws_router.websocket("/ws/logs")
async def ws_logs(
    websocket: WebSocket,
    token: str = Query(default=""),
    host_id: int | None = Query(None),
    service: str | None = Query(None),
    level: str | None = Query(None),
):
    """
    WebSocket 实时日志流 (WebSocket Real-time Log Stream)

    通过 query 参数 ?token=JWT 进行认证。

    Args:
        websocket: WebSocket 连接对象
        token: JWT 访问令牌（通过 query 参数传递）
        host_id: 可选的主机ID过滤条件
        service: 可选的服务名过滤条件
        level: 可选的日志级别过滤条件，支持多值逗号分隔
    """
    # WebSocket 认证
    if not token:
        token = websocket.cookies.get("access_token", "")
    payload = decode_token(token) if token else None
    if not payload or payload.get("type") != "access":
        await websocket.close(code=4001, reason="Unauthorized")
        return

    await websocket.accept()
    queue = log_broadcaster.subscribe()  # 订阅日志广播队列
    
    try:
        while True:  # 持续监听和推送日志
            entry = await queue.get()  # 从广播队列中获取新日志条目
            
            # 按客户端指定的条件进行服务端过滤
            if host_id is not None and entry.get("host_id") != host_id:
                continue  # 主机ID不匹配，跳过此条目
            if service and entry.get("service") != service:
                continue  # 服务名不匹配，跳过此条目
            if level:
                levels = [l.strip().upper() for l in level.split(",")]
                if entry.get("level", "").upper() not in levels:
                    continue  # 日志级别不匹配，跳过此条目
                    
            # 向客户端推送符合条件的日志条目
            await websocket.send_json(entry)
    except WebSocketDisconnect:
        pass  # 客户端主动断开连接，正常情况
    finally:
        # 连接结束时清理资源，取消订阅避免内存泄漏
        log_broadcaster.unsubscribe(queue)
