"""
认证会话服务

用于实现单用户单活跃登录：
- 登录时写入新的会话 SID
- 鉴权时校验 token SID 与 Redis 中当前 SID 一致
"""
from __future__ import annotations

import secrets

from app.core.config import settings
from app.core.redis import get_redis


def generate_session_id() -> str:
    """生成新的登录会话 SID。"""
    return secrets.token_urlsafe(24)


def _session_key(user_id: int | str) -> str:
    return f"auth:active_session:{user_id}"


def _session_ttl_seconds() -> int:
    # 与 refresh token 生命周期对齐，避免会话键比 token 更早失效
    return max(3600, settings.jwt_refresh_token_expire_days * 24 * 3600)


async def set_active_session(user_id: int, session_id: str) -> None:
    """设置用户当前活跃 SID，新登录会覆盖旧 SID。"""
    redis = await get_redis()
    await redis.set(_session_key(user_id), session_id, ex=_session_ttl_seconds())


async def get_active_session(user_id: int) -> str | None:
    """读取用户当前活跃 SID。"""
    redis = await get_redis()
    return await redis.get(_session_key(user_id))


async def clear_active_session(user_id: int) -> None:
    """清理用户活跃 SID（登出时使用）。"""
    redis = await get_redis()
    await redis.delete(_session_key(user_id))


async def validate_active_session(user_id: int, token_sid: str | None) -> bool:
    """
    校验 token SID 是否为该用户的当前活跃 SID。
    """
    if not token_sid:
        return False
    current_sid = await get_active_session(user_id)
    return bool(current_sid and current_sid == token_sid)
