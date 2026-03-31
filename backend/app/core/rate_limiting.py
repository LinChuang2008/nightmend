"""
API 限流中间件 (API Rate Limiting Middleware)

基于 Redis 实现的分布式 API 限流中间件，支持基于 IP 地址和用户的频率控制。
使用滑动窗口算法精确控制 API 调用频率，防止滥用和 DDoS 攻击。

Distributed API rate limiting middleware based on Redis, supporting frequency control
based on IP address and users. Uses sliding window algorithm for precise API call
frequency control to prevent abuse and DDoS attacks.

限流规则分级 (Rate Limit Rules Tiers):
- 严格级别：登录、密码重置等敏感接口 (Strict: login, password reset)
- 普通级别：常规业务 API (Normal: regular business API)
- 宽松级别：静态资源、健康检查 (Relaxed: static resources, health check)
"""
import hashlib
import json
import time
from typing import Dict, Optional, List, Tuple

from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.core.redis import get_redis
from app.core.security import decode_token


class RateLimitRule:
    """
    限流规则定义 (Rate Limit Rule Definition)
    
    定义单个端点或端点组的限流参数，包括时间窗口、最大请求数、
    是否区分用户等配置。支持灵活的规则组合。
    
    Defines rate limiting parameters for a single endpoint or endpoint group,
    including time window, max requests, user differentiation, etc.
    """
    
    def __init__(
        self, 
        max_requests: int, 
        window_seconds: int, 
        per_user: bool = False,
        description: str = ""
    ):
        """
        初始化限流规则 (Initialize Rate Limit Rule)
        
        Args:
            max_requests (int): 时间窗口内最大请求数 (Max requests within time window)
            window_seconds (int): 时间窗口长度（秒） (Time window length in seconds)
            per_user (bool): 是否区分用户限制 (Whether to limit per user)
            description (str): 规则描述 (Rule description)
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.per_user = per_user
        self.description = description


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    API 限流中间件 (API Rate Limiting Middleware)
    
    FastAPI 中间件，拦截所有 HTTP 请求并应用限流规则。
    支持基于路径匹配的规则配置，使用 Redis 存储限流状态。
    
    FastAPI middleware that intercepts all HTTP requests and applies rate limiting rules.
    Supports rule configuration based on path matching, uses Redis to store rate limiting state.
    """
    
    def __init__(self, app, enable_rate_limiting: bool = True):
        """
        初始化限流中间件 (Initialize Rate Limiting Middleware)
        
        Args:
            app: FastAPI 应用实例 (FastAPI application instance)
            enable_rate_limiting (bool): 是否启用限流 (Whether to enable rate limiting)
        """
        super().__init__(app)
        self.enable_rate_limiting = enable_rate_limiting
        
        # 预定义限流规则 (Predefined Rate Limit Rules)
        self.rules: Dict[str, RateLimitRule] = {
            # 严格限制：认证相关端点 (Strict: Authentication endpoints)
            "/api/v1/auth/login": RateLimitRule(5, 300, description="登录接口：5次/5分钟"),
            "/api/v1/auth/register": RateLimitRule(3, 600, description="注册接口：3次/10分钟"),
            "/api/v1/auth/refresh": RateLimitRule(10, 300, per_user=True, description="刷新Token：10次/5分钟/用户"),

            # 普通限制：业务 API (Normal: Business API)
            "/api/v1/alerts": RateLimitRule(100, 60, per_user=True, description="告警管理：100次/分钟/用户"),
            "/api/v1/hosts": RateLimitRule(200, 60, per_user=True, description="主机管理：200次/分钟/用户"),
            "/api/v1/services": RateLimitRule(200, 60, per_user=True, description="服务监控：200次/分钟/用户"),
            "/api/v1/logs": RateLimitRule(50, 60, per_user=True, description="日志查询：50次/分钟/用户"),
            "/api/v1/ai": RateLimitRule(20, 60, per_user=True, description="AI 分析：20次/分钟/用户"),

            # 严格限制：写操作和敏感操作 (Strict: Write and sensitive operations)
            "/api/v1/settings": RateLimitRule(30, 60, per_user=True, description="设置修改：30次/分钟/用户"),
            "/api/v1/users": RateLimitRule(50, 60, per_user=True, description="用户管理：50次/分钟/用户"),
            "/api/v1/remediations": RateLimitRule(20, 60, per_user=True, description="修复操作：20次/分钟/用户"),

            # Agent 数据上报：收紧限制 (Agent reporting: tightened)
            "/api/v1/agent/report": RateLimitRule(200, 60, description="Agent上报：200次/分钟"),

            # 全局默认限制 (Global default limit)
            "*": RateLimitRule(300, 60, description="默认限制：300次/分钟"),
        }
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """
        中间件主处理函数 (Main Middleware Processing Function)
        
        拦截每个 HTTP 请求，应用对应的限流规则。
        如果超出限制则返回 429 状态码，否则放行请求。
        
        Args:
            request: HTTP 请求对象 (HTTP request object)
            call_next: 下一个中间件或路由处理函数 (Next middleware or route handler)
            
        Returns:
            Response: HTTP 响应对象 (HTTP response object)
        """
        if not self.enable_rate_limiting:
            # 限流功能被禁用，直接放行 (Rate limiting disabled, pass through)
            return await call_next(request)
        
        # 跳过健康检查等特定路径 (Skip specific paths like health checks)
        if self._should_skip_rate_limiting(request):
            return await call_next(request)
        
        try:
            # 应用限流规则 (Apply rate limiting rules)
            await self._apply_rate_limit(request)
        except HTTPException as e:
            # 限流触发，返回错误响应 (Rate limit exceeded, return error response)
            headers = e.headers or {}
            # 添加基本安全头到限流错误响应 (Add basic security headers to rate limit error response)
            headers.update({
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "Cache-Control": "no-cache, no-store, must-revalidate",
            })
            
            return Response(
                content=json.dumps({
                    "error": "Rate limit exceeded",
                    "message": e.detail,
                    "retry_after": headers.get('Retry-After', '60')
                }),
                status_code=e.status_code,
                headers=headers,
                media_type="application/json"
            )
        except Exception as e:
            # 限流检查出错，记录日志但不阻断请求 (Rate limit check error, log but don't block)
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Rate limiting error: {e}")
            # 出错时放行请求，确保可用性优先 (Pass through on error, prioritize availability)
        
        return await call_next(request)
    
    def _should_skip_rate_limiting(self, request: Request) -> bool:
        """
        判断是否跳过限流检查 (Determine whether to skip rate limiting check)
        
        某些路径（如健康检查、静态资源等）可能需要跳过限流，
        以确保监控和基础功能的正常运行。
        
        Args:
            request: HTTP 请求对象 (HTTP request object)
            
        Returns:
            bool: True 表示跳过限流 (True to skip rate limiting)
        """
        path = request.url.path
        
        # 跳过的路径列表 (Paths to skip)
        skip_paths = [
            "/health",
            "/api/v1/health",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/favicon.ico",
            "/api/v1/demo/alerts/stream",
        ]
        
        return path in skip_paths or path.startswith("/static")
    
    async def _apply_rate_limit(self, request: Request) -> None:
        """
        应用限流规则检查 (Apply Rate Limiting Rule Check)
        
        根据请求路径匹配限流规则，检查是否超出频率限制。
        使用 Redis 滑动窗口算法精确计数。
        
        Args:
            request: HTTP 请求对象 (HTTP request object)
            
        Raises:
            HTTPException: 当请求频率超出限制时抛出 429 错误
        """
        path = request.url.path
        rule = self._get_matching_rule(path)
        
        if not rule:
            # 没有匹配的规则，跳过限流 (No matching rule, skip rate limiting)
            return
        
        # 构造限流键 (Build rate limit key)
        rate_limit_key = await self._build_rate_limit_key(request, rule)
        
        # 检查限流状态 (Check rate limit status)
        current_requests, ttl = await self._check_rate_limit(rate_limit_key, rule)
        
        if current_requests > rule.max_requests:
            # 超出限制，抛出异常 (Exceeded limit, raise exception)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded: {rule.description}. Current: {current_requests}/{rule.max_requests}",
                headers={"Retry-After": str(ttl)}
            )
    
    def _get_matching_rule(self, path: str) -> Optional[RateLimitRule]:
        """
        根据路径匹配限流规则 (Match Rate Limit Rule by Path)
        
        优先匹配精确路径，然后匹配前缀模式，最后使用默认规则。
        支持灵活的路径模式匹配。
        
        Args:
            path: 请求路径 (Request path)
            
        Returns:
            Optional[RateLimitRule]: 匹配的限流规则，无匹配时返回 None
        """
        # 1. 精确匹配 (Exact match)
        if path in self.rules:
            return self.rules[path]
        
        # 2. 前缀匹配 (Prefix match)
        for rule_path, rule in self.rules.items():
            if rule_path.endswith("*") and path.startswith(rule_path[:-1]):
                return rule
            elif "*" not in rule_path and path.startswith(rule_path):
                return rule
        
        # 3. 默认规则 (Default rule)
        return self.rules.get("*")
    
    async def _build_rate_limit_key(self, request: Request, rule: RateLimitRule) -> str:
        """
        构造限流缓存键 (Build Rate Limit Cache Key)
        
        根据规则配置和请求信息构造唯一的缓存键。
        支持基于 IP、用户、路径等多维度的限流粒度。
        
        Args:
            request: HTTP 请求对象 (HTTP request object)
            rule: 限流规则 (Rate limit rule)
            
        Returns:
            str: Redis 缓存键 (Redis cache key)
        """
        path = request.url.path
        
        # 获取客户端 IP (Get client IP)
        client_ip = self._get_client_ip(request)
        
        # 基础键前缀 (Base key prefix)
        key_parts = ["rate_limit", path.replace("/", "_")]
        
        if rule.per_user:
            # 基于用户限流 (Per-user rate limiting)
            user_id = await self._get_user_id_from_request(request)
            if user_id:
                key_parts.append(f"user_{user_id}")
            else:
                # 未认证用户使用 IP (Use IP for unauthenticated users)
                key_parts.append(f"ip_{client_ip}")
        else:
            # 基于 IP 限流 (Per-IP rate limiting)
            key_parts.append(f"ip_{client_ip}")
        
        return ":".join(key_parts)
    
    def _get_client_ip(self, request: Request) -> str:
        """
        获取客户端真实 IP 地址 (Get Client Real IP Address)
        
        考虑代理服务器转发头，获取客户端的真实 IP 地址。
        优先使用 X-Forwarded-For 等标准头。
        
        Args:
            request: HTTP 请求对象 (HTTP request object)
            
        Returns:
            str: 客户端 IP 地址 (Client IP address)
        """
        # 安全: 只有来自可信代理时才信任 X-Forwarded-For
        # 在 Docker 环境中，可信代理是 nginx (通常是 172.x 或 10.x 网段)
        import ipaddress
        client_ip = request.client.host if request.client else "unknown"
        _TRUSTED_PROXIES = {"127.0.0.1", "::1"}
        try:
            addr = ipaddress.ip_address(client_ip)
            is_trusted = (
                client_ip in _TRUSTED_PROXIES
                or addr.is_private
            )
        except ValueError:
            is_trusted = False

        if is_trusted:
            forwarded_for = request.headers.get("X-Forwarded-For")
            if forwarded_for:
                return forwarded_for.split(",")[0].strip()
            real_ip = request.headers.get("X-Real-IP")
            if real_ip:
                return real_ip.strip()

        return client_ip
    
    async def _get_user_id_from_request(self, request: Request) -> Optional[str]:
        """
        从请求中提取用户 ID (Extract User ID from Request)
        
        解析 Authorization 头中的 JWT token，提取用户身份信息。
        用于基于用户的限流策略。
        
        Args:
            request: HTTP 请求对象 (HTTP request object)
            
        Returns:
            Optional[str]: 用户 ID，未认证时返回 None (User ID, None if unauthenticated)
        """
        try:
            # 获取 Authorization 头 (Get Authorization header)
            auth_header = request.headers.get("Authorization")
            if not auth_header or not auth_header.startswith("Bearer "):
                return None
            
            # 提取并解析 token (Extract and decode token)
            token = auth_header.split(" ")[1]
            payload = decode_token(token)
            
            if payload and payload.get("type") == "access":
                return payload.get("sub")  # JWT subject (用户 ID)
            
        except Exception:
            # 解析失败，当作未认证处理 (Parse failed, treat as unauthenticated)
            pass
        
        return None
    
    async def _check_rate_limit(self, key: str, rule: RateLimitRule) -> Tuple[int, int]:
        """
        检查限流状态并更新计数器 (Check Rate Limit Status and Update Counter)
        
        使用 Redis 滑动窗口算法实现精确的频率限制。
        每次调用都会增加计数器，并返回当前计数和剩余过期时间。
        
        Args:
            key: Redis 缓存键 (Redis cache key)
            rule: 限流规则 (Rate limit rule)
            
        Returns:
            Tuple[int, int]: (当前请求数, TTL秒数) (Current request count, TTL seconds)
        """
        try:
            redis_client = await get_redis()
            current_time = int(time.time())
            window_start = current_time - rule.window_seconds
            
            # 使用 Redis 有序集合实现滑动窗口 (Use Redis sorted set for sliding window)
            pipe = redis_client.pipeline()
            
            # 1. 清理过期的记录 (Clean expired records)
            pipe.zremrangebyscore(key, 0, window_start)
            
            # 2. 添加当前请求记录 (Add current request record)
            pipe.zadd(key, {str(current_time): current_time})
            
            # 3. 获取窗口内的请求总数 (Get total requests in window)
            pipe.zcard(key)
            
            # 4. 设置过期时间 (Set expiration time)
            pipe.expire(key, rule.window_seconds + 60)  # 多留一分钟缓冲
            
            results = await pipe.execute()
            current_requests = results[2]  # zcard 结果
            
            # TTL 为窗口剩余时间 (TTL is remaining window time)
            ttl = rule.window_seconds
            
            return current_requests, ttl
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Redis rate limit check failed: {e}")
            # Redis 故障时允许请求通过 (Allow requests when Redis fails)
            return 0, 0


# 工厂函数：创建限流中间件实例 (Factory function: Create rate limit middleware instance)
def create_rate_limit_middleware(enable: bool = True) -> RateLimitMiddleware:
    """
    创建限流中间件实例 (Create Rate Limit Middleware Instance)
    
    工厂函数，根据配置创建限流中间件。
    支持通过环境变量控制是否启用限流功能。
    
    Args:
        enable (bool): 是否启用限流功能 (Whether to enable rate limiting)
        
    Returns:
        RateLimitMiddleware: 限流中间件实例 (Rate limit middleware instance)
    """
    import os
    
    # 从环境变量读取限流开关 (Read rate limiting switch from environment variables)
    enable_from_env = os.getenv("ENABLE_RATE_LIMITING", "true").lower() == "true"
    
    return lambda app: RateLimitMiddleware(app, enable_rate_limiting=enable and enable_from_env)