"""
外部认证路由模块 (External Authentication Router)

功能说明：提供OAuth和LDAP等外部认证集成
核心职责：
  - OAuth 2.0 认证流程 (Google, GitHub, GitLab, Microsoft 等)
  - LDAP/Active Directory 认证
  - 外部用户信息同步
  - 认证源管理和配置
依赖关系：依赖 requests, python-ldap, authlib
API端点：GET /oauth/{provider}, POST /oauth/callback, POST /ldap/login

Author: VigilOps Team
"""
import asyncio
import logging
import secrets
from typing import Dict, Any, Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
import httpx

from app.core.database import get_db
from app.core.security import create_access_token, create_refresh_token
from app.core.config import settings
from app.models.user import User
from app.schemas.auth import TokenResponse, UserResponse
from app.services.audit import log_audit
from app.services.auth_session import generate_session_id, set_active_session

# 导入可选依赖，如未安装则禁用相应功能
try:
    import ldap3
    LDAP_AVAILABLE = True
except ImportError:
    LDAP_AVAILABLE = False

router = APIRouter(prefix="/api/v1/auth", tags=["external-auth"])
logger = logging.getLogger(__name__)

# OAuth 提供商配置
OAUTH_PROVIDERS = {
    "google": {
        "authorize_url": "https://accounts.google.com/o/oauth2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "userinfo_url": "https://www.googleapis.com/oauth2/v2/userinfo",
        "scopes": ["openid", "email", "profile"],
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
    },
    "github": {
        "authorize_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "userinfo_url": "https://api.github.com/user",
        "scopes": ["user:email"],
        "client_id": settings.github_client_id,
        "client_secret": settings.github_client_secret,
    },
    "gitlab": {
        "authorize_url": "https://gitlab.com/oauth/authorize",
        "token_url": "https://gitlab.com/oauth/token",
        "userinfo_url": "https://gitlab.com/api/v4/user",
        "scopes": ["read_user"],
        "client_id": settings.gitlab_client_id,
        "client_secret": settings.gitlab_client_secret,
    },
    "microsoft": {
        "authorize_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "userinfo_url": "https://graph.microsoft.com/v1.0/me",
        "scopes": ["openid", "profile", "email"],
        "client_id": settings.microsoft_client_id,
        "client_secret": settings.microsoft_client_secret,
    }
}

# OAuth state 使用 Redis 存储，支持多实例部署和自动过期
from app.core.redis import get_redis
_OAUTH_STATE_TTL = 600  # 10 分钟过期


async def _save_oauth_state(state: str, provider: str):
    """将 OAuth state 保存到 Redis，设置 10 分钟过期"""
    redis = await get_redis()
    await redis.setex(f"oauth_state:{state}", _OAUTH_STATE_TTL, provider)


async def _get_oauth_state(state: str) -> str | None:
    """从 Redis 获取并删除 OAuth state（一次性使用）"""
    redis = await get_redis()
    provider = await redis.get(f"oauth_state:{state}")
    if provider:
        await redis.delete(f"oauth_state:{state}")
    return provider


class LDAPLoginRequest(BaseModel):
    """LDAP 登录请求体，通过 JSON Body 传输，避免密码出现在 URL/QueryString 中"""
    email: str
    password: str


@router.get("/oauth/{provider}")
async def oauth_login(provider: str, request: Request):
    """
    OAuth 登录重定向
    
    将用户重定向到指定 OAuth 提供商的授权页面
    
    Args:
        provider: OAuth 提供商 (google, github, gitlab, microsoft)
        request: FastAPI 请求对象
        
    Returns:
        重定向响应到 OAuth 授权 URL
    """
    if provider not in OAUTH_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的OAuth提供商: {provider}"
        )
    
    provider_config = OAUTH_PROVIDERS[provider]
    
    if not provider_config["client_id"] or not provider_config["client_secret"]:
        raise HTTPException(
            status_code=501,
            detail=f"OAuth提供商 {provider} 未配置"
        )
    
    # 生成授权URL
    callback_url = str(request.url_for("oauth_callback", provider=provider))
    
    # 生成随机 state 并保存到 Redis，用于回调时的 CSRF 校验
    csrf_state = secrets.token_urlsafe(32)
    await _save_oauth_state(csrf_state, provider)

    params = {
        "client_id": provider_config["client_id"],
        "redirect_uri": callback_url,
        "scope": " ".join(provider_config["scopes"]),
        "response_type": "code",
        "state": csrf_state,
    }
    
    # Microsoft 需要特殊参数
    if provider == "microsoft":
        params["response_mode"] = "query"
    
    authorize_url = f"{provider_config['authorize_url']}?{urlencode(params)}"
    
    return {"redirect_url": authorize_url}


@router.get("/oauth/{provider}/callback")
async def oauth_callback(
    provider: str,
    code: str,
    state: str = Query(..., description="CSRF state parameter"),
    request: Request = None,
    db: AsyncSession = Depends(get_db)
):
    """
    OAuth 回调处理
    
    处理OAuth提供商的授权回调，获取用户信息并创建/登录用户
    
    Args:
        provider: OAuth 提供商
        code: 授权码
        state: CSRF防护状态
        request: FastAPI 请求对象
        db: 数据库会话
        
    Returns:
        JWT 令牌响应
    """
    if provider not in OAUTH_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"不支持的OAuth提供商: {provider}")
    
    # 验证 state 参数防 CSRF（从 Redis 获取并删除，一次性使用防重放）
    stored_provider = await _get_oauth_state(state)
    if not stored_provider or stored_provider != provider:
        raise HTTPException(status_code=400, detail="无效或已过期的状态参数")
    
    provider_config = OAUTH_PROVIDERS[provider]
    
    try:
        # 1. 用授权码换取访问令牌
        token_data = await _exchange_code_for_token(provider, code, request)
        access_token = token_data.get("access_token")
        
        if not access_token:
            raise HTTPException(status_code=400, detail="获取访问令牌失败")
        
        # 2. 获取用户信息
        user_info = await _get_oauth_user_info(provider, access_token)
        
        # 3. 查找或创建用户
        user = await _find_or_create_oauth_user(db, provider, user_info)
        
        # 4. 生成JWT令牌（与 auth.py 保持一致，sub 使用用户 ID）
        session_id = generate_session_id()
        await set_active_session(user.id, session_id)
        access_jwt = create_access_token(str(user.id), session_id=session_id)
        refresh_jwt = create_refresh_token(str(user.id), session_id=session_id)
        
        # 记录审计日志
        await log_audit(
            db, None, "user_oauth_login", 
            f"OAuth登录成功: {provider}", 
            {"provider": provider, "user_id": user.id}
        )
        
        return TokenResponse(
            access_token=access_jwt,
            refresh_token=refresh_jwt,
            token_type="bearer"
        )
        
    except Exception as e:
        logger.error(f"OAuth callback error for {provider}: {str(e)}")
        await log_audit(
            db, None, "user_oauth_login_failed",
            f"OAuth登录失败: {provider}",
            {"provider": provider, "error": str(e)}
        )
        raise HTTPException(status_code=500, detail="OAuth认证失败")


@router.post("/ldap/login")
async def ldap_login(
    credentials: LDAPLoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    LDAP 认证登录

    凭据通过 JSON Body 传输，避免密码出现在 URL Query String 中。

    Args:
        credentials: 包含 email 和 password 的请求体
        request: FastAPI 请求对象
        db: 数据库会话

    Returns:
        JWT 令牌响应
    """
    email = credentials.email
    password = credentials.password
    if not LDAP_AVAILABLE:
        raise HTTPException(
            status_code=501,
            detail="LDAP支持未安装，请安装 python-ldap"
        )
    
    if not getattr(settings, "LDAP_SERVER", None):
        raise HTTPException(
            status_code=501,
            detail="LDAP服务器未配置"
        )
    
    try:
        # 1. LDAP 认证
        user_info = await _authenticate_ldap_user(email, password)
        
        # 2. 查找或创建用户
        user = await _find_or_create_ldap_user(db, user_info)
        
        # 3. 生成JWT令牌（与 auth.py 保持一致，sub 使用用户 ID）
        session_id = generate_session_id()
        await set_active_session(user.id, session_id)
        access_token = create_access_token(str(user.id), session_id=session_id)
        refresh_token = create_refresh_token(str(user.id), session_id=session_id)
        
        # 记录审计日志
        await log_audit(
            db, None, "user_ldap_login",
            "LDAP登录成功",
            {"user_id": user.id, "ldap_dn": user_info.get("dn")}
        )
        
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer"
        )
        
    except Exception as e:
        logger.error(f"LDAP login error: {str(e)}")
        await log_audit(
            db, None, "user_ldap_login_failed",
            "LDAP登录失败",
            {"email": email, "error": str(e)}
        )
        raise HTTPException(
            status_code=401,
            detail="LDAP认证失败"
        )


async def _exchange_code_for_token(provider: str, code: str, request: Request) -> Dict[str, Any]:
    """用授权码换取访问令牌"""
    provider_config = OAUTH_PROVIDERS[provider]
    callback_url = str(request.url_for("oauth_callback", provider=provider))
    
    token_data = {
        "client_id": provider_config["client_id"],
        "client_secret": provider_config["client_secret"],
        "code": code,
        "redirect_uri": callback_url,
    }
    
    # GitHub 需要特殊处理
    if provider == "github":
        token_data["grant_type"] = "authorization_code"
        headers = {"Accept": "application/json"}
    else:
        token_data["grant_type"] = "authorization_code"
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            provider_config["token_url"],
            data=token_data,
            headers=headers
        )
        
        if response.status_code != 200:
            raise Exception(f"Token exchange failed: {response.text}")
        
        return response.json()


async def _get_oauth_user_info(provider: str, access_token: str) -> Dict[str, Any]:
    """获取OAuth用户信息"""
    provider_config = OAUTH_PROVIDERS[provider]
    
    headers = {"Authorization": f"Bearer {access_token}"}
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            provider_config["userinfo_url"],
            headers=headers
        )
        
        if response.status_code != 200:
            raise Exception(f"Failed to get user info: {response.text}")
        
        user_data = response.json()
        
        # 标准化用户信息格式
        if provider == "github":
            # GitHub 需要额外请求邮箱
            if not user_data.get("email"):
                email_response = await client.get(
                    "https://api.github.com/user/emails",
                    headers=headers
                )
                if email_response.status_code == 200:
                    emails = email_response.json()
                    primary_email = next((e["email"] for e in emails if e["primary"]), None)
                    user_data["email"] = primary_email
            
            return {
                "email": user_data.get("email"),
                "name": user_data.get("name") or user_data.get("login"),
                "avatar_url": user_data.get("avatar_url"),
                "provider_id": str(user_data.get("id")),
                "provider": provider
            }
            
        elif provider == "google":
            return {
                "email": user_data.get("email"),
                "name": user_data.get("name"),
                "avatar_url": user_data.get("picture"),
                "provider_id": user_data.get("id"),
                "provider": provider
            }
            
        elif provider == "gitlab":
            return {
                "email": user_data.get("email"),
                "name": user_data.get("name") or user_data.get("username"),
                "avatar_url": user_data.get("avatar_url"),
                "provider_id": str(user_data.get("id")),
                "provider": provider
            }
            
        elif provider == "microsoft":
            return {
                "email": user_data.get("mail") or user_data.get("userPrincipalName"),
                "name": user_data.get("displayName"),
                "avatar_url": None,  # Microsoft Graph 需要额外请求头像
                "provider_id": user_data.get("id"),
                "provider": provider
            }
        
        return user_data


async def _find_or_create_oauth_user(db: AsyncSession, provider: str, user_info: Dict[str, Any]) -> User:
    """查找或创建OAuth用户"""
    email = user_info.get("email")
    
    if not email:
        raise Exception("无法获取用户邮箱")
    
    # 查找现有用户
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    
    if user:
        # 更新用户信息
        if user_info.get("name"):
            user.name = user_info["name"]
        await db.commit()
        await db.refresh(user)
        return user
    else:
        # 创建新用户
        # 检查是否是第一个用户（自动设为管理员），使用 advisory lock 防止竞态条件
        from sqlalchemy import text
        await db.execute(text("SELECT pg_advisory_xact_lock(8007)"))  # 全局用户创建锁
        count_result = await db.execute(select(func.count(User.id)))
        user_count = count_result.scalar()

        new_user = User(
            email=email,
            name=user_info.get("name") or email.split("@")[0],
            hashed_password="!" + __import__('secrets').token_urlsafe(64),  # OAuth用户不使用本地密码，设为不可匹配值
            role="admin" if user_count == 0 else "viewer",
            is_active=True
        )

        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)
        return new_user


async def _authenticate_ldap_user(email: str, password: str) -> Dict[str, Any]:
    """LDAP用户认证"""
    if not LDAP_AVAILABLE:
        raise Exception("LDAP support not available")
    
    ldap_server = getattr(settings, "LDAP_SERVER", None)
    ldap_port = getattr(settings, "LDAP_PORT", 389)
    ldap_use_tls = getattr(settings, "LDAP_USE_TLS", False)
    ldap_base_dn = getattr(settings, "LDAP_BASE_DN", "")
    ldap_user_search = getattr(settings, "LDAP_USER_SEARCH", "uid={}")

    if not ldap_server:
        raise Exception("LDAP server not configured")

    # 防止 LDAP 注入：转义特殊字符
    safe_email = ldap3.utils.conv.escape_filter_chars(email)

    # 构建用户DN
    user_dn = f"{ldap_user_search.format(safe_email)},{ldap_base_dn}"
    
    try:
        # 连接LDAP服务器
        server = ldap3.Server(
            host=ldap_server,
            port=ldap_port,
            use_ssl=ldap_use_tls,
            get_info=ldap3.ALL
        )
        
        connection = ldap3.Connection(
            server,
            user=user_dn,
            password=password,
            auto_bind=True,
            authentication=ldap3.SIMPLE,
            check_names=True
        )
        
        # 搜索用户属性（使用已转义的 safe_email 防止 LDAP 注入）
        search_filter = f"({ldap_user_search.format(safe_email).split(',')[0]})"
        connection.search(
            search_base=ldap_base_dn,
            search_filter=search_filter,
            attributes=["cn", "displayName", "mail", "givenName", "sn"]
        )
        
        if not connection.entries:
            raise Exception("User not found in LDAP")
        
        entry = connection.entries[0]
        
        # 提取用户信息
        user_info = {
            "email": str(entry.mail) if entry.mail else email,
            "name": str(entry.displayName) if entry.displayName else str(entry.cn),
            "dn": entry.entry_dn,
            "provider": "ldap"
        }
        
        connection.unbind()
        return user_info
        
    except ldap3.core.exceptions.LDAPBindError:
        raise Exception("Invalid credentials")
    except Exception as e:
        raise Exception(f"LDAP authentication error: {str(e)}")


async def _find_or_create_ldap_user(db: AsyncSession, user_info: Dict[str, Any]) -> User:
    """查找或创建LDAP用户"""
    email = user_info.get("email")
    
    if not email:
        raise Exception("无法获取用户邮箱")
    
    # 查找现有用户
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    
    if user:
        # 更新用户信息
        if user_info.get("name"):
            user.name = user_info["name"]
        await db.commit()
        await db.refresh(user)
        return user
    else:
        # 创建新用户
        # 检查是否是第一个用户（自动设为管理员），使用 advisory lock 防止竞态条件
        from sqlalchemy import text
        await db.execute(text("SELECT pg_advisory_xact_lock(8007)"))  # 全局用户创建锁
        count_result = await db.execute(select(func.count(User.id)))
        user_count = count_result.scalar()

        new_user = User(
            email=email,
            name=user_info.get("name") or email.split("@")[0],
            hashed_password="!" + __import__('secrets').token_urlsafe(64),  # LDAP用户不使用本地密码，设为不可匹配值
            role="admin" if user_count == 0 else "viewer",
            is_active=True
        )
        
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)
        return new_user


@router.get("/providers")
async def list_auth_providers():
    """
    获取可用的认证提供商列表
    
    Returns:
        可用的认证提供商配置信息
    """
    available_providers = {}
    
    # 检查OAuth提供商配置
    for provider, config in OAUTH_PROVIDERS.items():
        if config["client_id"] and config["client_secret"]:
            available_providers[provider] = {
                "type": "oauth",
                "name": provider.title(),
                "enabled": True
            }
        else:
            available_providers[provider] = {
                "type": "oauth", 
                "name": provider.title(),
                "enabled": False,
                "reason": "未配置客户端ID和密钥"
            }
    
    # 检查LDAP配置
    ldap_configured = bool(
        LDAP_AVAILABLE and
        getattr(settings, "LDAP_SERVER", None) and
        getattr(settings, "LDAP_BASE_DN", None)
    )
    
    available_providers["ldap"] = {
        "type": "ldap",
        "name": "LDAP/Active Directory",
        "enabled": ldap_configured,
        "reason": "LDAP服务器未配置" if not ldap_configured else None
    }
    
    return {
        "providers": available_providers,
        "local_auth_enabled": True  # 本地认证始终可用
    }