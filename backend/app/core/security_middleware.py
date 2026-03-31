"""
安全增强中间件 (Security Enhancement Middleware)

提供 Web 应用安全防护功能，包括安全响应头设置、内容安全策略、
XSS 防护、点击劫持保护等。符合 OWASP 安全最佳实践。

Provides web application security protection features, including security response headers,
content security policy, XSS protection, clickjacking protection, etc. 
Complies with OWASP security best practices.
"""
import os
import re
from typing import Dict, List, Optional

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


class SecurityMiddleware(BaseHTTPMiddleware):
    """
    安全增强中间件 (Security Enhancement Middleware)
    
    为所有 HTTP 响应添加安全相关的响应头，提供基础的 Web 安全防护。
    包括 XSS 防护、内容类型嗅探防护、HTTPS 强制、点击劫持防护等。
    
    Adds security-related response headers to all HTTP responses, providing basic web security protection.
    Includes XSS protection, content type sniffing protection, HTTPS enforcement, clickjacking protection, etc.
    """
    
    def __init__(self, app, enable_security_headers: bool = True):
        """
        初始化安全中间件 (Initialize Security Middleware)
        
        Args:
            app: FastAPI 应用实例 (FastAPI application instance)
            enable_security_headers (bool): 是否启用安全头 (Whether to enable security headers)
        """
        super().__init__(app)
        self.enable_security_headers = enable_security_headers
        
        # 从环境变量读取配置 (Read configuration from environment variables)
        self.is_production = os.getenv("ENVIRONMENT", "development").lower() == "production"
        self.frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3001")
        self.api_domain = os.getenv("API_DOMAIN", "localhost:8001")
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """
        中间件主处理函数 (Main Middleware Processing Function)
        
        处理请求并在响应中添加安全头。
        同时进行一些基础的安全检查和输入验证。
        
        Args:
            request: HTTP 请求对象 (HTTP request object)
            call_next: 下一个中间件或路由处理函数 (Next middleware or route handler)
            
        Returns:
            Response: 增强了安全头的 HTTP 响应 (HTTP response with enhanced security headers)
        """
        # SSE 流端点直接放行，避免 BaseHTTPMiddleware 缓冲响应体
        if request.url.path == "/api/v1/demo/alerts/stream":
            return await call_next(request)

        # 请求前安全检查 (Pre-request security checks)
        if not self._is_request_safe(request):
            return Response(
                content="Bad Request",
                status_code=400,
                headers={"Content-Type": "text/plain"}
            )

        # 处理请求 (Process request)
        response = await call_next(request)

        # 添加安全头 (Add security headers)
        if self.enable_security_headers:
            self._add_security_headers(response, request)

        return response
    
    def _is_request_safe(self, request: Request) -> bool:
        """
        基础请求安全检查 (Basic Request Security Check)
        
        检查请求是否包含明显的恶意特征，如过长的 URL、
        可疑的 User-Agent 等。
        
        Args:
            request: HTTP 请求对象 (HTTP request object)
            
        Returns:
            bool: True 表示请求安全 (True if request is safe)
        """
        # 检查 URL 长度 (Check URL length)
        if len(str(request.url)) > 2048:
            return False
        
        # 检查请求体大小 (Check request body size)
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                size = int(content_length)
                # 限制请求体最大 50MB (Limit request body to max 50MB)
                max_size = int(os.getenv("MAX_REQUEST_SIZE", "52428800"))  # 50MB
                if size > max_size:
                    return False
            except ValueError:
                return False
        
        # 检查可疑的 User-Agent (Check suspicious User-Agent)
        user_agent = request.headers.get("user-agent", "").lower()
        suspicious_agents = [
            "sqlmap", "nikto", "nmap", "masscan", "nessus",
            "burpsuite", "owasp zap", "w3af", "skipfish"
        ]
        if any(agent in user_agent for agent in suspicious_agents):
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Suspicious user agent detected: {user_agent} from {request.client.host}")
            # 记录但不阻止，避免误杀 (Log but don't block to avoid false positives)
        
        return True
    
    def _add_security_headers(self, response: Response, request: Request) -> None:
        """
        添加安全响应头 (Add Security Response Headers)
        
        为响应添加各种安全相关的 HTTP 头，提供多层次的安全防护。
        根据生产环境和开发环境使用不同的安全策略。
        
        Args:
            response: HTTP 响应对象 (HTTP response object)
            request: HTTP 请求对象 (HTTP request object)
        """
        headers = self._build_security_headers(request)
        
        for name, value in headers.items():
            response.headers[name] = value
    
    def _build_security_headers(self, request: Request) -> Dict[str, str]:
        """
        构建安全响应头字典 (Build Security Response Headers Dictionary)
        
        根据当前环境和请求类型构建适当的安全头。
        生产环境使用更严格的安全策略。
        
        Args:
            request: HTTP 请求对象 (HTTP request object)
            
        Returns:
            Dict[str, str]: 安全响应头字典 (Security response headers dictionary)
        """
        headers = {}
        
        # 1. X-Content-Type-Options: 防止 MIME 类型嗅探 (Prevent MIME type sniffing)
        headers["X-Content-Type-Options"] = "nosniff"
        
        # 2. X-Frame-Options: 防止点击劫持 (Prevent clickjacking)
        headers["X-Frame-Options"] = "DENY"
        
        # 3. X-XSS-Protection: XSS 防护 (XSS protection)
        headers["X-XSS-Protection"] = "1; mode=block"
        
        # 4. Referrer-Policy: 控制引用信息泄露 (Control referrer information leakage)
        headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # 5. HSTS: 强制 HTTPS（仅生产环境） (Force HTTPS in production only)
        if self.is_production:
            headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
        
        # 6. Content Security Policy: 内容安全策略 (Content Security Policy)
        csp = self._build_content_security_policy(request)
        if csp:
            headers["Content-Security-Policy"] = csp
        
        # 7. Permissions Policy: 权限策略 (Permissions Policy)
        headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=(), "
            "payment=(), usb=(), magnetometer=(), gyroscope=()"
        )
        
        # 8. X-Permitted-Cross-Domain-Policies: 阻止跨域策略文件 (Block cross-domain policy files)
        headers["X-Permitted-Cross-Domain-Policies"] = "none"
        
        # 9. Cache-Control: 敏感页面缓存控制 (Cache control for sensitive pages)
        if self._is_sensitive_path(request.url.path):
            headers["Cache-Control"] = "no-cache, no-store, must-revalidate, private"
            headers["Pragma"] = "no-cache"
            headers["Expires"] = "0"
        
        return headers
    
    def _build_content_security_policy(self, request: Request) -> Optional[str]:
        """
        构建内容安全策略 (Build Content Security Policy)
        
        根据应用需求和环境构建 CSP 策略。
        开发环境相对宽松，生产环境更严格。
        
        Args:
            request: HTTP 请求对象 (HTTP request object)
            
        Returns:
            Optional[str]: CSP 策略字符串 (CSP policy string)
        """
        # API 端点通常不需要复杂的 CSP (API endpoints usually don't need complex CSP)
        if request.url.path.startswith("/api/"):
            return "default-src 'none'; frame-ancestors 'none';"
        
        # 基础 CSP 策略 (Basic CSP policy)
        csp_directives = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline'",  # 开发需要，生产环境应移除 unsafe-inline
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data: https:",
            "font-src 'self' https:",
            "connect-src 'self'",
            "frame-src 'none'",
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "form-action 'self'",
        ]
        
        # 开发环境允许本地资源 (Allow local resources in development)
        if not self.is_production:
            csp_directives.extend([
                "connect-src 'self' ws: wss: http://localhost:* https://localhost:*",
                "script-src 'self' 'unsafe-inline' 'unsafe-eval'",  # 开发工具需要
            ])
        
        return "; ".join(csp_directives) + ";"
    
    def _is_sensitive_path(self, path: str) -> bool:
        """
        判断是否为敏感路径 (Determine if Path is Sensitive)
        
        敏感路径需要额外的缓存控制，防止敏感信息被缓存。
        
        Args:
            path: 请求路径 (Request path)
            
        Returns:
            bool: True 表示敏感路径 (True if path is sensitive)
        """
        sensitive_patterns = [
            r"/api/v1/auth/.*",
            r"/api/v1/users/.*",
            r"/api/v1/settings/.*",
            r"/api/v1/audit.*",
        ]
        
        return any(re.match(pattern, path) for pattern in sensitive_patterns)


class RequestSizeMiddleware(BaseHTTPMiddleware):
    """
    请求大小限制中间件 (Request Size Limiting Middleware)
    
    限制 HTTP 请求的最大大小，防止大文件攻击和资源耗尽。
    可以为不同的端点设置不同的大小限制。
    
    Limits the maximum size of HTTP requests to prevent large file attacks and resource exhaustion.
    Different size limits can be set for different endpoints.
    """
    
    def __init__(self, app, max_size: int = 10 * 1024 * 1024):  # 默认 10MB
        """
        初始化请求大小限制中间件 (Initialize Request Size Limiting Middleware)
        
        Args:
            app: FastAPI 应用实例 (FastAPI application instance)
            max_size (int): 最大请求大小（字节） (Maximum request size in bytes)
        """
        super().__init__(app)
        self.max_size = max_size
        
        # 特殊路径的大小限制 (Size limits for special paths)
        self.path_limits = {
            "/api/v1/logs/upload": 50 * 1024 * 1024,  # 日志上传 50MB
            "/api/v1/agent/report": 1 * 1024 * 1024,  # Agent 报告 1MB
        }
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """
        检查请求大小并处理 (Check Request Size and Process)
        """
        # SSE 流端点直接放行
        if request.url.path == "/api/v1/demo/alerts/stream":
            return await call_next(request)

        content_length = request.headers.get("content-length")
        
        if content_length:
            try:
                size = int(content_length)
                max_allowed = self._get_max_size_for_path(request.url.path)
                
                if size > max_allowed:
                    return Response(
                        content=f"Request entity too large. Max allowed: {max_allowed} bytes",
                        status_code=413,
                        headers={"Content-Type": "text/plain"}
                    )
            except ValueError:
                # Content-Length 不是有效数字 (Content-Length is not a valid number)
                return Response(
                    content="Invalid Content-Length header",
                    status_code=400,
                    headers={"Content-Type": "text/plain"}
                )
        
        return await call_next(request)
    
    def _get_max_size_for_path(self, path: str) -> int:
        """
        获取路径对应的最大大小限制 (Get Maximum Size Limit for Path)
        
        Args:
            path: 请求路径 (Request path)
            
        Returns:
            int: 最大允许大小（字节） (Maximum allowed size in bytes)
        """
        for pattern, limit in self.path_limits.items():
            if path.startswith(pattern) or re.match(pattern, path):
                return limit
        
        return self.max_size


# 工厂函数 (Factory Functions)
def create_security_middleware(enable: bool = True) -> SecurityMiddleware:
    """
    创建安全中间件实例 (Create Security Middleware Instance)
    
    Args:
        enable (bool): 是否启用安全增强 (Whether to enable security enhancements)
        
    Returns:
        SecurityMiddleware: 安全中间件实例 (Security middleware instance)
    """
    enable_from_env = os.getenv("ENABLE_SECURITY_HEADERS", "true").lower() == "true"
    return lambda app: SecurityMiddleware(app, enable_security_headers=enable and enable_from_env)


def create_request_size_middleware(max_size: Optional[int] = None) -> RequestSizeMiddleware:
    """
    创建请求大小限制中间件实例 (Create Request Size Limiting Middleware Instance)
    
    Args:
        max_size (Optional[int]): 最大请求大小，None 使用环境变量 (Max request size, None to use env var)
        
    Returns:
        RequestSizeMiddleware: 请求大小限制中间件实例 (Request size limiting middleware instance)
    """
    if max_size is None:
        max_size = int(os.getenv("MAX_REQUEST_SIZE", str(10 * 1024 * 1024)))  # 默认 10MB
    
    return lambda app: RequestSizeMiddleware(app, max_size=max_size)