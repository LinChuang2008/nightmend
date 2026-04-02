"""
FastAPI 依赖项模块 (FastAPI Dependencies Module)

提供 NightMend 平台的通用依赖注入函数，包括用户认证、权限检查等。
基于 JWT 令牌实现用户身份验证和基于角色的访问控制（RBAC）。

Provides common dependency injection functions for the NightMend platform,
including user authentication and permission checks. Implements user authentication
and Role-Based Access Control (RBAC) based on JWT tokens.
"""
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_token
from app.core.redis import is_token_blacklisted
from app.models.user import User
from app.services.auth_session import validate_active_session

# Bearer Token 认证方案 (Bearer Token Authentication Scheme)
# auto_error=False：让我们手动处理错误，以便支持 cookie 回退
security = HTTPBearer(auto_error=False)

# P0-2 骨架：httpOnly cookie 中的访问令牌 key
_COOKIE_ACCESS = "access_token"


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    从请求中提取并验证 JWT，返回当前登录用户。

    P0-2 骨架：优先读取 Authorization Bearer header，
    回退到 httpOnly cookie（access_token），支持平滑迁移。
    
    Extract and validate JWT from request, return current user.
    P0-2 Skeleton: prefers Authorization Bearer header, falls back to httpOnly cookie.
    """
    token_str: Optional[str] = None

    # 1. 优先使用 Bearer header（现有前端兼容）
    if credentials is not None:
        token_str = credentials.credentials
    else:
        # 2. 回退：从 httpOnly cookie 读取（P0-2 新增路径）
        token_str = request.cookies.get(_COOKIE_ACCESS)

    if not token_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(token_str)
    if payload is None or payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    jti = payload.get("jti")
    if jti and await is_token_blacklisted(jti):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has been revoked")

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    token_sid = payload.get("sid")
    if not token_sid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired, please login again")

    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    is_valid_sid = await validate_active_session(user.id, token_sid)
    if not is_valid_sid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Your account logged in elsewhere")

    return user


def require_role(*roles: str):
    """
    角色检查依赖工厂 (Role check dependency factory)
    
    返回一个检查用户角色的依赖函数，用于实现基于角色的访问控制。
    只有拥有指定角色的用户才能访问受保护的端点。
    
    Returns a dependency function that checks user roles for Role-Based Access Control.
    Only users with specified roles can access protected endpoints.
    """
    async def checker(user: User = Depends(get_current_user)):
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
        return user
    return checker


# 预定义常用角色依赖 (Predefined common role dependencies)
get_admin_user = require_role("admin")  # 仅管理员 (Admin only)
require_admin = require_role("admin")  # 别名，供 log_admin 等模块使用 (Alias for log_admin etc.)
get_operator_user = require_role("admin", "operator")  # 管理员和操作员 (Admin and operator)
get_viewer_user = require_role("admin", "operator", "viewer")  # 所有角色 (All roles)
