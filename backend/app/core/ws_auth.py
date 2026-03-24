"""
WebSocket 连接认证工具 (WebSocket Connection Authentication Utilities)

提供统一的 WebSocket JWT 认证逻辑，避免在多个路由中重复代码。
"""
from typing import Optional

from fastapi import WebSocket


async def validate_ws_token(websocket: WebSocket) -> Optional[dict]:
    """
    验证 WebSocket 连接的 JWT token，返回 payload 或 None。

    认证流程：优先读取 cookie 中的 access_token，兼容 query 参数 token。
    校验 JWT 有效性 + session 是否仍然活跃。
    """
    from app.core.security import decode_token
    from app.services.auth_session import validate_active_session

    token_str = websocket.cookies.get("access_token") or websocket.query_params.get("token")
    if not token_str:
        return None
    payload = decode_token(token_str)
    if payload is None or payload.get("type") != "access":
        return None
    user_id = payload.get("sub")
    token_sid = payload.get("sid")
    if user_id and token_sid:
        try:
            is_valid = await validate_active_session(int(user_id), token_sid)
            if not is_valid:
                return None
        except (ValueError, TypeError):
            return None
    return payload
