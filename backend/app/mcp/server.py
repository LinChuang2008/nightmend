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
import json
import logging
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any, Union

from fastmcp import FastMCP
from pydantic import BaseModel

from sqlalchemy import func as sa_func

from app.core.config import settings
from app.core.database import SessionLocal
from app.services.ai_engine import AIEngine
from app.models.host import Host
from app.models.alert import Alert, AlertRule
from app.models.log_entry import LogEntry
from app.models.service import Service
from app.models.host_metric import HostMetric

logger = logging.getLogger(__name__)

# Initialize FastMCP server
mcp_server = FastMCP("VigilOps")


@contextmanager
def get_mcp_db():
    """每次调用创建独立的数据库 Session，用完即关闭，防止连接泄漏"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


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
        with get_mcp_db() as db:
            query = db.query(Host)
            if status_filter:
                query = query.filter(Host.status == status_filter)

            hosts = query.limit(limit).all()
            host_ids = [h.id for h in hosts]

            # Batch fetch latest metrics to avoid N+1 queries
            metrics_map = {}
            if host_ids:
                latest_sub = (
                    db.query(
                        HostMetric.host_id,
                        sa_func.max(HostMetric.recorded_at).label("max_at"),
                    )
                    .filter(HostMetric.host_id.in_(host_ids))
                    .group_by(HostMetric.host_id)
                    .subquery()
                )
                latest_metrics = (
                    db.query(HostMetric)
                    .join(
                        latest_sub,
                        (HostMetric.host_id == latest_sub.c.host_id)
                        & (HostMetric.recorded_at == latest_sub.c.max_at),
                    )
                    .all()
                )
                metrics_map = {m.host_id: m for m in latest_metrics}

            servers_data = []
            for host in hosts:
                server_info = {
                    "id": host.id,
                    "hostname": host.hostname,
                    "ip": host.ip_address_address,
                    "status": host.status,
                    "os": host.os,
                    "last_seen": host.last_heartbeat.isoformat() if host.last_heartbeat else None,
                    "metrics": {}
                }

                latest_metric = metrics_map.get(host.id)
                if latest_metric:
                    server_info["metrics"] = {
                        "cpu_percent": latest_metric.cpu_percent,
                        "memory_percent": latest_metric.memory_percent,
                        "disk_percent": latest_metric.disk_percent,
                        "cpu_load_1": latest_metric.cpu_load_1,
                        "recorded_at": latest_metric.recorded_at.isoformat()
                    }

                servers_data.append(server_info)

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
        with get_mcp_db() as db:
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours_back)

            query = db.query(Alert).filter(Alert.fired_at > cutoff_time)
            if severity:
                query = query.filter(Alert.severity == severity)
            if status:
                query = query.filter(Alert.status == status)

            alerts = query.order_by(Alert.fired_at.desc()).limit(limit).all()

            # Batch fetch related hosts and rules to avoid N+1
            host_ids = {a.host_id for a in alerts if a.host_id}
            rule_ids = {a.rule_id for a in alerts if a.rule_id}
            hosts_map = {h.id: h for h in db.query(Host).filter(Host.id.in_(host_ids)).all()} if host_ids else {}
            rules_map = {r.id: r for r in db.query(AlertRule).filter(AlertRule.id.in_(rule_ids)).all()} if rule_ids else {}

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
                    "host": {
                        "id": host.id,
                        "hostname": host.hostname,
                        "ip": host.ip_address
                    } if host else None,
                    "rule": {
                        "id": rule.id,
                        "name": rule.name,
                        "metric": rule.metric,
                        "operator": rule.operator
                    } if rule else None
                }
                alerts_data.append(alert_info)

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
        with get_mcp_db() as db:
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

            # Batch fetch hosts to avoid N+1
            log_host_ids = {log.host_id for log in logs if log.host_id}
            hosts_map = {h.id: h for h in db.query(Host).filter(Host.id.in_(log_host_ids)).all()} if log_host_ids else {}

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
                    "host": {
                        "id": host.id,
                        "hostname": host.hostname,
                        "ip": host.ip_address
                    } if host else None
                }
                logs_data.append(log_info)

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
    AI-powered incident root cause analysis (VigilOps differentiator)
    
    Args:
        alert_id: Specific alert to analyze
        description: Free-text incident description
        include_context: Include related metrics and logs in analysis
        
    Returns:
        Dict containing AI analysis, root cause, and recommendations
    """
    try:
        with get_mcp_db() as db:
            ai_engine = AIEngine()
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

            analysis_result = ai_engine.analyze_complex_incident(
                json.dumps(context_data),
                description or "Please analyze this incident"
            )

            return {
                "analysis": analysis_result,
                "context_used": bool(context_data),
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
        with get_mcp_db() as db:
            if service_id:
                services = db.query(Service).filter(Service.id == service_id).all()
            else:
                services = db.query(Service).limit(50).all()

            topology_data = {
                "services": [],
                "dependencies": [],
                "metadata": {
                    "service_count": len(services),
                    "focused_service_id": service_id,
                    "include_dependencies": include_dependencies
                }
            }

            # Batch fetch hosts to avoid N+1
            svc_host_ids = {s.host_id for s in services if s.host_id}
            hosts_map = {h.id: h for h in db.query(Host).filter(Host.id.in_(svc_host_ids)).all()} if svc_host_ids else {}

            for service in services:
                host = hosts_map.get(service.host_id)

                service_info = {
                    "id": service.id,
                    "name": service.name,
                    "status": service.status,
                    "type": service.type,
                    "target": service.target,
                    "category": getattr(service, 'category', 'unknown'),
                    "host": {
                        "id": host.id,
                        "hostname": host.hostname,
                        "ip": host.ip_address_address,
                        "status": host.status
                    } if host else None
                }
                topology_data["services"].append(service_info)

            if include_dependencies:
                topology_data["dependencies"] = [
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
        logger.warning("VIGILOPS_MCP_API_KEY not set — MCP server running without authentication")
        # Use streamable HTTP transport without authentication
        asyncio.run(mcp_server.run_http_async(host=host, port=port))
        return

    logger.info("Bearer Token auth enabled for MCP server")
    mcp_app = mcp_server.streamable_http_app()

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


if __name__ == "__main__":
    import os

    host = os.environ.get("VIGILOPS_MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("VIGILOPS_MCP_PORT", "8003"))
    start_mcp_server(host=host, port=port)


# Export the server instance
__all__ = ["mcp_server", "start_mcp_server", "stop_mcp_server"]