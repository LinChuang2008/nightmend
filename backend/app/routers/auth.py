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

Author: VigilOps Team
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
    - access_token：短期（2h），路径 /api 限制范围
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
        path="/api",
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

    # 第一个用户自动设为管理员，后续用户默认为 operator（可访问所有功能页面，不含用户管理）
    count_result = await db.execute(select(func.count()).select_from(User))
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

    access_token = create_access_token(str(user.id))
    refresh_token = create_refresh_token(str(user.id))

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

    access_token = create_access_token(str(user.id))
    refresh_token = create_refresh_token(str(user.id))

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
    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    access_token = create_access_token(str(user.id))
    new_refresh_token = create_refresh_token(str(user.id))

    # P0-2 骨架：刷新后更新 cookie
    _set_auth_cookies(response, access_token, new_refresh_token)

    return TokenResponse(access_token=access_token, refresh_token=new_refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response):
    """
    登出接口 (Logout)
    
    清除 httpOnly cookie，使客户端 cookie 中的 JWT 失效。
    P0-2 骨架：前端调用此接口登出，同时前端负责清理 localStorage。

    Note：服务端无状态 JWT 无法真正撤销，建议后续引入 Redis 黑名单实现真正撤销。
    TODO P0-2 完整实现：在 Redis 维护 token 黑名单（jti claim）。
    """
    response.delete_cookie(key=_COOKIE_ACCESS, path="/api")
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
