"""
用户认证路由模块 (User Authentication Router)

功能说明：提供用户注册、登录、JWT令牌管理等认证相关接口
核心职责：
  - 用户注册（首个用户自动设为管理员）
  - 用户登录验证与令牌生成
  - JWT访问令牌和刷新令牌管理
  - 获取当前用户信息
  - 速率限制防暴力破解
依赖关系：依赖 SQLAlchemy、JWT安全模块、审计服务、Redis
API端点：POST /register, POST /login, POST /refresh, GET /me

Author: NightMend Team
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.security import hash_password, verify_password, create_access_token, create_refresh_token, decode_token
from app.models.user import User
from app.schemas.auth import UserRegister, UserLogin, TokenResponse, TokenRefresh, UserResponse
from app.services.audit import log_audit
from app.services.auth_session import (
    generate_session_id,
    set_active_session,
    validate_active_session,
    clear_active_session,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# ── Cookie 配置常量 (Cookie Configuration Constants) ───────────────────────────
# P0-2 骨架：统一 cookie 参数，便于后续全量迁移时统一调整
# P0-2 Skeleton: centralized cookie params for future full migration
_COOKIE_ACCESS = "access_token"
_COOKIE_REFRESH = "refresh_token"
# 生产环境下 secure=True（仅 HTTPS），开发环境下允许 HTTP
_COOKIE_SECURE = settings.environment.lower() == "production"


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    """
    将 JWT 令牌写入 httpOnly Cookie（P0-2 骨架）。
    
    Set JWT tokens as httpOnly cookies.
    - access_token：短期（2h），路径 / 限制范围
    - refresh_token：长期（7d），路径 /api/v1/auth/refresh 限制调用
    """
    # 访问令牌 cookie：2 小时
    response.set_cookie(
        key=_COOKIE_ACCESS,
        value=access_token,
        httponly=True,
        secure=_COOKIE_SECURE,
        samesite="lax",
        max_age=settings.jwt_access_token_expire_minutes * 60,
        path="/",
    )
    # 刷新令牌 cookie：7 天，路径限制到刷新接口
    response.set_cookie(
        key=_COOKIE_REFRESH,
        value=refresh_token,
        httponly=True,
        secure=_COOKIE_SECURE,
        samesite="lax",
        max_age=settings.jwt_refresh_token_expire_days * 24 * 3600,
        path="/api/v1/auth/refresh",
    )

# ── 速率限制说明 (Rate Limiting) ──────────────────────────────
# 速率限制由 Redis 中间件 (RateLimitMiddleware) 统一处理
# 配置见 core/rate_limiting.py，auth 路由有独立的更严格规则


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(data: UserRegister, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    """
    用户注册接口 (User Registration)
    
    新用户注册功能，系统中第一个注册的用户将自动成为管理员。
    含速率限制：每 IP 每 5 分钟最多 3 次注册请求。
    P0-2 骨架：注册成功同时 set httpOnly cookie。

    Args:
        data: 用户注册数据（邮箱、姓名、密码）
        request: HTTP请求对象（用于获取客户端IP进行速率限制）
        response: HTTP响应对象（用于设置 cookie）
        db: 数据库会话依赖注入
    Returns:
        TokenResponse: 包含访问令牌和刷新令牌的响应（兼容现有前端）
    Raises:
        HTTPException 409: 邮箱已被注册
        HTTPException 429: 注册请求过于频繁
    """
    # 检查邮箱唯一性约束 (Check email uniqueness constraint)
    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    # 第一个用户自动设为管理员，后续用户默认为 operator
    # with_for_update() 防止并发注册时多个用户同时获得 admin 角色
    count_result = await db.execute(
        select(func.count()).select_from(User).with_for_update()
    )
    user_count = count_result.scalar()
    role = "admin" if user_count == 0 else "operator"

    user = User(
        email=data.email,
        name=data.name,
        hashed_password=hash_password(data.password),
        role=role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    session_id = generate_session_id()
    await set_active_session(user.id, session_id)
    access_token = create_access_token(str(user.id), session_id=session_id)
    refresh_token = create_refresh_token(str(user.id), session_id=session_id)

    # P0-2 骨架：同步设置 httpOnly cookie（与 body 响应并行，前端逐步迁移）
    _set_auth_cookies(response, access_token, refresh_token)

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/login", response_model=TokenResponse)
async def login(data: UserLogin, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    """
    用户登录接口 (User Login)
    
    验证用户凭证并生成访问令牌，同时记录审计日志。
    含速率限制：每 IP 每 5 分钟最多 5 次登录请求，防暴力破解。
    P0-2 骨架：登录成功同时 set httpOnly cookie。

    Args:
        data: 用户登录数据（邮箱、密码）
        request: HTTP请求对象（用于获取客户端IP）
        response: HTTP响应对象（用于设置 cookie）
        db: 数据库会话依赖注入
    Returns:
        TokenResponse: 包含访问令牌和刷新令牌的响应（兼容现有前端）
    Raises:
        HTTPException 401: 凭证无效（邮箱不存在或密码错误）
        HTTPException 403: 账户已禁用
        HTTPException 429: 登录请求过于频繁
    """
    # 根据邮箱查找用户 (Find user by email)
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()
    # 验证用户存在性和密码正确性 (Verify user existence and password)
    if user is None or not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    # 检查账户是否被禁用 (Check if account is disabled)
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

    # 记录登录审计日志，包含客户端IP (Log login audit with client IP)
    await log_audit(db, user.id, "login", "user", user.id,
                    None, request.client.host if request.client else None)
    await db.commit()

    session_id = generate_session_id()
    await set_active_session(user.id, session_id)
    access_token = create_access_token(str(user.id), session_id=session_id)
    refresh_token = create_refresh_token(str(user.id), session_id=session_id)

    # P0-2 骨架：同步设置 httpOnly cookie（与 body 响应并行，前端逐步迁移）
    _set_auth_cookies(response, access_token, refresh_token)

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(request: Request, response: Response, data: TokenRefresh | None = None, db: AsyncSession = Depends(get_db)):
    """
    令牌刷新接口 (Token Refresh)
    
    使用有效的刷新令牌获取新的访问令牌和刷新令牌。
    P0-2 骨架：优先从 httpOnly cookie 读取刷新令牌，兼容 body 传参。

    Args:
        request: HTTP 请求（用于读取 cookie）
        response: HTTP 响应（用于更新 cookie）
        data: 令牌刷新数据（包含刷新令牌），cookie 模式下可不传
        db: 数据库会话依赖注入
    Returns:
        TokenResponse: 包含新的访问令牌和刷新令牌
    Raises:
        HTTPException 401: 刷新令牌无效或已过期，或用户不存在
    """
    # P0-2 骨架：优先使用 cookie 中的刷新令牌，回退到 body 参数
    token_str = request.cookies.get(_COOKIE_REFRESH)
    if not token_str and data is not None:
        token_str = data.refresh_token

    if not token_str:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token missing")

    # 解析刷新令牌载荷 (Decode refresh token payload)
    payload = decode_token(token_str)
    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    # 从令牌中提取用户ID并验证用户状态 (Extract user ID and verify user status)
    user_id = payload.get("sub")
    token_sid = payload.get("sid")
    if not token_sid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired, please login again")

    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    is_valid_sid = await validate_active_session(user.id, token_sid)
    if not is_valid_sid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Your account logged in elsewhere")

    # 刷新时沿用同一个 SID，并顺延 Redis 会话 TTL
    await set_active_session(user.id, token_sid)
    access_token = create_access_token(str(user.id), session_id=token_sid)
    new_refresh_token = create_refresh_token(str(user.id), session_id=token_sid)

    # P0-2 骨架：刷新后更新 cookie
    _set_auth_cookies(response, access_token, new_refresh_token)

    return TokenResponse(access_token=access_token, refresh_token=new_refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
):
    """
    登出接口 (Logout)

    清除 httpOnly cookie 并将当前 token 加入 Redis 黑名单，使其在服务端真正失效。
    """
    await clear_active_session(current_user.id)

    from app.core.redis import blacklist_token

    # 尝试从 header 或 cookie 获取 token 并加入黑名单
    token_str = None
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token_str = auth_header[7:]
    else:
        token_str = request.cookies.get(_COOKIE_ACCESS)

    if token_str:
        payload = decode_token(token_str)
        if payload and payload.get("jti"):
            # TTL = token 剩余有效期（秒），最多不超过 access token 有效期
            import time
            exp = payload.get("exp", 0)
            ttl = max(int(exp - time.time()), 0)
            if ttl > 0:
                await blacklist_token(payload["jti"], ttl)

    # 同时也尝试黑名单 refresh token
    refresh_str = request.cookies.get(_COOKIE_REFRESH)
    if refresh_str:
        payload = decode_token(refresh_str)
        if payload and payload.get("jti"):
            import time
            exp = payload.get("exp", 0)
            ttl = max(int(exp - time.time()), 0)
            if ttl > 0:
                await blacklist_token(payload["jti"], ttl)

    response.delete_cookie(key=_COOKIE_ACCESS, path="/")
    response.delete_cookie(key=_COOKIE_REFRESH, path="/api/v1/auth/refresh")


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)):
    """
    获取当前用户信息 (Get Current User)
    
    基于JWT令牌获取当前登录用户的详细信息。
    
    Args:
        current_user: 当前用户对象（通过JWT依赖注入获得）
    Returns:
        UserResponse: 用户信息响应（ID、邮箱、姓名、角色等）
    流程：
        1. 通过JWT中间件验证访问令牌
        2. 从数据库获取用户信息
        3. 返回用户详情（不包含敏感信息）
    """
    return current_user
