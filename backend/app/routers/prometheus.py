"""
Prometheus 兼容性路由模块 (Prometheus Compatibility Router)

功能说明：提供 Prometheus 格式的指标暴露接口，支持标准的 /metrics 端点
核心职责：
  - 暴露主机性能指标（CPU、内存、磁盘、网络）
  - 暴露服务监控指标（状态、响应时间）
  - 暴露告警统计指标（告警数量、严重级别分布）
  - 兼容 Prometheus 文本格式和命名规范
依赖关系：依赖 SQLAlchemy、Redis 缓存
API端点：GET /metrics (Prometheus 标准端点)

Author: VigilOps Team
"""
import hashlib
import json
from typing import List, Dict, Any, Optional, Union
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, func, desc, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis import get_redis
from app.core.security import decode_token
from app.core.redis import is_token_blacklisted
from app.models.host import Host
from app.models.host_metric import HostMetric
from app.models.service import Service
from app.models.service import ServiceCheck
from app.models.alert import Alert
from app.models.user import User
from app.models.agent_token import AgentToken

# Bearer Token 认证（auto_error=False 允许回退到 cookie）
_security = HTTPBearer(auto_error=False)


async def _require_user_or_agent_token(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_security),
    db: AsyncSession = Depends(get_db),
) -> Union[User, AgentToken]:
    """
    组合认证：接受用户 JWT 或 Agent Token。
    Prometheus server 用 agent token 拉取，Web UI 用用户 JWT 访问。
    """
    token_str: Optional[str] = None

    if credentials is not None:
        token_str = credentials.credentials
    else:
        token_str = request.cookies.get("access_token")

    if not token_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 1. 尝试作为用户 JWT 解析
    payload = decode_token(token_str)
    if payload is not None and payload.get("type") == "access":
        jti = payload.get("jti")
        if jti and await is_token_blacklisted(jti):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has been revoked")
        user_id = payload.get("sub")
        if user_id is not None:
            result = await db.execute(select(User).where(User.id == int(user_id)))
            user = result.scalar_one_or_none()
            if user is not None and user.is_active:
                return user

    # 2. 回退：尝试作为 Agent Token 验证
    token_hash = hashlib.sha256(token_str.encode()).hexdigest()
    result = await db.execute(
        select(AgentToken).where(
            AgentToken.token_hash == token_hash,
            AgentToken.is_active == True,  # noqa: E712
        )
    )
    agent_token = result.scalar_one_or_none()
    if agent_token is not None:
        await db.execute(
            update(AgentToken)
            .where(AgentToken.id == agent_token.id)
            .values(last_used_at=datetime.now(timezone.utc))
        )
        await db.commit()
        return agent_token

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

router = APIRouter(prefix="/api/v1", tags=["prometheus"])


def format_prometheus_metric(name: str, value: float, labels: Dict[str, str] = None, help_text: str = None, metric_type: str = None) -> str:
    """
    格式化 Prometheus 指标格式
    
    Args:
        name: 指标名称
        value: 指标值
        labels: 标签字典
        help_text: 帮助文本
        metric_type: 指标类型 (counter, gauge, histogram, summary)
    
    Returns:
        str: Prometheus 格式的指标行
    """
    lines = []
    
    if help_text:
        lines.append(f"# HELP {name} {help_text}")
    
    if metric_type:
        lines.append(f"# TYPE {name} {metric_type}")
    
    if labels:
        label_str = ",".join([f'{k}="{v}"' for k, v in labels.items()])
        lines.append(f"{name}{{{label_str}}} {value}")
    else:
        lines.append(f"{name} {value}")
    
    return "\n".join(lines)


@router.get("/metrics", response_class=Response)
async def prometheus_metrics(
    auth: Union[User, AgentToken] = Depends(_require_user_or_agent_token),
    db: AsyncSession = Depends(get_db),
):
    """
    Prometheus 兼容的指标暴露端点
    
    返回 Prometheus 文本格式的监控指标，包括：
    - 主机性能指标 (vigilops_host_cpu_percent, vigilops_host_memory_percent 等)
    - 服务状态指标 (vigilops_service_up, vigilops_service_response_time 等)
    - 告警统计指标 (vigilops_alerts_total, vigilops_alerts_by_severity 等)
    - 系统状态指标 (vigilops_hosts_total, vigilops_services_total 等)
    
    格式兼容 Prometheus 官方规范：https://prometheus.io/docs/instrumenting/exposition_formats/
    """
    metrics_lines = []
    
    try:
        # 1. 主机性能指标
        # 获取最新的主机指标数据
        latest_metrics_query = select(
            HostMetric.host_id,
            HostMetric.cpu_percent,
            HostMetric.cpu_load_1,
            HostMetric.cpu_load_5,
            HostMetric.cpu_load_15,
            HostMetric.memory_percent,
            HostMetric.disk_percent,
            HostMetric.net_bytes_sent,
            HostMetric.net_bytes_recv,
            Host.hostname.label('hostname'),
            Host.ip_address.label('host_ip'),
            Host.group_name
        ).select_from(
            HostMetric.__table__.join(Host.__table__, HostMetric.host_id == Host.id)
        ).where(
            HostMetric.id.in_(
                select(func.max(HostMetric.id)).group_by(HostMetric.host_id)
            )
        )
        
        result = await db.execute(latest_metrics_query)
        host_metrics = result.mappings().all()
        
        # CPU 指标
        for metric in host_metrics:
            labels = {
                "hostname": metric['hostname'],
                "host_ip": metric['host_ip'],
                "group": metric['group_name'] or "default"
            }
            
            metrics_lines.append(format_prometheus_metric(
                "vigilops_host_cpu_percent",
                metric['cpu_percent'] or 0,
                labels,
                "Host CPU usage percentage",
                "gauge"
            ))
            
            metrics_lines.append(format_prometheus_metric(
                "vigilops_host_cpu_load_1m",
                metric['cpu_load_1'] or 0,
                labels,
                "Host 1-minute load average",
                "gauge"
            ))
            
            metrics_lines.append(format_prometheus_metric(
                "vigilops_host_cpu_load_5m",
                metric['cpu_load_5'] or 0,
                labels,
                "Host 5-minute load average",
                "gauge"
            ))
            
            metrics_lines.append(format_prometheus_metric(
                "vigilops_host_cpu_load_15m",
                metric['cpu_load_15'] or 0,
                labels,
                "Host 15-minute load average",
                "gauge"
            ))
            
            # 内存指标
            metrics_lines.append(format_prometheus_metric(
                "vigilops_host_memory_percent",
                metric['memory_percent'] or 0,
                labels,
                "Host memory usage percentage",
                "gauge"
            ))
            
            # 磁盘指标
            metrics_lines.append(format_prometheus_metric(
                "vigilops_host_disk_percent",
                metric['disk_percent'] or 0,
                labels,
                "Host disk usage percentage",
                "gauge"
            ))
            
            # 网络指标
            metrics_lines.append(format_prometheus_metric(
                "vigilops_host_network_bytes_sent_total",
                metric['net_bytes_sent'] or 0,
                labels,
                "Total bytes sent over network",
                "counter"
            ))
            
            metrics_lines.append(format_prometheus_metric(
                "vigilops_host_network_bytes_received_total",
                metric['net_bytes_recv'] or 0,
                labels,
                "Total bytes received over network",
                "counter"
            ))
        
        # 2. 服务状态指标
        services_query = select(Service)
        services_result = await db.execute(services_query)
        services = services_result.scalars().all()
        
        # 获取最新的服务检查结果
        for service in services:
            latest_check_query = select(ServiceCheck).where(
                ServiceCheck.service_id == service.id
            ).order_by(desc(ServiceCheck.checked_at)).limit(1)
            
            check_result = await db.execute(latest_check_query)
            latest_check = check_result.scalar_one_or_none()
            
            labels = {
                "service_name": service.name,
                "service_type": service.type or "unknown",
                "host_ip": service.host or "unknown"
            }
            
            # 服务状态 (1 = up, 0 = down)
            status_value = 1 if (latest_check and latest_check.status == 'up') else 0
            metrics_lines.append(format_prometheus_metric(
                "vigilops_service_up",
                status_value,
                labels,
                "Service availability (1 = up, 0 = down)",
                "gauge"
            ))
            
            # 响应时间
            if latest_check and latest_check.response_time:
                metrics_lines.append(format_prometheus_metric(
                    "vigilops_service_response_time_seconds",
                    latest_check.response_time / 1000.0,  # 转换为秒
                    labels,
                    "Service response time in seconds",
                    "gauge"
                ))
        
        # 3. 告警统计指标
        alerts_query = select(
            Alert.status,
            Alert.severity,
            func.count().label('count')
        ).group_by(Alert.status, Alert.severity)
        
        alerts_result = await db.execute(alerts_query)
        alert_stats = alerts_result.mappings().all()
        
        for stat in alert_stats:
            labels = {
                "status": stat['status'],
                "severity": stat['severity']
            }
            
            metrics_lines.append(format_prometheus_metric(
                "vigilops_alerts_total",
                stat['count'],
                labels,
                "Total number of alerts by status and severity",
                "gauge"
            ))
        
        # 4. 系统状态统计
        # 主机总数和状态统计
        hosts_query = select(
            Host.status,
            func.count().label('count')
        ).group_by(Host.status)
        
        hosts_result = await db.execute(hosts_query)
        host_stats = hosts_result.mappings().all()
        
        total_hosts = sum(stat['count'] for stat in host_stats)
        metrics_lines.append(format_prometheus_metric(
            "vigilops_hosts_total",
            total_hosts,
            None,
            "Total number of monitored hosts",
            "gauge"
        ))
        
        for stat in host_stats:
            metrics_lines.append(format_prometheus_metric(
                "vigilops_hosts_by_status",
                stat['count'],
                {"status": stat['status']},
                "Number of hosts by status",
                "gauge"
            ))
        
        # 服务总数统计
        services_count_query = select(func.count(Service.id))
        services_count_result = await db.execute(services_count_query)
        total_services = services_count_result.scalar()
        
        metrics_lines.append(format_prometheus_metric(
            "vigilops_services_total",
            total_services,
            None,
            "Total number of monitored services",
            "gauge"
        ))
        
        # 5. VigilOps 自身状态指标
        metrics_lines.append(format_prometheus_metric(
            "vigilops_up",
            1,
            {"version": "1.0.0"},
            "VigilOps system availability",
            "gauge"
        ))
        
        # 添加时间戳
        current_timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
        metrics_lines.append(format_prometheus_metric(
            "vigilops_last_scrape_timestamp_ms",
            current_timestamp,
            None,
            "Last scrape timestamp in milliseconds",
            "gauge"
        ))
        
    except Exception as e:
        # 如果获取指标失败，至少返回系统不可用状态
        metrics_lines = [
            format_prometheus_metric(
                "vigilops_up",
                0,
                {"error": str(e)[:50]},
                "VigilOps system availability",
                "gauge"
            )
        ]
    
    # 返回 Prometheus 文本格式
    response_text = "\n\n".join(metrics_lines) + "\n"
    return Response(content=response_text, media_type="text/plain; version=0.0.4; charset=utf-8")


@router.get("/prometheus/targets")
async def prometheus_targets(
    auth: Union[User, AgentToken] = Depends(_require_user_or_agent_token),
    db: AsyncSession = Depends(get_db),
):
    """
    Prometheus 服务发现目标端点
    
    返回当前监控的主机和服务列表，可用于 Prometheus 的 HTTP 服务发现
    格式兼容 Prometheus HTTP SD: https://prometheus.io/docs/prometheus/latest/configuration/configuration/#http_sd_config
    """
    targets = []
    
    try:
        # 获取所有主机作为目标
        hosts_query = select(Host).where(Host.status == 'online')
        hosts_result = await db.execute(hosts_query)
        hosts = hosts_result.scalars().all()
        
        for host in hosts:
            target = {
                "targets": [f"{host.ip_address}:9100"],  # 假设使用 node_exporter 默认端口
                "labels": {
                    "job": "node-exporter",
                    "instance": host.hostname,
                    "hostname": host.hostname,
                    "host_ip": host.ip_address,
                    "group": host.group_name or "default",
                    "__meta_vigilops_host_id": str(host.id),
                    "__meta_vigilops_host_status": host.status
                }
            }
            targets.append(target)
        
        # 获取所有服务作为目标
        services_query = select(Service)
        services_result = await db.execute(services_query)
        services = services_result.scalars().all()
        
        for service in services:
            if service.host and service.port:
                target = {
                    "targets": [f"{service.host}:{service.port}"],
                    "labels": {
                        "job": f"service-{service.type or 'unknown'}",
                        "instance": service.name,
                        "service_name": service.name,
                        "service_type": service.type or "unknown",
                        "host_ip": service.host,
                        "__meta_vigilops_service_id": str(service.id)
                    }
                }
                targets.append(target)
    
    except Exception as e:
        # 返回空目标列表，避免 Prometheus 抓取失败
        targets = []
    
    return targets