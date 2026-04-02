"""
NightMend MCP Server (Model Context Protocol Server)

Exposes NightMend core operational tools to AI agents through the MCP protocol.
First open-source monitoring platform with native MCP support + AI analysis.

Features:
- Server health monitoring and metrics
- Alert management and incident analysis
- Log search with time range filtering
- AI-powered root cause analysis
- Service topology visualization
- Real-time operational insights

Competitive advantage: Native AI integration with monitoring data.
"""
import asyncio
import json
import logging
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any, Union

from fastmcp import FastMCP
from pydantic import BaseModel
from sqlalchemy.orm import joinedload

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.database import async_session as AsyncSessionLocal
from app.core.redis import get_redis
from app.models.host import Host
from app.models.alert import Alert, AlertRule
from app.models.log_entry import LogEntry
from app.models.service import Service
from app.models.service_dependency import ServiceDependency
from app.models.host_metric import HostMetric
from app.models.user import User
from app.models.ops_session import OpsSession
from app.services.ops_agent_loop import get_or_create_loop, remove_loop
from app.tools import tool_registry
from app.tools.base import ToolEventType
from app.tools.context import ToolContext
from app.tools.safety import SafetyChecker

logger = logging.getLogger(__name__)

# Initialize FastMCP server
mcp_server = FastMCP("NightMend")


@contextmanager
def _get_db():
    """获取数据库 session，自动关闭防止连接泄漏。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _run_async_sync(coro):
    """在同步上下文安全执行协程。"""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result_box: dict[str, Any] = {}
    error_box: dict[str, Exception] = {}

    def _runner():
        try:
            result_box["value"] = asyncio.run(coro)
        except Exception as e:
            error_box["error"] = e

    t = threading.Thread(target=_runner, daemon=True)
    t.start()
    t.join()
    if "error" in error_box:
        raise error_box["error"]
    return result_box.get("value")


async def _run_ops_loop_for_mcp(session_id: str, user_id: int, prompt: str) -> dict:
    """
    使用 OpsAgentLoop 执行 MCP 事件分析。
    MCP 场景下自动拒绝 execute_command，自动回答 ask_user，避免阻塞。
    """
    loop = get_or_create_loop(session_id, user_id)
    text_parts: list[str] = []
    tool_trace: list[str] = []
    error_msg: Optional[str] = None
    try:
        async for event in loop.run(prompt):
            event_type = event.get("event")
            if event_type == "text_delta":
                text_parts.append(event.get("delta", ""))
            elif event_type == "tool_start":
                tool_trace.append(f"tool_start:{event.get('tool_name', '')}")
            elif event_type == "tool_done":
                tool_trace.append(f"tool_done:{event.get('tool_name', '')}")
            elif event_type == "command_request":
                message_id = event.get("message_id", "")
                if message_id:
                    await loop.handle_command_confirm(message_id, "reject")
                tool_trace.append("command_request:auto_reject")
            elif event_type == "ask_user":
                message_id = event.get("message_id", "")
                if message_id:
                    await loop.handle_ask_user_answer(message_id, "")
                tool_trace.append("ask_user:auto_answer")
            elif event_type == "error":
                error_msg = event.get("message", "unknown error")
                break
            elif event_type == "done":
                break
    finally:
        remove_loop(session_id)

    return {
        "analysis_text": "".join(text_parts).strip(),
        "tool_trace": tool_trace,
        "error": error_msg,
    }


def _host_to_dict(host: Host) -> dict:
    """将 Host 对象转为字典，避免重复代码。"""
    return {
        "id": host.id,
        "hostname": host.hostname,
        "display_name": host.display_name,
        "display_hostname": host.display_hostname,
        "ip": host.display_ip,
        "status": host.status,
    }


# ─── Auto-registration from unified ToolRegistry ────────────────────────────
# Tools defined in app/tools/builtins/ and app/tools/runbooks/ are auto-registered
# here so MCP clients get the same capabilities as the Ops Assistant.


def register_tools_from_registry(server: FastMCP) -> int:
    """Auto-register all tools from the unified ToolRegistry as MCP tools.

    Returns the number of tools successfully registered.
    Handles the case where the registry has 0 tools (e.g. startup timing).
    """
    tools = tool_registry.list_tools()
    if not tools:
        logger.warning(
            "ToolRegistry has 0 tools — registry may not be initialized yet. "
            "Call init_tool_registry() before register_tools_from_registry()."
        )
        return 0

    count = 0
    for tool in tools:
        try:
            _register_mcp_tool(server, tool)
            logger.info("MCP: registered tool '%s' from ToolRegistry", tool.name)
            count += 1
        except Exception:
            logger.warning(
                "MCP: failed to register tool '%s', skipping",
                tool.name,
                exc_info=True,
            )
    logger.info("MCP: %d/%d registry tools registered", count, len(tools))
    return count


def _register_mcp_tool(server: FastMCP, tool) -> None:
    """Register a single OpsTool as an MCP tool using the closure pattern.

    The handler runs the async tool.execute() via _run_async_sync() because
    MCP tool handlers may be invoked in a sync context.
    """

    # Use a default-arg closure to capture the current `tool` value
    async def _async_handler(tool=tool, **kwargs):
        """Async inner handler — executes the OpsTool and collects RESULT events."""
        # MCP mode: tools requiring approval are auto-rejected (safety first)
        if tool.requires_approval:
            return {
                "error": (
                    f"Tool '{tool.name}' requires user confirmation and is not "
                    "available in MCP mode."
                )
            }

        redis = await get_redis()
        ctx = ToolContext(
            session_id=f"mcp-{uuid.uuid4()}",
            user_id=0,  # MCP has no interactive user; tools use service context
            db_session_factory=AsyncSessionLocal,
            redis=redis,
            safety_checker=SafetyChecker(redis=redis),
            caller="mcp",
        )

        results: list[dict] = []
        try:
            async for event in tool.execute(kwargs, ctx):
                if event.type == ToolEventType.RESULT:
                    results.append(event.data)
        except Exception as exc:
            logger.error("MCP tool '%s' execution error: %s", tool.name, exc)
            return {"error": str(exc)}

        return results[-1] if results else {}

    def handler(tool=tool, **kwargs):
        """Sync wrapper — bridges MCP's sync call convention to our async tools."""
        # TODO: Phase 2 — migrate MCP server to fully async and remove
        # _run_async_sync() hack. For now, this is necessary because FastMCP
        # may invoke tool handlers in a sync context.
        return _run_async_sync(_async_handler(tool=tool, **kwargs))

    # Attach metadata so FastMCP can introspect the tool
    handler.__name__ = tool.name
    handler.__doc__ = tool.description

    server.tool(name=tool.name, description=tool.description)(handler)


# ─── Legacy manual MCP tools ────────────────────────────────────────────────
# The tools below were hand-written before the unified ToolRegistry existed.
# They can be REMOVED once the registry-based registration above is validated
# in production and confirmed to cover all use cases.
# Until then, they serve as a fallback with richer MCP-specific formatting
# (e.g. batch metric queries, topology dependencies).


@mcp_server.tool()
def get_servers_health(
    limit: int = 10,
    status_filter: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get server health status and key metrics

    Args:
        limit: Maximum number of servers to return (default: 10)
        status_filter: Filter by status (online/offline/warning)

    Returns:
        Dict containing server health data and metrics
    """
    try:
        with _get_db() as db:
            query = db.query(Host)
            if status_filter:
                query = query.filter(Host.status == status_filter)

            hosts = query.limit(limit).all()
            host_ids = [h.id for h in hosts]

            # 批量查询最新指标，避免 N+1
            latest_metrics: dict[int, HostMetric] = {}
            if host_ids:
                from sqlalchemy import func
                subq = db.query(
                    HostMetric.host_id,
                    func.max(HostMetric.recorded_at).label("max_at")
                ).filter(
                    HostMetric.host_id.in_(host_ids)
                ).group_by(HostMetric.host_id).subquery()

                metrics = db.query(HostMetric).join(
                    subq,
                    (HostMetric.host_id == subq.c.host_id) &
                    (HostMetric.recorded_at == subq.c.max_at)
                ).all()
                latest_metrics = {m.host_id: m for m in metrics}

            servers_data = []
            for host in hosts:
                server_info = {
                    **_host_to_dict(host),
                    "os": host.os,
                    "last_seen": host.last_heartbeat.isoformat() if host.last_heartbeat else None,
                    "metrics": {}
                }

                m = latest_metrics.get(host.id)
                if m:
                    server_info["metrics"] = {
                        "cpu_percent": m.cpu_percent,
                        "memory_percent": m.memory_percent,
                        "disk_percent": m.disk_percent,
                        "cpu_load_1": m.cpu_load_1,
                        "recorded_at": m.recorded_at.isoformat()
                    }

                servers_data.append(server_info)

            # Summary statistics
            total_hosts = db.query(Host).count()
            online_hosts = db.query(Host).filter(Host.status == "online").count()
            offline_hosts = db.query(Host).filter(Host.status == "offline").count()

            return {
                "servers": servers_data,
                "summary": {
                    "total": total_hosts,
                    "online": online_hosts,
                    "offline": offline_hosts,
                    "queried_count": len(servers_data)
                },
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

    except Exception as e:
        logger.error(f"Error getting server health: {e}")
        return {"error": str(e), "servers": [], "summary": {}}


@mcp_server.tool()
def get_alerts(
    severity: Optional[str] = None,
    status: Optional[str] = "firing",
    limit: int = 20,
    hours_back: int = 24
) -> Dict[str, Any]:
    """
    Get active alerts with filtering options

    Args:
        severity: Filter by severity (critical/warning/info)
        status: Filter by status (firing/resolved/acknowledged)
        limit: Maximum alerts to return (default: 20)
        hours_back: Look back this many hours (default: 24)

    Returns:
        Dict containing alert data and statistics
    """
    try:
        with _get_db() as db:
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours_back)

            query = db.query(Alert).filter(Alert.fired_at > cutoff_time)
            if severity:
                query = query.filter(Alert.severity == severity)
            if status:
                query = query.filter(Alert.status == status)

            alerts = query.order_by(Alert.fired_at.desc()).limit(limit).all()

            # 批量预加载 host 和 rule，避免 N+1
            host_ids = {a.host_id for a in alerts if a.host_id}
            rule_ids = {a.rule_id for a in alerts if a.rule_id}

            hosts_map = {}
            if host_ids:
                hosts_map = {h.id: h for h in db.query(Host).filter(Host.id.in_(host_ids)).all()}
            rules_map = {}
            if rule_ids:
                rules_map = {r.id: r for r in db.query(AlertRule).filter(AlertRule.id.in_(rule_ids)).all()}

            alerts_data = []
            for alert in alerts:
                host = hosts_map.get(alert.host_id)
                rule = rules_map.get(alert.rule_id)

                alert_info = {
                    "id": alert.id,
                    "title": alert.title,
                    "message": alert.message,
                    "severity": alert.severity,
                    "status": alert.status,
                    "metric_value": alert.metric_value,
                    "threshold": alert.threshold,
                    "fired_at": alert.fired_at.isoformat(),
                    "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
                    "host": _host_to_dict(host) if host else None,
                    "rule": {
                        "id": rule.id,
                        "name": rule.name,
                        "metric": rule.metric,
                        "operator": rule.operator
                    } if rule else None
                }
                alerts_data.append(alert_info)

            # Statistics — 合并为一次查询
            from sqlalchemy import func, case
            stats = db.query(
                func.count(Alert.id).label("total"),
                func.count(case((Alert.severity == "critical", Alert.id))).label("critical"),
            ).filter(Alert.fired_at > cutoff_time).one()

            return {
                "alerts": alerts_data,
                "statistics": {
                    "total_in_period": stats.total or 0,
                    "critical_count": stats.critical or 0,
                    "returned_count": len(alerts_data),
                    "time_range_hours": hours_back
                },
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

    except Exception as e:
        logger.error(f"Error getting alerts: {e}")
        return {"error": str(e), "alerts": [], "statistics": {}}


@mcp_server.tool()
def search_logs(
    keyword: str,
    host_id: Optional[int] = None,
    service: Optional[str] = None,
    level: Optional[str] = None,
    hours_back: int = 1,
    limit: int = 50
) -> Dict[str, Any]:
    """
    Search logs with keyword and filters

    Args:
        keyword: Search keyword in log messages
        host_id: Filter by specific host ID
        service: Filter by service name
        level: Filter by log level (DEBUG/INFO/WARN/ERROR/FATAL)
        hours_back: Search in last N hours (default: 1)
        limit: Maximum log entries to return (default: 50)

    Returns:
        Dict containing matching log entries and metadata
    """
    try:
        with _get_db() as db:
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours_back)

            query = db.query(LogEntry).filter(
                LogEntry.timestamp > cutoff_time,
                LogEntry.message.contains(keyword)
            )

            if host_id:
                query = query.filter(LogEntry.host_id == host_id)
            if service:
                query = query.filter(LogEntry.service == service)
            if level:
                query = query.filter(LogEntry.level == level)

            logs = query.order_by(LogEntry.timestamp.desc()).limit(limit).all()

            # 批量预加载 host，避免 N+1
            log_host_ids = {log.host_id for log in logs if log.host_id}
            hosts_map = {}
            if log_host_ids:
                hosts_map = {h.id: h for h in db.query(Host).filter(Host.id.in_(log_host_ids)).all()}

            logs_data = []
            for log in logs:
                host = hosts_map.get(log.host_id)
                log_info = {
                    "id": log.id,
                    "message": log.message,
                    "level": log.level,
                    "service": log.service,
                    "source": log.source,
                    "timestamp": log.timestamp.isoformat(),
                    "host": _host_to_dict(host) if host else None
                }
                logs_data.append(log_info)

            # 总匹配数
            from sqlalchemy import func
            total_matches = db.query(func.count(LogEntry.id)).filter(
                LogEntry.timestamp > cutoff_time,
                LogEntry.message.contains(keyword)
            ).scalar() or 0

            return {
                "logs": logs_data,
                "search_info": {
                    "keyword": keyword,
                    "total_matches": total_matches,
                    "returned_count": len(logs_data),
                    "time_range_hours": hours_back,
                    "filters": {
                        "host_id": host_id,
                        "service": service,
                        "level": level
                    }
                },
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

    except Exception as e:
        logger.error(f"Error searching logs: {e}")
        return {"error": str(e), "logs": [], "search_info": {}}


@mcp_server.tool()
def analyze_incident(
    alert_id: Optional[int] = None,
    description: Optional[str] = None,
    include_context: bool = True
) -> Dict[str, Any]:
    """
    AI-powered incident root cause analysis via OpsAgentLoop

    Args:
        alert_id: Specific alert to analyze
        description: Free-text incident description
        include_context: Include related metrics and logs in analysis

    Returns:
        Dict containing AI analysis, root cause, and recommendations
    """
    try:
        with _get_db() as db:
            context_data = {}

            if alert_id:
                alert = db.query(Alert).filter(Alert.id == alert_id).first()
                if not alert:
                    return {"error": f"Alert {alert_id} not found"}

                context_data["alert"] = {
                    "title": alert.title,
                    "message": alert.message,
                    "severity": alert.severity,
                    "metric_value": alert.metric_value,
                    "threshold": alert.threshold,
                    "fired_at": alert.fired_at.isoformat()
                }

                if include_context and alert.host_id:
                    recent_metrics = db.query(HostMetric).filter(
                        HostMetric.host_id == alert.host_id,
                        HostMetric.recorded_at > alert.fired_at - timedelta(hours=1)
                    ).order_by(HostMetric.recorded_at.desc()).limit(10).all()

                    context_data["recent_metrics"] = [
                        {
                            "cpu_percent": m.cpu_percent,
                            "memory_percent": m.memory_percent,
                            "disk_percent": m.disk_percent,
                            "recorded_at": m.recorded_at.isoformat()
                        } for m in recent_metrics
                    ]

                    related_logs = db.query(LogEntry).filter(
                        LogEntry.host_id == alert.host_id,
                        LogEntry.timestamp.between(
                            alert.fired_at - timedelta(minutes=30),
                            alert.fired_at + timedelta(minutes=10)
                        )
                    ).order_by(LogEntry.timestamp.desc()).limit(20).all()

                    context_data["related_logs"] = [
                        {
                            "message": log.message,
                            "level": log.level,
                            "service": log.service,
                            "timestamp": log.timestamp.isoformat()
                        } for log in related_logs
                    ]

            # 使用专用 MCP 服务账号（viewer 角色，最小权限），不冒充 admin
            mcp_user = db.query(User).filter(User.email == "mcp-service@nightmend.internal").first()
            if not mcp_user:
                # 自动创建专用服务账号（viewer 角色，禁止登录）
                from app.core.security import get_password_hash
                import secrets
                mcp_user = User(
                    email="mcp-service@nightmend.internal",
                    name="MCP Service",
                    hashed_password=get_password_hash(secrets.token_hex(32)),
                    role="viewer",
                    is_active=True,
                )
                db.add(mcp_user)
                db.commit()
                db.refresh(mcp_user)

            # 创建临时 OpsSession
            session_id = str(uuid.uuid4())
            temp_session = OpsSession(
                id=session_id,
                user_id=mcp_user.id,
                title="MCP 事件分析",
            )
            db.add(temp_session)
            db.commit()

        # DB session 已关闭，在独立线程中运行异步分析（使用自己的 DB 连接）
        prompt = (
            "你是 NightMend AI 运维助手。请基于以下告警上下文做根因分析与处置建议。\n"
            "限制：本次仅做分析，不要调用 execute_command，不要 ask_user，不要等待人工确认。\n\n"
            f"事件描述：{description or 'Automated incident analysis'}\n"
            f"上下文JSON：{json.dumps(context_data, ensure_ascii=False)}"
        )

        loop_result = _run_async_sync(_run_ops_loop_for_mcp(session_id, mcp_user.id, prompt))
        analysis_result = loop_result.get("analysis_text") or "未获得分析结论"

        # 更新 session 状态
        with _get_db() as db:
            session_obj = db.query(OpsSession).filter(OpsSession.id == session_id).first()
            if session_obj:
                session_obj.status = "closed"
                session_obj.updated_at = datetime.now(timezone.utc)
                db.commit()

        return {
            "analysis": analysis_result,
            "context_used": bool(context_data),
            "engine": "ops_agent_loop",
            "session_id": session_id,
            "tool_trace": loop_result.get("tool_trace", []),
            "error": loop_result.get("error"),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        logger.error(f"Error analyzing incident: {e}")
        return {"error": str(e), "analysis": "Analysis failed"}


@mcp_server.tool()
def get_topology(
    service_id: Optional[int] = None,
    include_dependencies: bool = True
) -> Dict[str, Any]:
    """
    Get service topology and dependency mapping

    Args:
        service_id: Focus on specific service (optional)
        include_dependencies: Include dependency relationships

    Returns:
        Dict containing topology data and service relationships
    """
    try:
        with _get_db() as db:
            if service_id:
                services = db.query(Service).filter(Service.id == service_id).all()
            else:
                services = db.query(Service).limit(50).all()

            # 批量预加载 host，避免 N+1
            svc_host_ids = {s.host_id for s in services if s.host_id}
            hosts_map = {}
            if svc_host_ids:
                hosts_map = {h.id: h for h in db.query(Host).filter(Host.id.in_(svc_host_ids)).all()}

            services_data = []
            for service in services:
                host = hosts_map.get(service.host_id)
                service_info = {
                    "id": service.id,
                    "name": service.name,
                    "status": service.status,
                    "type": service.type,
                    "port": service.port,
                    "category": getattr(service, 'category', 'unknown'),
                    "host": _host_to_dict(host) if host else None
                }
                services_data.append(service_info)

            # 查询真实的服务依赖关系
            dependencies_data = []
            if include_dependencies:
                svc_ids = [s.id for s in services]
                if svc_ids:
                    deps = db.query(ServiceDependency).filter(
                        (ServiceDependency.source_service_id.in_(svc_ids)) |
                        (ServiceDependency.target_service_id.in_(svc_ids))
                    ).all()
                    dependencies_data = [
                        {
                            "from_service_id": dep.source_service_id,
                            "to_service_id": dep.target_service_id,
                            "type": dep.dependency_type,
                            "description": dep.description,
                        } for dep in deps
                    ]

            return {
                "topology": {
                    "services": services_data,
                    "dependencies": dependencies_data,
                    "metadata": {
                        "service_count": len(services_data),
                        "dependency_count": len(dependencies_data),
                        "focused_service_id": service_id,
                    }
                },
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

    except Exception as e:
        logger.error(f"Error getting topology: {e}")
        return {"error": str(e), "topology": {"services": [], "dependencies": []}}


# Server management functions
def start_mcp_server(host: str = "127.0.0.1", port: int = 8003):
    """Start the MCP server with optional Bearer Token authentication"""
    import uvicorn
    import asyncio
    from starlette.responses import JSONResponse
    from app.tools import init_tool_registry

    # Ensure the ToolRegistry is populated before registering MCP tools.
    # If init_tool_registry() was already called at app startup, the registry
    # already has tools — skip re-discovery to avoid duplicate ValueError.
    if tool_registry.tool_count == 0:
        init_tool_registry()
    registered = register_tools_from_registry(mcp_server)
    logger.info("MCP: %d tools auto-registered from ToolRegistry", registered)

    api_key = settings.nightmend_mcp_api_key
    logger.info(f"Starting NightMend MCP Server on {host}:{port}")

    if not api_key:
        import os
        env = os.getenv("ENVIRONMENT", "production").lower()
        if env != "development":
            logger.error("NIGHTMEND_MCP_API_KEY not set — refusing to start MCP server without authentication in production")
            return
        logger.warning("NIGHTMEND_MCP_API_KEY not set — MCP server running without authentication (development mode)")
        asyncio.run(mcp_server.run_http_async(host=host, port=port))
        return

    logger.info("Bearer Token auth enabled for MCP server")
    mcp_app = mcp_server.http_app()

    class BearerAuthMiddleware:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            if scope["type"] in ("http", "websocket"):
                headers = dict(scope.get("headers", []))
                auth = headers.get(b"authorization", b"").decode("latin-1")
                token = auth[7:] if auth.startswith("Bearer ") else ""
                if token != api_key:
                    if scope["type"] == "http":
                        response = JSONResponse({"detail": "Unauthorized"}, status_code=401)
                        await response(scope, receive, send)
                        return
                    else:
                        # WebSocket: 拒绝连接
                        await send({"type": "websocket.close", "code": 4401})
                        return
            await self.app(scope, receive, send)

    uvicorn.run(BearerAuthMiddleware(mcp_app), host=host, port=port)


def stop_mcp_server():
    """Stop the MCP server"""
    logger.info("Stopping NightMend MCP Server")


if __name__ == "__main__":
    import os

    host = os.environ.get("NIGHTMEND_MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("NIGHTMEND_MCP_PORT", "8003"))
    start_mcp_server(host=host, port=port)


# Export the server instance
__all__ = ["mcp_server", "start_mcp_server", "stop_mcp_server", "register_tools_from_registry"]
