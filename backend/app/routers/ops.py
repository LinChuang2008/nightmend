"""
AI 运维助手路由模块

提供：
- REST API：会话管理、Skill 列表
- WebSocket：前端实时通道（/api/v1/ops/ws/{session_id}）
- Agent 命令结果中转：接收 Agent 回传的 command_output/command_result，路由到对应 OpsAgentLoop
"""
import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.ops_session import OpsSession
from app.models.ops_message import OpsMessage
from app.schemas.ops import OpsSessionCreate, OpsSessionResponse, OpsSessionDetail, OpsMessageResponse, SkillInfo
from app.services.ops_agent_loop import get_or_create_loop, remove_loop, OPS_WS_CHANNEL
from app.services.ops_skill_loader import list_skills
from app.core.redis import get_redis
from app.services.auth_session import validate_active_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ops", tags=["ops"])

# 本进程内持有的前端 WebSocket 连接
_frontend_ws_clients: dict[str, WebSocket] = {}  # session_id -> WebSocket


async def _close_inactive_sessions(db: AsyncSession, user_id: int):
    """将 24 小时无活动的 active 会话标记为 closed。"""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    result = await db.execute(
        select(OpsSession).where(
            OpsSession.user_id == user_id,
            OpsSession.status == "active",
            OpsSession.updated_at < cutoff,
        )
    )
    stale_sessions = result.scalars().all()
    if not stale_sessions:
        return
    for s in stale_sessions:
        s.status = "closed"
    await db.commit()


# ─── REST API ──────────────────────────────────────────────────────────────────

@router.post("/sessions", response_model=OpsSessionResponse)
async def create_session(
    body: OpsSessionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = OpsSession(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        title=body.title,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@router.get("/sessions", response_model=list[OpsSessionResponse])
async def list_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _close_inactive_sessions(db, current_user.id)
    result = await db.execute(
        select(OpsSession)
        .where(OpsSession.user_id == current_user.id)
        .order_by(OpsSession.updated_at.desc())
        .limit(50)
    )
    return result.scalars().all()


@router.get("/sessions/{session_id}", response_model=OpsSessionDetail)
async def get_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _close_inactive_sessions(db, current_user.id)
    result = await db.execute(
        select(OpsSession).where(OpsSession.id == session_id, OpsSession.user_id == current_user.id)
    )
    session = result.scalar_one_or_none()
    if not session:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Session not found")

    msgs_result = await db.execute(
        select(OpsMessage)
        .where(OpsMessage.session_id == session_id, OpsMessage.compacted == False)  # noqa: E712
        .order_by(OpsMessage.created_at.asc())
    )
    messages = msgs_result.scalars().all()

    return OpsSessionDetail(
        id=session.id,
        title=session.title,
        status=session.status,
        target_host_id=session.target_host_id,
        token_count=session.token_count,
        created_at=session.created_at,
        updated_at=session.updated_at,
        messages=[OpsMessageResponse.model_validate(m) for m in messages],
    )


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(OpsSession).where(OpsSession.id == session_id, OpsSession.user_id == current_user.id)
    )
    session = result.scalar_one_or_none()
    if session:
        await db.delete(session)
        await db.commit()
    remove_loop(session_id)


@router.get("/skills", response_model=list[SkillInfo])
async def get_skills(_: User = Depends(get_current_user)):
    return list_skills()


# ─── 前端 WebSocket ────────────────────────────────────────────────────────────

@router.websocket("/ws/{session_id}")
async def ops_websocket(
    websocket: WebSocket,
    session_id: str,
    token: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    await websocket.accept()

    # JWT 认证：优先 Authorization header，其次 query param token，最后 cookie
    from app.core.security import decode_token
    auth_header = websocket.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        raw_token = auth_header[7:]
    elif token:
        raw_token = token
    else:
        cookies = {}
        cookie_header = websocket.headers.get("cookie", "")
        for part in cookie_header.split(";"):
            part = part.strip()
            if "=" in part:
                k, _, v = part.partition("=")
                cookies[k.strip()] = v.strip()
        raw_token = cookies.get("access_token")

    if not raw_token:
        await websocket.close(code=1008, reason="Missing token")
        return

    payload = decode_token(raw_token)
    if not payload or payload.get("type") != "access":
        await websocket.close(code=1008, reason="Invalid token")
        return
    user_id = int(payload.get("sub", 0))
    token_sid = payload.get("sid")
    if not token_sid:
        await websocket.close(code=1008, reason="Session expired, please login again")
        return

    if not await validate_active_session(user_id, token_sid):
        await websocket.close(code=1008, reason="Your account logged in elsewhere")
        return

    # 验证 session 归属
    result = await db.execute(
        select(OpsSession).where(OpsSession.id == session_id, OpsSession.user_id == user_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        await websocket.close(code=1008, reason="Session not found")
        return

    _frontend_ws_clients[session_id] = websocket
    loop = get_or_create_loop(session_id, user_id)

    # 用 asyncio.Queue 做进程内事件传递，彻底避免 Redis Pub/Sub 时序问题
    event_queue: asyncio.Queue = asyncio.Queue()

    # 启动 Queue 消费者：从 queue 读事件发给 WebSocket
    sender_task = asyncio.create_task(_queue_sender(event_queue, websocket))
    # 订阅 Redis ops_ws channel，接收跨 Worker 推送事件（如 command_output/title_update）
    redis_sub_task = asyncio.create_task(_redis_ops_ws_subscriber(session_id, event_queue))

    logger.info(f"Ops WebSocket connected: session_id={session_id} user_id={user_id}")

    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
            except asyncio.TimeoutError:
                # 定期检查 sid，确保新登录可以挤掉旧连接
                if not await validate_active_session(user_id, token_sid):
                    await websocket.close(code=1008, reason="Your account logged in elsewhere")
                    break
                continue

            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type")

            if msg_type == "user_message":
                content = msg.get("content", "")
                logger.info(f"Received user_message for session {session_id}: {content[:50]!r}")
                # 启动 AI 推理循环，事件直接放入 queue
                asyncio.create_task(
                    _run_agent_loop_serial(
                        loop,
                        content,
                        event_queue,
                        msg.get("host_id"),
                    )
                )

            elif msg_type == "command_confirm":
                await loop.handle_command_confirm(
                    msg.get("message_id", ""), msg.get("action", "reject")
                )

            elif msg_type == "ask_user_answer":
                await loop.handle_ask_user_answer(
                    msg.get("message_id", ""), msg.get("answer", "")
                )

            elif msg_type == "approval_reply":
                logger.info(f"Received approval_reply for session {session_id}: message_id={msg.get('message_id')}, action={msg.get('action')}")
                await loop.handle_approval_reply(
                    message_id=msg.get("message_id", ""),
                    action=msg.get("action", ""),
                    answer=msg.get("answer"),
                    request_type=msg.get("request_type"),
                )

            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})

            else:
                logger.warning(f"Unknown WS message type for session {session_id}: {msg_type}")

    except WebSocketDisconnect:
        logger.info(f"Ops WebSocket disconnected: session_id={session_id}")
    except Exception as e:
        logger.error(f"Ops WebSocket error: {e}", exc_info=True)
    finally:
        sender_task.cancel()
        redis_sub_task.cancel()
        _frontend_ws_clients.pop(session_id, None)


async def _run_agent_loop(loop, user_message: str, queue: asyncio.Queue, host_id: int | None = None):
    """在后台运行 AI 推理循环，将事件直接放入 asyncio.Queue。"""
    session_id = loop.session_id
    logger.info(f"Starting agent loop for session {session_id}")
    try:
        async for event in loop.run(user_message, host_id=host_id):
            await queue.put(event)
        logger.info(f"Agent loop completed for session {session_id}")
    except Exception as e:
        logger.error(f"Agent loop error for session {session_id}: {e}", exc_info=True)
        await queue.put({"event": "error", "message": str(e)})


async def _run_agent_loop_serial(
    loop,
    user_message: str,
    queue: asyncio.Queue,
    host_id: int | None = None,
):
    """运行单轮推理；串行由 OpsAgentLoop 内部全局锁保证。"""
    await _run_agent_loop(loop, user_message, queue, host_id=host_id)


async def _queue_sender(queue: asyncio.Queue, websocket: WebSocket):
    """从 asyncio.Queue 读取事件并发送给前端 WebSocket。"""
    try:
        while True:
            event = await queue.get()
            try:
                await websocket.send_json(event)
            except Exception as e:
                logger.warning(f"WebSocket send failed: {e}")
                break
    except asyncio.CancelledError:
        pass


async def _redis_ops_ws_subscriber(session_id: str, queue: asyncio.Queue):
    """订阅 Redis ops_ws:{session_id}，将事件转发到当前前端队列。"""
    redis = await get_redis()
    channel = f"{OPS_WS_CHANNEL}{session_id}"
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel)
    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            raw = message.get("data")
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="ignore")
            try:
                event = json.loads(raw)
            except Exception:
                continue
            await queue.put(event)
    except asyncio.CancelledError:
        pass
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()
