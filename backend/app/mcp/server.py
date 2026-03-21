"""
VigilOps MCP Server (Model Context Protocol Server)

Exposes VigilOps core operational tools to AI agents through the MCP protocol.
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
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any, Union

from fastmcp import FastMCP
from pydantic import BaseModel

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.host import Host
from app.models.alert import Alert, AlertRule
from app.models.log_entry import LogEntry  
from app.models.service import Service
from app.models.host_metric import HostMetric
from app.models.user import User
from app.models.ops_session import OpsSession
from app.services.ops_agent_loop import get_or_create_loop, remove_loop

logger = logging.getLogger(__name__)

# Initialize FastMCP server
mcp_server = FastMCP("VigilOps")


class VigilOpsMCP:
    """VigilOps MCP Tools Provider"""
    
    def __init__(self):
        self.db = None
        
    def get_db(self):
        """Get database session"""
        if self.db is None or not self.db.is_active:
            self.db = SessionLocal()
        return self.db
        
    def close_db(self):
        """Close database session"""
        if self.db:
            self.db.close()
            self.db = None


# Global instance
vigilops_mcp = VigilOpsMCP()


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
        db = vigilops_mcp.get_db()
        
        # Query hosts with latest metrics
        query = db.query(Host)
        if status_filter:
            query = query.filter(Host.status == status_filter)
        
        hosts = query.limit(limit).all()
        
        servers_data = []
        for host in hosts:
            # Get latest metrics
            latest_metric = db.query(HostMetric).filter(
                HostMetric.host_id == host.id
            ).order_by(HostMetric.recorded_at.desc()).first()
            
            server_info = {
                "id": host.id,
                "hostname": host.hostname,
                "display_name": host.display_name,
                "display_hostname": host.display_hostname,
                "ip": host.display_ip,
                "status": host.status,
                "os": host.os,
                "last_seen": host.last_heartbeat.isoformat() if host.last_heartbeat else None,
                "metrics": {}
            }
            
            if latest_metric:
                server_info["metrics"] = {
                    "cpu_percent": latest_metric.cpu_percent,
                    "memory_percent": latest_metric.memory_percent,
                    "disk_percent": latest_metric.disk_percent,
                    "cpu_load_1": latest_metric.cpu_load_1,
                    "recorded_at": latest_metric.recorded_at.isoformat()
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
        db = vigilops_mcp.get_db()
        
        # Time filter
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        
        # Build query
        query = db.query(Alert).filter(Alert.fired_at > cutoff_time)
        
        if severity:
            query = query.filter(Alert.severity == severity)
        if status:
            query = query.filter(Alert.status == status)
            
        # Order by severity and time
        severity_order = {"critical": 3, "warning": 2, "info": 1}
        alerts = query.order_by(Alert.fired_at.desc()).limit(limit).all()
        
        alerts_data = []
        for alert in alerts:
            # Get host and rule info
            host = db.query(Host).filter(Host.id == alert.host_id).first()
            rule = db.query(AlertRule).filter(AlertRule.id == alert.rule_id).first()
            
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
                "host": {
                    "id": host.id,
                    "hostname": host.hostname,
                    "display_name": host.display_name,
                    "display_hostname": host.display_hostname,
                    "ip": host.display_ip
                } if host else None,
                "rule": {
                    "id": rule.id,
                    "name": rule.name,
                    "metric": rule.metric,
                    "operator": rule.operator
                } if rule else None
            }
            alerts_data.append(alert_info)
        
        # Statistics
        total_alerts = db.query(Alert).filter(Alert.fired_at > cutoff_time).count()
        critical_count = db.query(Alert).filter(
            Alert.fired_at > cutoff_time, 
            Alert.severity == "critical"
        ).count()
        
        return {
            "alerts": alerts_data,
            "statistics": {
                "total_in_period": total_alerts,
                "critical_count": critical_count,
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
        db = vigilops_mcp.get_db()
        
        # Time filter
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        
        # Build query
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
            
        # Order by timestamp desc and limit
        logs = query.order_by(LogEntry.timestamp.desc()).limit(limit).all()
        
        logs_data = []
        for log in logs:
            # Get host info
            host = db.query(Host).filter(Host.id == log.host_id).first()
            
            log_info = {
                "id": log.id,
                "message": log.message,
                "level": log.level,
                "service": log.service,
                "source": log.source,
                "timestamp": log.timestamp.isoformat(),
                "host": {
                    "id": host.id,
                    "hostname": host.hostname,
                    "display_name": host.display_name,
                    "display_hostname": host.display_hostname,
                    "ip": host.display_ip
                } if host else None
            }
            logs_data.append(log_info)
        
        # Statistics  
        total_matches = db.query(LogEntry).filter(
            LogEntry.timestamp > cutoff_time,
            LogEntry.message.contains(keyword)
        ).count()
        
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
        db = vigilops_mcp.get_db()
        context_data = {}
        
        if alert_id:
            # Get alert details
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
                # Get recent metrics for this host
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
                
                # Get related logs
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
        
        # 选择一个可用用户作为会话归属（MCP 无显式用户上下文）
        mcp_user = db.query(User).order_by(User.id.asc()).first()
        if not mcp_user:
            return {"error": "No available user for MCP analyze_incident"}

        # 创建临时 OpsSession，复用新 AI Agent Loop 流程
        session_id = str(uuid.uuid4())
        temp_session = OpsSession(
            id=session_id,
            user_id=mcp_user.id,
            title="MCP 事件分析",
        )
        db.add(temp_session)
        db.commit()

        prompt = (
            "你是 VigilOps AI 运维助手。请基于以下告警上下文做根因分析与处置建议。\n"
            "限制：本次仅做分析，不要调用 execute_command，不要 ask_user，不要等待人工确认。\n\n"
            f"事件描述：{description or 'Automated incident analysis'}\n"
            f"上下文JSON：{json.dumps(context_data, ensure_ascii=False)}"
        )

        loop_result = _run_async_sync(_run_ops_loop_for_mcp(session_id, mcp_user.id, prompt))
        analysis_result = loop_result.get("analysis_text") or "未获得分析结论"

        temp_session.status = "closed"
        temp_session.updated_at = datetime.now(timezone.utc)
        db.commit()

        return {
            "analysis": analysis_result,
            "context_used": bool(context_data),
            "engine": "ops_agent_loop",
            "session_id": session_id,
            "tool_trace": loop_result.get("tool_trace", []),
            "error": loop_result.get("error"),
            "recommendations": [
                "Check system resource utilization",
                "Review recent configuration changes", 
                "Monitor related services",
                "Verify network connectivity"
            ],
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
        db = vigilops_mcp.get_db()
        
        # Get services
        if service_id:
            services = db.query(Service).filter(Service.id == service_id).all()
        else:
            services = db.query(Service).limit(50).all()  # Limit to prevent huge responses
            
        topology_data = {
            "services": [],
            "dependencies": [],
            "metadata": {
                "service_count": len(services),
                "focused_service_id": service_id,
                "include_dependencies": include_dependencies
            }
        }
        
        for service in services:
            # Get host info
            host = db.query(Host).filter(Host.id == service.host_id).first()
            
            service_info = {
                "id": service.id,
                "name": service.name,
                "status": service.status,
                "type": service.type,
                "port": service.port,
                "category": getattr(service, 'category', 'unknown'),
                "host": {
                    "id": host.id,
                    "hostname": host.hostname,
                    "display_name": host.display_name,
                    "display_hostname": host.display_hostname,
                    "ip": host.display_ip,
                    "status": host.status
                } if host else None
            }
            topology_data["services"].append(service_info)
        
        # Note: Dependencies would require ServiceDependency model queries
        # This is a simplified version for MVP
        if include_dependencies:
            topology_data["dependencies"] = [
                # Placeholder - would query actual dependency relationships
                {
                    "from_service_id": None,
                    "to_service_id": None,
                    "type": "dependency"
                }
            ]
        
        return {
            "topology": topology_data,
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

    api_key = settings.vigilops_mcp_api_key
    logger.info(f"Starting VigilOps MCP Server on {host}:{port}")

    if not api_key:
        import os
        env = os.getenv("ENVIRONMENT", "production").lower()
        if env != "development":
            logger.error("VIGILOPS_MCP_API_KEY not set — refusing to start MCP server without authentication in production")
            return
        logger.warning("VIGILOPS_MCP_API_KEY not set — MCP server running without authentication (development mode)")
        asyncio.run(mcp_server.run_http_async(host=host, port=port))
        return

    logger.info("Bearer Token auth enabled for MCP server")
    mcp_app = mcp_server.http_app()

    class BearerAuthMiddleware:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            if scope["type"] == "http":
                headers = dict(scope.get("headers", []))
                auth = headers.get(b"authorization", b"").decode("latin-1")
                token = auth[7:] if auth.startswith("Bearer ") else ""
                if token != api_key:
                    response = JSONResponse({"detail": "Unauthorized"}, status_code=401)
                    await response(scope, receive, send)
                    return
            await self.app(scope, receive, send)

    uvicorn.run(BearerAuthMiddleware(mcp_app), host=host, port=port)


def stop_mcp_server():
    """Stop the MCP server"""
    logger.info("Stopping VigilOps MCP Server")
    vigilops_mcp.close_db()


if __name__ == "__main__":
    import os

    host = os.environ.get("VIGILOPS_MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("VIGILOPS_MCP_PORT", "8003"))
    start_mcp_server(host=host, port=port)


# Export the server instance
__all__ = ["mcp_server", "start_mcp_server", "stop_mcp_server", "vigilops_mcp"]
