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
from sqlalchemy import select, exists, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_admin_user, get_current_user
from app.core.config import settings
from app.models.user import User
from app.models.ops_session import OpsSession
from app.models.ops_message import OpsMessage
from app.models.setting import Setting
from app.schemas.ops import (
    OpsSessionCreate,
    OpsSessionResponse,
    OpsSessionDetail,
    OpsMessageResponse,
    SkillInfo,
    OpsAIConfigResponse,
    OpsAIConfigCreate,
    OpsAIConfigUpdate,
    OpsAIConfigImport,
)
from app.services.ops_agent_loop import get_or_create_loop, remove_loop, OPS_WS_CHANNEL
from app.services.ops_skill_loader import list_skills
from app.core.redis import get_redis
from app.services.auth_session import validate_active_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ops", tags=["ops"])

# 本进程内持有的前端 WebSocket 连接
_frontend_ws_clients: dict[str, WebSocket] = {}  # session_id -> WebSocket

_AI_SETTING_KEYS = {
    "configs": "ops_ai_configs_v2",
    "default_id": "ops_ai_default_config_id",
    "base_url": "ops_ai_base_url",
    "model": "ops_ai_model",
    "api_key": "ops_ai_api_key",
    "max_tokens": "ops_ai_max_tokens",
    "extra_context": "ops_ai_extra_context",
}

_AI_FEATURE_POLICIES: dict[str, dict] = {
    "default": {"label": "默认配置（全局回退）", "max_models": 1},
    "ops_assistant": {"label": "AI 运维助手", "max_models": 999},
    "ai_insight": {"label": "AI 智能洞察", "max_models": 1},
    "ops_report": {"label": "AI 运维报告", "max_models": 1},
    "alert_analysis": {"label": "AI 告警分析", "max_models": 1},
    "log_analysis": {"label": "AI 日志分析", "max_models": 1},
    "runbook_generation": {"label": "AI Runbook 生成", "max_models": 1},
}


async def _get_setting_value(db: AsyncSession, key: str) -> str | None:
    result = await db.execute(select(Setting).where(Setting.key == key))
    setting = result.scalar_one_or_none()
    return setting.value if setting else None


async def _set_setting_value(db: AsyncSession, key: str, value: str, description: str = ""):
    result = await db.execute(select(Setting).where(Setting.key == key))
    setting = result.scalar_one_or_none()
    if setting:
        setting.value = value
        if description and not setting.description:
            setting.description = description
    else:
        db.add(Setting(key=key, value=value, description=description))


async def _load_ai_configs(db: AsyncSession) -> tuple[list[dict], str]:
    raw = await _get_setting_value(db, _AI_SETTING_KEYS["configs"])
    default_id = await _get_setting_value(db, _AI_SETTING_KEYS["default_id"]) or ""
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return data, default_id
        except json.JSONDecodeError:
            pass

    # 向后兼容：把旧单配置迁移成 v2 列表
    legacy_base_url = await _get_setting_value(db, _AI_SETTING_KEYS["base_url"]) or settings.ai_api_base
    legacy_model = await _get_setting_value(db, _AI_SETTING_KEYS["model"]) or settings.ai_model
    legacy_api_key = await _get_setting_value(db, _AI_SETTING_KEYS["api_key"]) or settings.ai_api_key
    legacy_max_tokens = await _get_setting_value(db, _AI_SETTING_KEYS["max_tokens"])
    legacy_extra_context = await _get_setting_value(db, _AI_SETTING_KEYS["extra_context"]) or ""
    try:
        max_output_tokens = int(legacy_max_tokens) if legacy_max_tokens is not None else settings.ai_max_tokens
    except ValueError:
        max_output_tokens = settings.ai_max_tokens

    # 回退配置使用稳定 ID，避免前端编辑时因随机 ID 变化导致 404
    cfg_id = "legacy-default"
    cfg = {
        "id": cfg_id,
        "feature_key": "ops_assistant",
        "name": "AI 运维助手默认模型",
        "base_url": legacy_base_url,
        "model": legacy_model,
        "api_key": legacy_api_key,
        "max_output_tokens": max_output_tokens,
        "supports_deep_thinking": False,
        "deep_thinking_max_tokens": 0,
        "model_context_tokens": 200000,
        "allowed_context_tokens": 120000,
        "extra_context": legacy_extra_context,
        "enabled": True,
    }
    return [cfg], cfg_id


def _sanitize_ai_config(cfg: dict, default_id: str) -> OpsAIConfigResponse:
    feature_key = _feature_key_of(cfg)
    api_key = str(cfg.get("api_key") or "").strip()
    api_key_mask = None
    if api_key:
        if len(api_key) <= 4:
            api_key_mask = "*" * len(api_key)
        else:
            api_key_mask = f"{api_key[:3]}****{api_key[-4:]}"
    return OpsAIConfigResponse(
        id=str(cfg.get("id") or ""),
        feature_key=feature_key,
        name=str(cfg.get("name") or _AI_FEATURE_POLICIES.get(feature_key, {}).get("label") or "未命名功能"),
        base_url=str(cfg.get("base_url") or settings.ai_api_base),
        model=str(cfg.get("model") or settings.ai_model),
        max_output_tokens=int(cfg.get("max_output_tokens") or settings.ai_max_tokens),
        supports_deep_thinking=bool(cfg.get("supports_deep_thinking", False)),
        deep_thinking_max_tokens=int(cfg.get("deep_thinking_max_tokens") or 0),
        model_context_tokens=int(cfg.get("model_context_tokens") or 200000),
        allowed_context_tokens=int(cfg.get("allowed_context_tokens") or 120000),
        extra_context=str(cfg.get("extra_context") or ""),
        has_api_key=bool(api_key),
        api_key_mask=api_key_mask,
        is_default=str(cfg.get("id") or "") == default_id,
        enabled=bool(cfg.get("enabled", True)),
    )


async def _save_ai_configs(db: AsyncSession, configs: list[dict], default_id: str):
    await _set_setting_value(
        db,
        _AI_SETTING_KEYS["configs"],
        json.dumps(configs, ensure_ascii=False),
        "Ops AI multi business config list",
    )
    await _set_setting_value(
        db,
        _AI_SETTING_KEYS["default_id"],
        default_id,
        "Ops AI default config id",
    )


def _feature_key_of(cfg: dict) -> str:
    return str(cfg.get("feature_key") or cfg.get("business_key") or "ops_assistant")


def _enforce_feature_model_limit(configs: list[dict], feature_key: str):
    from fastapi import HTTPException

    policy = _AI_FEATURE_POLICIES.get(feature_key)
    if not policy:
        raise HTTPException(status_code=400, detail=f"不支持的 feature_key: {feature_key}")
    if policy["max_models"] <= 1:
        count = sum(1 for c in configs if _feature_key_of(c) == feature_key)
        if count >= 1:
            raise HTTPException(status_code=400, detail=f"{policy['label']} 仅允许配置一个模型")


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


async def _cleanup_empty_sessions(
    db: AsyncSession,
    user_id: int,
    keep_session_id: str | None = None,
) -> OpsSession | None:
    """清理多余空白会话，仅保留一个最近的空白草稿。"""
    empty_message_exists = exists(
        select(1).where(OpsMessage.session_id == OpsSession.id)
    )
    result = await db.execute(
        select(OpsSession)
        .where(
            OpsSession.user_id == user_id,
            OpsSession.status == "active",
            or_(OpsSession.title.is_(None), OpsSession.title == ""),
            ~empty_message_exists,
        )
        .order_by(OpsSession.updated_at.desc(), OpsSession.created_at.desc())
    )
    empty_sessions = result.scalars().all()
    if not empty_sessions:
        return None

    preserved: OpsSession | None = None
    for session in empty_sessions:
        if keep_session_id and session.id == keep_session_id:
            preserved = session
            break
    if preserved is None:
        preserved = empty_sessions[0]

    for session in empty_sessions:
        if session.id == preserved.id:
            continue
        await db.delete(session)
        remove_loop(session.id)

    await db.commit()
    await db.refresh(preserved)
    return preserved


# ─── REST API ──────────────────────────────────────────────────────────────────

@router.post("/sessions", response_model=OpsSessionResponse)
async def create_session(
    body: OpsSessionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # 清理该用户残留的空白草稿（无标题、无消息），避免堆积。
    # POST /sessions 是用户显式动作（含首次进入页面或点击"新建会话"），
    # 必须总是返回一个全新的会话，且尊重 body.title。
    empty_message_exists = exists(
        select(1).where(OpsMessage.session_id == OpsSession.id)
    )
    stale_drafts = await db.execute(
        select(OpsSession).where(
            OpsSession.user_id == current_user.id,
            OpsSession.status == "active",
            or_(OpsSession.title.is_(None), OpsSession.title == ""),
            ~empty_message_exists,
            # 跳过最近 60 秒内更新过的 session，避免删除正在推理中的会话
            OpsSession.updated_at < (datetime.now(timezone.utc) - timedelta(seconds=60)),
        )
    )
    for draft in stale_drafts.scalars().all():
        await db.delete(draft)
        remove_loop(draft.id)

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
    await _cleanup_empty_sessions(db, current_user.id)
    visible_message_exists = exists(
        select(1).where(
            OpsMessage.session_id == OpsSession.id,
            OpsMessage.compacted == False,  # noqa: E712
        )
    )
    result = await db.execute(
        select(OpsSession)
        .where(
            OpsSession.user_id == current_user.id,
            or_(
                OpsSession.status == "active",
                visible_message_exists,
            ),
        )
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
        prompt_tokens=session.prompt_tokens,
        completion_tokens=session.completion_tokens,
        total_tokens=session.total_tokens,
        context_limit_tokens=session.context_limit_tokens,
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


@router.get("/ai-config-features")
async def list_ai_config_features(_: User = Depends(get_current_user)):
    return [
        {"feature_key": key, "label": value["label"], "max_models": value["max_models"]}
        for key, value in _AI_FEATURE_POLICIES.items()
    ]


@router.get("/ai-configs", response_model=list[OpsAIConfigResponse])
async def list_ai_configs(
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    configs, default_id = await _load_ai_configs(db)
    enabled_configs = [c for c in configs if bool(c.get("enabled", True))]
    return [_sanitize_ai_config(c, default_id) for c in enabled_configs]


@router.get("/ai-configs/admin", response_model=list[OpsAIConfigResponse])
async def list_ai_configs_admin(
    _: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    configs, default_id = await _load_ai_configs(db)
    return [_sanitize_ai_config(c, default_id) for c in configs]


@router.post("/ai-configs", response_model=OpsAIConfigResponse)
async def create_ai_config(
    body: OpsAIConfigCreate,
    _: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    configs, default_id = await _load_ai_configs(db)
    feature_key = body.feature_key.strip()
    _enforce_feature_model_limit(configs, feature_key)
    new_cfg = {
        "id": str(uuid.uuid4()),
        "feature_key": feature_key,
        "name": body.name.strip(),
        "base_url": body.base_url.strip(),
        "model": body.model.strip(),
        "api_key": (body.api_key or "").strip(),
        "max_output_tokens": int(body.max_output_tokens),
        "supports_deep_thinking": bool(body.supports_deep_thinking),
        "deep_thinking_max_tokens": int(body.deep_thinking_max_tokens),
        "model_context_tokens": int(body.model_context_tokens),
        "allowed_context_tokens": int(body.allowed_context_tokens),
        "extra_context": body.extra_context or "",
        "enabled": bool(body.enabled),
    }
    configs.append(new_cfg)
    if not default_id:
        default_id = new_cfg["id"]
    await _save_ai_configs(db, configs, default_id)
    await db.commit()
    return _sanitize_ai_config(new_cfg, default_id)


@router.put("/ai-configs/{config_id}", response_model=OpsAIConfigResponse)
async def update_ai_config(
    config_id: str,
    body: OpsAIConfigUpdate,
    _: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    from fastapi import HTTPException

    configs, default_id = await _load_ai_configs(db)
    target = next((c for c in configs if str(c.get("id")) == config_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="AI 配置不存在")

    updates = body.model_dump(exclude_unset=True)
    if "feature_key" in updates and updates["feature_key"] is not None:
        new_feature_key = str(updates["feature_key"]).strip()
        old_feature_key = _feature_key_of(target)
        if new_feature_key != old_feature_key:
            _enforce_feature_model_limit([c for c in configs if str(c.get("id")) != config_id], new_feature_key)
        target["feature_key"] = new_feature_key
    if "name" in updates and updates["name"] is not None:
        target["name"] = str(updates["name"]).strip()
    if "base_url" in updates and updates["base_url"] is not None:
        target["base_url"] = str(updates["base_url"]).strip()
    if "model" in updates and updates["model"] is not None:
        target["model"] = str(updates["model"]).strip()
    if "api_key" in updates and updates["api_key"] is not None:
        api_key = str(updates["api_key"]).strip()
        # 编辑时留空表示“不更新”，避免把已保存密钥清空
        if api_key:
            target["api_key"] = api_key
    if "max_output_tokens" in updates and updates["max_output_tokens"] is not None:
        target["max_output_tokens"] = int(updates["max_output_tokens"])
    if "supports_deep_thinking" in updates and updates["supports_deep_thinking"] is not None:
        target["supports_deep_thinking"] = bool(updates["supports_deep_thinking"])
    if "deep_thinking_max_tokens" in updates and updates["deep_thinking_max_tokens"] is not None:
        target["deep_thinking_max_tokens"] = int(updates["deep_thinking_max_tokens"])
    if "model_context_tokens" in updates and updates["model_context_tokens"] is not None:
        target["model_context_tokens"] = int(updates["model_context_tokens"])
    if "allowed_context_tokens" in updates and updates["allowed_context_tokens"] is not None:
        target["allowed_context_tokens"] = int(updates["allowed_context_tokens"])
    if "extra_context" in updates and updates["extra_context"] is not None:
        target["extra_context"] = str(updates["extra_context"])
    if "enabled" in updates and updates["enabled"] is not None:
        target["enabled"] = bool(updates["enabled"])

    await _save_ai_configs(db, configs, default_id)
    await db.commit()
    return _sanitize_ai_config(target, default_id)


@router.post("/ai-configs/{config_id}/default", response_model=OpsAIConfigResponse)
async def set_default_ai_config(
    config_id: str,
    _: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    from fastapi import HTTPException

    configs, _ = await _load_ai_configs(db)
    target = next((c for c in configs if str(c.get("id")) == config_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="AI 配置不存在")
    await _save_ai_configs(db, configs, config_id)
    await db.commit()
    return _sanitize_ai_config(target, config_id)


@router.delete("/ai-configs/{config_id}", status_code=204)
async def delete_ai_config(
    config_id: str,
    _: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    from fastapi import HTTPException

    configs, default_id = await _load_ai_configs(db)
    filtered = [c for c in configs if str(c.get("id")) != config_id]
    if len(filtered) == len(configs):
        raise HTTPException(status_code=404, detail="AI 配置不存在")
    if not filtered:
        raise HTTPException(status_code=400, detail="至少保留一个 AI 配置")
    if default_id == config_id:
        default_id = str(filtered[0].get("id"))
    await _save_ai_configs(db, filtered, default_id)
    await db.commit()


@router.post("/ai-configs/import", response_model=OpsAIConfigResponse)
async def import_ai_config(
    body: OpsAIConfigImport,
    _: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    raw = body.config or {}
    mapped = {
        "base_url": raw.get("base_url") or raw.get("baseURL") or raw.get("api_base"),
        "api_key": raw.get("api_key") or raw.get("apiKey"),
        "model": raw.get("model"),
        "max_output_tokens": raw.get("max_output_tokens") or raw.get("max_tokens") or raw.get("maxTokens"),
        "supports_deep_thinking": raw.get("supports_deep_thinking") or raw.get("supportsDeepThinking"),
        "deep_thinking_max_tokens": raw.get("deep_thinking_max_tokens") or raw.get("deepThinkingMaxTokens"),
        "model_context_tokens": raw.get("model_context_tokens") or raw.get("modelContextTokens"),
        "allowed_context_tokens": raw.get("allowed_context_tokens") or raw.get("allowedContextTokens"),
        "extra_context": raw.get("context") or raw.get("extra_context") or "",
    }

    payload = OpsAIConfigCreate(
        feature_key=(body.feature_key or raw.get("feature_key") or raw.get("business_key") or "ops_assistant").strip(),
        name=(body.name or raw.get("name") or "未命名功能").strip(),
        base_url=str(mapped["base_url"] or settings.ai_api_base).strip(),
        model=str(mapped["model"] or settings.ai_model).strip(),
        api_key=str(mapped["api_key"] or "").strip(),
        max_output_tokens=int(mapped["max_output_tokens"] or settings.ai_max_tokens),
        supports_deep_thinking=bool(mapped["supports_deep_thinking"] or False),
        deep_thinking_max_tokens=int(mapped["deep_thinking_max_tokens"] or 0),
        model_context_tokens=int(mapped["model_context_tokens"] or 200000),
        allowed_context_tokens=int(mapped["allowed_context_tokens"] or 120000),
        extra_context=str(mapped["extra_context"] or ""),
        enabled=True,
    )
    return await create_ai_config(payload, _, db)


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
                        msg.get("ai_config_id"),
                        bool(msg.get("use_deep_thinking", False)),
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


async def _run_agent_loop(
    loop,
    user_message: str,
    queue: asyncio.Queue,
    host_id: int | None = None,
    ai_config_id: str | None = None,
    use_deep_thinking: bool = False,
):
    """在后台运行 AI 推理循环，将事件直接放入 asyncio.Queue。"""
    session_id = loop.session_id
    logger.info(f"Starting agent loop for session {session_id}")
    try:
        async for event in loop.run(
            user_message,
            host_id=host_id,
            ai_config_id=ai_config_id,
            use_deep_thinking=use_deep_thinking,
        ):
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
    ai_config_id: str | None = None,
    use_deep_thinking: bool = False,
):
    """运行单轮推理；串行由 OpsAgentLoop 内部全局锁保证。"""
    await _run_agent_loop(
        loop,
        user_message,
        queue,
        host_id=host_id,
        ai_config_id=ai_config_id,
        use_deep_thinking=use_deep_thinking,
    )


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
