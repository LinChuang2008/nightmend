"""
NightMend 后端应用入口模块 (NightMend Backend Application Entry Module)

NightMend 运维监控平台的主应用入口，负责 FastAPI 应用的完整生命周期管理。
包含应用初始化、中间件配置、路由注册、后台任务启动等核心功能。

Main application entry point for the NightMend operations monitoring platform,
responsible for complete FastAPI application lifecycle management.
Includes application initialization, middleware configuration, route registration, and background task startup.

主要功能 (Main Features):
- 数据库表自动创建和初始化 (Automatic database table creation and initialization)
- 内置告警规则种子数据 (Built-in alert rule seed data)
- 后台任务管理：离线检测、告警引擎、日志清理等 (Background task management)
- AI 异常检测和自动修复 (AI anomaly detection and auto-remediation)
- WebSocket 实时数据推送 (Real-time data push via WebSocket)
- 健康检查和监控 (Health checks and monitoring)
"""
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

# 配置应用级别日志 (Configure application-level logging)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import settings as app_settings
from app.core.exceptions import register_exception_handlers
from app.core.database import engine, Base
from app.core.redis import get_redis, close_redis
# 导入 models 包，确保最新模型全部注册到 Base.metadata。
# 新部署环境将由 create_all 直接按”当前最新模型”建表；
# 已部署旧版本环境仍建议通过 Alembic 做增量迁移。
import app.models  # noqa: F401
from app.models.alert_group import AlertGroup, AlertDeduplication  # noqa: F401
from app.models.custom_runbook import CustomRunbook  # noqa: F401
# 导入所有路由模块 (Import all router modules)
from app.routers import auth
from app.routers import agent_tokens
from app.routers import agent
from app.routers import agent_updates
from app.routers import hosts
from app.routers import services
from app.routers import alert_rules
from app.routers import alerts
from app.routers import notifications
from app.routers import settings
from app.routers import logs
from app.routers import log_admin
from app.routers import databases
from app.routers import users
from app.routers import audit_logs
from app.routers import reports
from app.routers import notification_templates
from app.routers import dashboard_ws
from app.routers import dashboard
from app.routers import topology
from app.routers import sla
from app.routers import remediation
from app.routers import servers
from app.routers import server_groups
from app.routers import on_call
from app.routers import alert_escalation
from app.routers import dashboard_config
from app.routers import prometheus
from app.routers import external_auth
from app.routers import ai_feedback
from app.routers import suppression_rules
from app.routers import ops
from app.routers import menu_settings
from app.routers import ai_operation_logs
from app.routers import ai_analysis
from app.routers import custom_runbooks
from app.routers import promql
from app.routers import webhooks
from app.routers import alert_stream
from app.api.v1 import data_retention
from app.api.v1 import alert_deduplication


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理器 (Application Lifecycle Manager)

    管理 NightMend 应用的完整生命周期，包括启动时的初始化和关闭时的清理。
    负责数据库表创建、内置数据初始化、后台任务启动和资源释放。

    Manages the complete lifecycle of the NightMend application, including initialization
    at startup and cleanup at shutdown. Responsible for database table creation,
    built-in data initialization, background task startup, and resource cleanup.
    """
    import asyncio
    import os
    from app.tasks.offline_detector import offline_detector_loop
    from app.tasks.alert_engine import alert_engine_loop
    from app.tasks.log_cleanup import log_cleanup_loop
    from app.tasks.db_metric_cleanup import db_metric_cleanup_loop
    from app.tasks.data_retention_task import data_retention_task
    from app.tasks.alert_deduplication_cleanup import alert_deduplication_cleanup_loop
    from app.services.alert_seed import seed_builtin_rules
    from app.core.database import async_session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        await seed_builtin_rules(session)

    # 初始化统一工具注册表 (Initialize Unified Tool Registry)
    from app.tools import init_tool_registry
    registry = init_tool_registry()
    logger_init = logging.getLogger("nightmend.tools")
    logger_init.info("Tool registry initialized: %d tools registered", registry.tool_count)

    from app.services.data_retention import DataRetentionService
    from app.core.database import SessionLocal
    try:
        sync_db = SessionLocal()
        try:
            retention_service = DataRetentionService(sync_db)
            for data_type, default_days in {
                "host_metrics": 30,
                "db_metrics": 30,
                "log_entries": 7,
                "ai_insights": 90,
                "audit_logs": 365
            }.items():
                if retention_service.get_retention_days(data_type) == default_days:
                    from app.models.setting import Setting
                    existing = sync_db.query(Setting).filter(Setting.key == f"retention_days_{data_type}").first()
                    if not existing:
                        retention_service.set_retention_days(data_type, default_days)
            sync_db.commit()
        finally:
            sync_db.close()
    except Exception as e:
        _init_logger = logging.getLogger(__name__)
        _init_logger.warning(f"Failed to initialize data retention settings: {e}")

    # 启动后台定时任务 (Start background scheduled tasks)
    logger = logging.getLogger("nightmend.tasks")

    retention_days = int(os.environ.get("LOG_RETENTION_DAYS", "7"))
    db_retention = int(os.environ.get("DB_METRIC_RETENTION_DAYS", "30"))

    from app.services.anomaly_scanner import anomaly_scanner_loop
    from app.tasks.report_scheduler import report_scheduler_loop

    # 注册所有后台任务及其工厂函数 (Register all background tasks with factory functions)
    background_tasks: dict[str, asyncio.Task] = {}
    task_factories: dict[str, callable] = {
        "offline_detector": lambda: offline_detector_loop(),
        "alert_engine": lambda: alert_engine_loop(),
        "log_cleanup": lambda: log_cleanup_loop(retention_days),
        "db_metric_cleanup": lambda: db_metric_cleanup_loop(db_retention),
        "data_retention": lambda: data_retention_task(),
        "alert_dedup_cleanup": lambda: alert_deduplication_cleanup_loop(),
        "anomaly_scanner": lambda: anomaly_scanner_loop(),
        "report_scheduler": lambda: report_scheduler_loop(),
    }

    # 自动修复监听任务（仅在配置启用时）
    if app_settings.agent_enabled:
        from app.tasks.remediation_listener import remediation_listener_loop
        task_factories["remediation_listener"] = lambda: remediation_listener_loop()

    # 启动所有任务
    for name, factory in task_factories.items():
        background_tasks[name] = asyncio.create_task(factory(), name=name)

    # 后台任务监控：检测崩溃并自动重启 (Background task monitor: detect crashes and auto-restart)
    async def _monitor_tasks():
        while True:
            await asyncio.sleep(30)
            for name, task in list(background_tasks.items()):
                if task.done():
                    exc = task.exception() if not task.cancelled() else None
                    if exc:
                        logger.error("后台任务 [%s] 崩溃: %s，30s 后自动重启", name, exc)
                    else:
                        logger.warning("后台任务 [%s] 意外退出，30s 后自动重启", name)
                    # 使用工厂函数重启任务
                    if name in task_factories:
                        background_tasks[name] = asyncio.create_task(
                            task_factories[name](), name=name
                        )
                        logger.info("后台任务 [%s] 已重启", name)

    monitor_task = asyncio.create_task(_monitor_tasks(), name="task_monitor")

    yield

    # 关闭阶段：清理资源和取消任务 (Shutdown Phase: Cleanup resources and cancel tasks)
    monitor_task.cancel()
    for name, task in background_tasks.items():
        task.cancel()

    await close_redis()
    await engine.dispose()


# 创建 FastAPI 应用实例 (Create FastAPI application instance)
app = FastAPI(
    title="NightMend",
    description="AI-powered infrastructure monitoring platform | AI 驱动的基础设施监控平台",
    version="2026.03.14-beta.1",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# 注册全局异常处理器 (Register global exception handlers)
register_exception_handlers(app)

# 导入安全和限流中间件 (Import security and rate limiting middleware)
from app.core.rate_limiting import RateLimitMiddleware
from app.core.security_middleware import SecurityMiddleware, RequestSizeMiddleware

# 配置安全中间件 (Configure security middleware)
# 注意：中间件的注册顺序很重要，安全检查应该在业务逻辑之前
# Note: Middleware registration order is important, security checks should be before business logic

# 1. 请求大小限制中间件 (Request size limiting middleware)
app.add_middleware(RequestSizeMiddleware)

# 2. 安全头中间件 (Security headers middleware)  
app.add_middleware(SecurityMiddleware)

# 3. API 限流中间件 (API rate limiting middleware)
app.add_middleware(RateLimitMiddleware)

# 4. 配置 CORS 中间件，允许前端跨域访问 (Configure CORS middleware for frontend cross-origin access)
# 生产环境下的 CORS 配置更加严格 (Stricter CORS configuration in production)
import os
# ⚠️ 安全原则：默认最严格，必须显式设置 ENVIRONMENT=development 才开放 CORS
# 未设置 ENVIRONMENT 时视为 production，绝不默认全开
_env = os.getenv("ENVIRONMENT", "production").lower()
is_development = _env == "development"
if is_development:
    allowed_origins = [
        "http://localhost:3000", "http://localhost:3001",
        "http://127.0.0.1:3000", "http://127.0.0.1:3001",
    ]
else:
    _frontend_url = os.getenv("FRONTEND_URL", "").strip()
    allowed_origins = [
        "https://demo.lchuangnet.com",
        "https://lchuangnet.com",
        "https://www.lchuangnet.com",
        "http://139.196.210.68:3001",
    ]
    if _frontend_url and _frontend_url not in allowed_origins:
        allowed_origins.append(_frontend_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,  # 生产环境限制具体域名 (Restrict specific domains in production)
    allow_credentials=True,  # 允许携带认证信息 (Allow credentials)
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],  # 明确允许的方法 (Explicitly allowed methods)
    allow_headers=["Content-Type", "Authorization", "X-Requested-With", "Accept", "Origin"],  # 明确允许的请求头 (Explicitly allowed headers)
    expose_headers=["X-Total-Count", "X-Rate-Limit-*"],  # 暴露的响应头 (Exposed response headers)
)

# 注册所有 API 路由模块 (Register all API router modules)
app.include_router(auth.router)  # 用户认证 (User authentication)
app.include_router(agent_tokens.router)  # Agent 令牌管理 (Agent token management)
app.include_router(agent.router)  # Agent 数据上报 (Agent data reporting)
app.include_router(agent_updates.router)  # Agent 更新管理 (Agent update management)
app.include_router(hosts.router)  # 主机管理 (Host management)
app.include_router(services.router)  # 服务监控 (Service monitoring)
app.include_router(alert_rules.router)  # 告警规则 (Alert rules)
app.include_router(alerts.router)  # 告警管理 (Alert management)
app.include_router(notifications.router)  # 通知管理 (Notification management)
app.include_router(settings.router)  # 系统设置 (System settings)
app.include_router(logs.router)  # 日志管理 (Log management)
app.include_router(logs.ws_router)  # WebSocket 日志流 (WebSocket log streaming)
app.include_router(log_admin.router)  # 日志后端管理 (Log backend administration)
app.include_router(databases.router)  # 数据库监控 (Database monitoring)
app.include_router(ai_feedback.router)  # AI 反馈 (AI feedback)
app.include_router(users.router)  # 用户管理 (User management)
app.include_router(audit_logs.router)  # 审计日志 (Audit logs)
app.include_router(reports.router)  # 运维报告 (Operations reports)
app.include_router(notification_templates.router)  # 通知模板 (Notification templates)
app.include_router(dashboard_ws.router)  # 仪表盘 WebSocket (Dashboard WebSocket)
app.include_router(dashboard.router)  # 仪表盘数据 (Dashboard data)
app.include_router(topology.router)  # 服务拓扑 (Service topology)
app.include_router(sla.router)  # SLA 管理 (SLA management)
app.include_router(remediation.router)  # 自动修复 (Auto-remediation)
app.include_router(remediation.trigger_router)  # 修复触发器 (Remediation triggers)
app.include_router(servers.router)  # 服务器管理 (Server management)
app.include_router(server_groups.router)  # 服务器分组 (Server grouping)
app.include_router(on_call.router)  # 值班排期管理 (On-call schedule management)
app.include_router(alert_escalation.router)  # 告警升级管理 (Alert escalation management)
app.include_router(dashboard_config.router)  # 仪表盘配置管理 (Dashboard configuration management)
app.include_router(data_retention.router, prefix="/api/v1/data-retention", tags=["数据保留策略"])  # 数据保留策略 (Data retention policy)
app.include_router(alert_deduplication.router, prefix="/api/v1/alert-deduplication", tags=["告警去重"])  # 告警去重和聚合 (Alert deduplication and aggregation)
app.include_router(prometheus.router)  # Prometheus 兼容性 (Prometheus compatibility)
app.include_router(external_auth.router)  # 外部认证 (External Authentication)
app.include_router(suppression_rules.router)  # 屏蔽规则管理 (Suppression rules management)
app.include_router(ops.router)  # AI 运维助手 (AI Ops Assistant)
app.include_router(menu_settings.router)  # 菜单可见性配置 (Menu visibility settings)
app.include_router(ai_operation_logs.router)  # AI 操作日志 (AI operation logs)
app.include_router(ai_analysis.router)  # AI 分析 (AI analysis: insights, root-cause, logs)
app.include_router(custom_runbooks.router)  # 自定义 Runbook 管理 (Custom Runbook Management)
app.include_router(promql.router)  # PromQL 查询 (PromQL Query Engine)
app.include_router(webhooks.router)  # 外部告警源 Webhook (External Alert Source Webhooks)
app.include_router(alert_stream.router)  # 告警诊断 SSE 流 (Alert Diagnosis SSE Stream)


@app.get("/health")
@app.get("/api/v1/health")
async def health():
    """
    健康检查接口 (Health Check Endpoint)
    
    验证 NightMend 平台各个核心组件的连通性和状态，包括 API、数据库、Redis 缓存等。
    用于负载均衡器健康检查、监控系统状态检测和运维故障排查。
    
    Verifies connectivity and status of core NightMend platform components,
    including API, database, Redis cache, etc. Used for load balancer health checks,
    monitoring system status detection, and operational troubleshooting.
    
    Returns:
        dict: 包含各组件状态和时间戳的健康检查结果 (Health check results with component status and timestamp)
    """
    checks = {"api": "ok"}

    # 数据库连通性检查 (Database connectivity check)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "error"

    # Redis 连通性检查 (Redis connectivity check)
    try:
        r = await get_redis()
        await r.ping()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "error"

    # 综合状态评估 (Overall status assessment)
    # 所有组件正常则返回 ok，否则返回 degraded (Return 'ok' if all components are healthy, otherwise 'degraded')
    status = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    
    return {
        "status": status,
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
