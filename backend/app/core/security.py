"""
安全工具模块 (Security Tools Module)

提供 NightMend 平台的安全功能，包括密码哈希加密、JWT 令牌生成与解析等。
使用行业标准的 bcrypt 算法进行密码加密，JWT 进行用户认证和会话管理。

Provides security functions for the NightMend platform, including password hashing
and JWT token generation/parsing. Uses industry-standard bcrypt algorithm for password
encryption and JWT for user authentication and session management.
"""
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from app.core.config import settings

# 密码哈希上下文，使用 bcrypt 算法 (Password Hash Context using bcrypt algorithm)
# bcrypt 是密码学安全的慢哈希算法，能有效抵御彩虹表和暴力破解攻击
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=14)


def hash_password(password: str) -> str:
    """
    对明文密码进行哈希加密 (Hash plain text password)
    
    使用 bcrypt 算法对用户密码进行安全哈希，生成的哈希值包含盐值（salt）。
    每次哈希同一密码都会产生不同的结果，提高安全性。
    
    Uses bcrypt algorithm to securely hash user passwords, generating hash values
    that include salt. Each hash of the same password produces different results for enhanced security.
    
    Args:
        password (str): 用户输入的明文密码 (User's plain text password)
        
    Returns:
        str: bcrypt 哈希后的密码字符串 (bcrypt hashed password string)
    """
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """
    验证明文密码是否与哈希值匹配 (Verify if plain text password matches hash)
    
    使用 bcrypt 验证用户输入的明文密码是否与存储的哈希值匹配。
    验证过程会自动提取盐值并重新计算哈希进行比较。
    
    Uses bcrypt to verify if user's plain text password matches the stored hash.
    The verification process automatically extracts salt and recalculates hash for comparison.
    
    Args:
        plain (str): 用户输入的明文密码 (User's plain text password)
        hashed (str): 数据库中存储的哈希密码 (Stored hashed password from database)
        
    Returns:
        bool: 密码匹配返回 True，否则返回 False (True if password matches, False otherwise)
    """
    return pwd_context.verify(plain, hashed)


def create_access_token(subject: str, session_id: str | None = None) -> str:
    """
    生成访问令牌（短期有效） (Generate access token with short expiry)
    
    创建用于 API 访问的短期 JWT 令牌，包含用户标识和过期时间。
    访问令牌有效期较短，用于日常 API 调用的身份验证。
    
    Creates a short-term JWT token for API access, containing user identifier and expiration time.
    Access tokens have short validity periods for routine API call authentication.
    
    Args:
        subject (str): 用户标识，通常是用户 ID 或邮箱 (User identifier, usually user ID or email)
        
    Returns:
        str: JWT 访问令牌字符串 (JWT access token string)
    """
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    payload = {"sub": subject, "exp": expire, "type": "access", "jti": uuid.uuid4().hex}
    if session_id:
        payload["sid"] = session_id
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(subject: str, session_id: str | None = None) -> str:
    """
    生成刷新令牌（长期有效） (Generate refresh token with long expiry)
    
    创建用于刷新访问令牌的长期 JWT 令牌，有效期较长。
    当访问令牌过期时，可使用刷新令牌获取新的访问令牌，避免用户重复登录。
    
    Creates a long-term JWT token for refreshing access tokens.
    When access tokens expire, refresh tokens can be used to obtain new access tokens
    without requiring users to log in again.
    
    Args:
        subject (str): 用户标识，通常是用户 ID 或邮箱 (User identifier, usually user ID or email)
        
    Returns:
        str: JWT 刷新令牌字符串 (JWT refresh token string)
    """
    expire = datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_token_expire_days)
    payload = {"sub": subject, "exp": expire, "type": "refresh", "jti": uuid.uuid4().hex}
    if session_id:
        payload["sid"] = session_id
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict | None:
    """
    解析 JWT 令牌，失败返回 None (Decode JWT token, return None on failure)
    
    验证并解析 JWT 令牌，提取其中的载荷数据。
    如果令牌格式错误、签名无效或已过期，则返回 None。
    
    Validates and decodes JWT token, extracting payload data.
    Returns None if token format is invalid, signature is invalid, or token has expired.
    
    Args:
        token (str): JWT 令牌字符串 (JWT token string)
        
    Returns:
        dict | None: 解析成功返回载荷字典，失败返回 None (Payload dict on success, None on failure)
    """
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        return None
