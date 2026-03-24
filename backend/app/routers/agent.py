"""
Agent数据上报路由模块 (Agent Data Reporting Router)

功能说明：提供Agent端向VigilOps平台上报各类监控数据的核心接口
核心职责：
  - Agent注册与主机信息管理（幂等性设计）
  - 心跳保活与在线状态维护
  - 主机性能指标收集和存储
  - 服务健康检查结果上报
  - 数据库性能指标监控
  - 批量日志采集与实时推送
  - 自动触发告警规则检查
依赖关系：依赖SQLAlchemy、Redis缓存、WebSocket广播、告警系统
API端点：POST /register, POST /heartbeat, POST /metrics, POST /services, POST /db-metrics, POST /logs

Author: VigilOps Team
"""
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import re
from app.core.agent_auth import verify_agent_token
from app.core.deps import get_current_user
from app.core.database import get_db
from app.core.redis import get_redis
from app.models.agent_token import AgentToken
from app.models.user import User
from app.models.host import Host
from app.models.host_metric import HostMetric
from app.models.service import Service, ServiceCheck
from app.schemas.service import ServiceCheckReport
from app.schemas.agent import (
    AgentRegisterRequest,
    AgentRegisterResponse,
    AgentHeartbeatRequest,
    AgentHeartbeatResponse,
    MetricReport,
)
from app.models.log_entry import LogEntry
from app.models.db_metric import MonitoredDatabase, DbMetric
from app.models.alert import AlertRule
from app.schemas.log_entry import LogBatchRequest, LogBatchResponse

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


def _auto_classify_service(name: str) -> str:
    """
    服务自动分类函数 (Automatic Service Classification)
    
    基于服务名称的关键词智能识别服务类型，用于服务拓扑图的层级展示。
    
    Args:
        name: 服务名称字符串
    Returns:
        str: 服务类别（middleware/business/infrastructure）
    分类规则：
        1. middleware - 数据库、缓存、消息队列等中间件
        2. infrastructure - Web服务器、代理、系统服务等基础设施
        3. business - 业务应用、API服务等（默认分类）
    """
    lower = name.lower()
    # 中间件层：数据库、缓存、消息队列、注册中心、搜索引擎等 (Middleware layer)
    if re.search(r'postgres|mysql|redis|rabbitmq|oracle|clickhouse|nacos|kafka|mongo|memcache|elasticsearch|mq', lower):
        return "middleware"
    # 基础设施层：Web服务器、代理、系统服务等 (Infrastructure layer)
    if re.search(r'nginx|httpd|apache|caddy|traefik|haproxy|keepalived|crond|ntpd|envoy', lower):
        return "infrastructure"
    # 业务应用层：后端、前端、应用服务等 (Business application layer)
    if re.search(r'backend|frontend|api|service|app|admin|job', lower):
        return "business"
    # 默认归为业务系统，确保所有服务都有分类 (Default to business to ensure all services are classified)
    return "business"


@router.post("/register", response_model=AgentRegisterResponse)
async def register_agent(
    body: AgentRegisterRequest,
    agent_token: AgentToken = Depends(verify_agent_token),
    db: AsyncSession = Depends(get_db),
):
    """
    Agent注册接口 (Agent Registration)
    
    Agent启动时向平台注册主机信息，支持幂等性操作确保重启安全。
    
    Args:
        body: Agent注册请求数据（主机名、IP、系统信息等）
        agent_token: 通过Token认证的Agent令牌对象
        db: 数据库会话依赖注入
    Returns:
        AgentRegisterResponse: 包含主机ID、状态、是否新建的响应
    流程：
        1. 基于hostname+token查找已有主机记录
        2. 存在则更新主机信息并设置在线状态
        3. 不存在则创建新主机记录
        4. 返回主机ID供后续API调用使用
    """
    # 查找是否已有相同hostname+token的主机（幂等性关键） (Find existing host by hostname+token for idempotency)
    result = await db.execute(
        select(Host).where(
            Host.hostname == body.hostname,
            Host.agent_token_id == agent_token.id,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        # 更新已有主机信息，支持Agent重启或配置变更 (Update existing host info for Agent restart or config changes)
        for field in ["ip_address", "display_name", "private_ip", "public_ip", "network_info", "os", "os_version", "arch", "cpu_cores", "memory_total_mb", "agent_version", "tags", "group_name"]:
            val = getattr(body, field, None)
            if val is not None:
                setattr(existing, field, val)
        existing.status = "online"  # 重新标记为在线状态
        existing.last_heartbeat = datetime.now(timezone.utc)  # 更新心跳时间
        await db.commit()
        await db.refresh(existing)
        return AgentRegisterResponse(host_id=existing.id, hostname=existing.hostname, status="online", created=False)

    # 创建新主机
    host = Host(
        hostname=body.hostname,
        display_name=body.display_name,
        ip_address=body.ip_address,
        private_ip=body.private_ip,
        public_ip=body.public_ip,
        network_info=body.network_info,
        os=body.os,
        os_version=body.os_version,
        arch=body.arch,
        cpu_cores=body.cpu_cores,
        memory_total_mb=body.memory_total_mb,
        agent_version=body.agent_version,
        tags=body.tags,
        group_name=body.group_name,
        agent_token_id=agent_token.id,
        status="online",
        last_heartbeat=datetime.now(timezone.utc),
    )
    db.add(host)
    await db.commit()
    await db.refresh(host)

    return AgentRegisterResponse(host_id=host.id, hostname=host.hostname, status="online", created=True)


@router.post("/heartbeat", response_model=AgentHeartbeatResponse)
async def heartbeat(
    body: AgentHeartbeatRequest,
    agent_token: AgentToken = Depends(verify_agent_token),
    db: AsyncSession = Depends(get_db),
):
    """
    Agent心跳保活接口 (Agent Heartbeat)
    
    定期接收Agent心跳，维护主机在线状态，支持离线检测机制。
    
    Args:
        body: 心跳请求数据（包含主机ID）
        agent_token: 通过Token认证的Agent令牌对象
        db: 数据库会话依赖注入
    Returns:
        AgentHeartbeatResponse: 包含状态确认和服务器时间
    流程：
        1. 更新数据库中主机的last_heartbeat时间
        2. 设置主机状态为online
        3. 写入Redis缓存，设置300秒过期时间
        4. 返回服务器当前时间用于时钟同步
    """
    now = datetime.now(timezone.utc)

    # 更新数据库中的心跳时间和在线状态 (Update heartbeat time and online status in database)
    result = await db.execute(select(Host).where(Host.id == body.host_id))
    host = result.scalar_one_or_none()
    if host:
        host.last_heartbeat = now
        host.status = "online"  # 确保主机标记为在线
        await db.commit()

    # 心跳 TTL 优先使用用户配置的 host_offline 规则 cooldown_seconds，fallback 到 300 秒
    # 但 TTL 必须至少是 Agent 心跳间隔（60s）的 2 倍，避免心跳还没来得及续期就被判定离线
    AGENT_HEARTBEAT_INTERVAL = 60
    rule_result = await db.execute(
        select(AlertRule).where(
            AlertRule.metric == "host_offline",
            AlertRule.is_enabled == True,  # noqa: E712
        ).limit(1)
    )
    offline_rule = rule_result.scalar_one_or_none()
    rule_cooldown = offline_rule.cooldown_seconds if (offline_rule and offline_rule.cooldown_seconds > 0) else 300
    heartbeat_ttl = max(rule_cooldown, AGENT_HEARTBEAT_INTERVAL * 2)

    # 写入Redis缓存，TTL 跟随 host_offline 规则配置
    redis = await get_redis()
    await redis.set(f"heartbeat:{body.host_id}", now.isoformat(), ex=heartbeat_ttl)

    return AgentHeartbeatResponse(status="ok", server_time=now)


@router.post("/metrics", status_code=201)
async def report_metrics(
    body: MetricReport,
    agent_token: AgentToken = Depends(verify_agent_token),
    db: AsyncSession = Depends(get_db),
):
    """
    主机性能指标上报接口 (Host Metrics Reporting)
    
    收集Agent上报的CPU、内存、磁盘、网络等系统性能指标。
    
    Args:
        body: 指标报告数据（CPU使用率、内存、磁盘、网络流量等）
        agent_token: 通过Token认证的Agent令牌对象
        db: 数据库会话依赖注入
    Returns:
        dict: 包含状态和指标记录ID的响应
    流程：
        1. 创建HostMetric记录持久化到数据库
        2. 缓存最新指标到Redis供仪表盘实时展示
        3. 设置600秒过期时间防止内存泄漏
    """
    import json as _json

    now = datetime.now(timezone.utc)
    recorded_at = body.timestamp or now

    # 持久化指标到数据库用于历史趋势分析 (Persist metrics to database for historical trend analysis)
    metric = HostMetric(
        host_id=body.host_id,
        cpu_percent=body.cpu_percent,  # CPU使用率
        cpu_load_1=body.cpu_load_1,    # 1分钟负载
        cpu_load_5=body.cpu_load_5,    # 5分钟负载
        cpu_load_15=body.cpu_load_15,  # 15分钟负载
        memory_used_mb=body.memory_used_mb,     # 内存使用量
        memory_percent=body.memory_percent,     # 内存使用率
        disk_used_mb=body.disk_used_mb,         # 磁盘已用空间
        disk_total_mb=body.disk_total_mb,       # 磁盘总空间
        disk_percent=body.disk_percent,         # 磁盘使用率
        net_bytes_sent=body.net_bytes_sent,     # 网络发送字节
        net_bytes_recv=body.net_bytes_recv,     # 网络接收字节
        net_send_rate_kb=body.net_send_rate_kb, # 发送速率
        net_recv_rate_kb=body.net_recv_rate_kb, # 接收速率
        net_packet_loss_rate=body.net_packet_loss_rate,  # 丢包率
        recorded_at=recorded_at,
    )
    db.add(metric)
    await db.commit()

    # 缓存最新指标到Redis，供仪表盘实时展示使用 (Cache latest metrics to Redis for real-time dashboard display)
    redis = await get_redis()
    latest = body.model_dump(exclude={"host_id", "timestamp"}, exclude_none=True)
    latest["recorded_at"] = recorded_at.isoformat()
    await redis.set(f"metrics:latest:{body.host_id}", _json.dumps(latest), ex=600)  # 10分钟过期

    # 存储指标历史到 Redis（用于精确持续时间判断）
    # 保留最近 20 个数据点（5 分钟历史，15秒间隔）
    try:
        history_key = f"metrics:history:{body.host_id}"
        history_entry = {
            "cpu_percent": body.cpu_percent,
            "memory_percent": body.memory_percent,
            "disk_percent": body.disk_percent,
            "cpu_load_1": body.cpu_load_1,
            "cpu_load_5": body.cpu_load_5,
            "cpu_load_15": body.cpu_load_15,
            "ts": recorded_at.isoformat()
        }

        # 获取现有历史
        existing_history = await redis.get(history_key)
        if existing_history:
            history = _json.loads(existing_history)
        else:
            history = []

        # 添加新数据点
        history.append(history_entry)

        # 只保留最近 20 个数据点
        history = history[-20:]

        # 存储回 Redis，TTL 10 分钟
        await redis.set(history_key, _json.dumps(history), ex=600)
    except Exception as e:
        # 不影响主流程，仅记录警告
        import logging
        logging.getLogger(__name__).warning(f"Failed to update metrics history: {e}")

    return {"status": "ok", "metric_id": metric.id}


@router.post("/services/register", status_code=200)
async def register_service(
    body: dict,
    agent_token: AgentToken = Depends(verify_agent_token),
    db: AsyncSession = Depends(get_db),
):
    """
    服务注册接口 (Service Registration)
    
    注册待监控的服务，支持幂等性操作，自动分类服务类型。
    
    Args:
        body: 服务注册数据（名称、目标URL、类型、检查间隔等）
        agent_token: 通过Token认证的Agent令牌对象
        db: 数据库会话依赖注入
    Returns:
        dict: 包含服务ID和是否新建的响应
    流程：
        1. 根据name+target查找已有服务
        2. 存在则返回服务ID，不存在则创建新服务
        3. 基于服务名自动分类（middleware/business/infrastructure）
        4. 返回服务ID供健康检查使用
    """
    name = body.get("name", "")
    target = body.get("target", body.get("url", ""))
    svc_type = body.get("type", "http")
    host_id = body.get("host_id")
    check_interval = body.get("check_interval", 60)
    timeout = body.get("timeout", 10)

    # 查找已有服务（按 host_id + name 唯一确定，target 可能因发现机制变化）
    result = await db.execute(
        select(Service).where(Service.host_id == host_id, Service.name == name)
    )
    existing = result.scalar_one_or_none()
    if existing:
        # target 有变化时同步更新，避免旧 target 残留
        if existing.target != target:
            existing.target = target
            existing.type = svc_type
            await db.commit()
        return {"service_id": existing.id, "created": False}

    # 自动分类
    category = _auto_classify_service(name)

    svc = Service(
        name=name, type=svc_type, target=target, host_id=host_id,
        check_interval=check_interval, timeout=timeout,
        category=category,
    )
    db.add(svc)
    await db.commit()
    await db.refresh(svc)
    return {"service_id": svc.id, "created": True}


@router.post("/services", status_code=201)
async def report_service_check(
    body: ServiceCheckReport,
    agent_token: AgentToken = Depends(verify_agent_token),
    db: AsyncSession = Depends(get_db),
):
    """
    服务健康检查结果上报接口 (Service Health Check Reporting)
    
    接收Agent执行的服务健康检查结果，更新服务状态。
    
    Args:
        body: 健康检查报告（服务ID、状态、响应时间、错误信息等）
        agent_token: 通过Token认证的Agent令牌对象
        db: 数据库会话依赖注入
    Returns:
        dict: 包含状态和检查记录ID的响应
    流程：
        1. 创建ServiceCheck记录保存检查详情
        2. 同步更新Service表中的当前状态
        3. 供服务列表和拓扑图显示使用
    """
    now = datetime.now(timezone.utc)

    check = ServiceCheck(
        service_id=body.service_id,
        status=body.status,
        response_time_ms=body.response_time_ms,
        status_code=body.status_code,
        error=body.error,
        checked_at=body.checked_at or now,
    )
    db.add(check)

    # 同步更新服务状态
    result = await db.execute(select(Service).where(Service.id == body.service_id))
    service = result.scalar_one_or_none()
    if service:
        service.status = body.status

    await db.commit()
    return {"status": "ok", "check_id": check.id}


@router.post("/db-metrics", status_code=201)
async def report_db_metrics(
    body: dict,
    agent_token: AgentToken = Depends(verify_agent_token),
    db: AsyncSession = Depends(get_db),
):
    """
    数据库性能指标上报接口 (Database Metrics Reporting)
    
    收集数据库连接数、查询性能、存储使用等关键指标，自动触发告警检查。
    
    Args:
        body: 数据库指标数据（连接数、慢查询、QPS、存储等）
        agent_token: 通过Token认证的Agent令牌对象
        db: 数据库会话依赖注入
    Returns:
        dict: 包含状态、数据库ID和指标记录ID
    Raises:
        HTTPException 400: 缺少必需的host_id或db_name参数
    流程：
        1. 根据host_id+db_name查找或创建MonitoredDatabase记录
        2. 创建DbMetric记录保存指标详情
        3. 检查是否触发数据库指标告警规则
        4. 返回数据库ID和指标记录ID
    """
    now = datetime.now(timezone.utc)
    host_id = body.get("host_id")
    db_name = body.get("db_name", "")
    db_type = body.get("db_type", "postgres")

    if not host_id or not db_name:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="host_id and db_name required")

    # 查找或创建被监控数据库记录
    result = await db.execute(
        select(MonitoredDatabase).where(
            MonitoredDatabase.host_id == host_id,
            MonitoredDatabase.name == db_name,
        )
    )
    monitored_db = result.scalar_one_or_none()
    if not monitored_db:
        monitored_db = MonitoredDatabase(
            host_id=host_id,
            name=db_name,
            db_type=db_type,
            status="healthy",
        )
        db.add(monitored_db)
        await db.flush()
    else:
        monitored_db.updated_at = now
        monitored_db.status = "healthy"

    # 更新 Oracle 慢查询详情
    slow_queries_detail = body.get("slow_queries_detail")
    if slow_queries_detail is not None:
        monitored_db.slow_queries_detail = slow_queries_detail

    # 写入指标记录
    metric = DbMetric(
        database_id=monitored_db.id,
        connections_total=body.get("connections_total"),
        connections_active=body.get("connections_active"),
        database_size_mb=body.get("database_size_mb"),
        slow_queries=body.get("slow_queries"),
        tables_count=body.get("tables_count"),
        transactions_committed=body.get("transactions_committed"),
        transactions_rolled_back=body.get("transactions_rolled_back"),
        qps=body.get("qps"),
        tablespace_used_pct=body.get("tablespace_used_pct"),
        recorded_at=now,
    )
    db.add(metric)
    await db.commit()

    # 检查数据库指标告警规则
    try:
        await _check_db_metric_alerts(monitored_db.id, body, db)
    except Exception:
        pass

    return {"status": "ok", "database_id": monitored_db.id, "metric_id": metric.id}


async def _check_db_metric_alerts(database_id: int, body: dict, db: AsyncSession):
    """
    数据库指标告警检查 (Database Metric Alert Check)
    
    对比数据库指标值与已配置的告警规则，自动创建告警记录。
    
    Args:
        database_id: 数据库记录ID
        body: 数据库指标数据字典
        db: 数据库会话对象
    流程：
        1. 查询所有启用的db_metric类型告警规则
        2. 遍历规则，检查指标值是否超过阈值
        3. 支持>, >=, <, <=, ==, != 比较操作符
        4. 触发条件时创建Alert记录
    """
    from app.models.alert import AlertRule, Alert
    import operator as op_module

    result = await db.execute(
        select(AlertRule).where(
            AlertRule.rule_type == "db_metric",
            AlertRule.is_enabled == True,
        )
    )
    rules = result.scalars().all()

    ops = {">": op_module.gt, ">=": op_module.ge, "<": op_module.lt, "<=": op_module.le, "==": op_module.eq, "!=": op_module.ne}

    for rule in rules:
        if rule.db_id and rule.db_id != database_id:
            continue
        metric_name = rule.db_metric_name
        if not metric_name:
            continue
        value = body.get(metric_name)
        if value is None:
            continue
        compare = ops.get(rule.operator, op_module.gt)
        if compare(float(value), rule.threshold):
            alert = Alert(
                rule_id=rule.id,
                host_id=body.get("host_id"),
                severity=rule.severity,
                status="firing",
                title=f"数据库告警: {rule.name}",
                message=f"{metric_name} = {value} {rule.operator} {rule.threshold}",
                metric_value=float(value),
                threshold=rule.threshold,
            )
            db.add(alert)

    await db.commit()


@router.post("/logs", response_model=LogBatchResponse, status_code=201)
async def ingest_logs(
    body: LogBatchRequest,
    agent_token: AgentToken = Depends(verify_agent_token),
    db: AsyncSession = Depends(get_db),
):
    """
    批量日志采集接口 (Bulk Log Ingestion)
    
    接收Agent批量上传的日志数据，支持实时推送和告警检测。
    
    Args:
        body: 批量日志请求（包含日志条目列表）
        agent_token: 通过Token认证的Agent令牌对象
        db: 数据库会话依赖注入
    Returns:
        LogBatchResponse: 包含接收日志数量的响应
    流程：
        1. 批量插入日志条目到PostgreSQL
        2. 广播到WebSocket订阅者实现实时日志流
        3. 检查日志内容是否匹配关键字告警规则
        4. 返回成功接收的日志条目数量
    """
    from sqlalchemy.dialects.postgresql import insert
    from app.routers.logs import log_broadcaster

    if not body.logs:
        return LogBatchResponse(received=0)

    rows = [item.model_dump() for item in body.logs]
    await db.execute(insert(LogEntry), rows)
    await db.commit()

    # 广播到 WebSocket 实时日志订阅者
    broadcast_entries = []
    for item in body.logs:
        entry = item.model_dump()
        entry["timestamp"] = entry["timestamp"].isoformat()
        broadcast_entries.append(entry)
    await log_broadcaster.publish(broadcast_entries)

    # 检查日志关键字告警规则
    try:
        await _check_log_keyword_alerts(body.logs, db)
    except Exception:
        pass  # 不影响日志写入

    return LogBatchResponse(received=len(rows))


async def _check_log_keyword_alerts(logs: list, db: AsyncSession):
    """
    日志关键字告警检查 (Log Keyword Alert Check)

    扫描日志内容，匹配关键字告警规则，自动创建告警记录。
    包含去重逻辑：同一规则在60秒内不重复创建告警。

    Args:
        logs: 日志条目对象列表
        db: 数据库会话对象
    流程：
        1. 查询所有启用的log_keyword类型告警规则
        2. 遍历日志条目，检查message字段是否包含关键字
        3. 支持按日志级别和服务名过滤匹配范围
        4. 去重检查：同一规则60秒内已有firing告警则跳过
        5. 匹配成功时创建Alert记录，截取前200字符
    """
    from app.models.alert import AlertRule, Alert
    from datetime import timedelta
    from app.services.suppression_service import SuppressionService

    result = await db.execute(
        select(AlertRule).where(
            AlertRule.rule_type == "log_keyword",
            AlertRule.is_enabled == True,
        )
    )
    rules = result.scalars().all()
    if not rules:
        return

    # 获取被屏蔽的 host_id，跳过这些主机的日志告警
    suppressed_host_ids = await SuppressionService.get_suppressed_host_ids_for_logs(db)

    now = datetime.now(timezone.utc)
    dedup_window = now - timedelta(seconds=60)

    # 预查询：获取所有相关规则在去重窗口内已有的firing告警
    rule_ids = [r.id for r in rules]
    existing_result = await db.execute(
        select(Alert.rule_id, Alert.host_id).where(
            Alert.rule_id.in_(rule_ids),
            Alert.status == "firing",
            Alert.fired_at >= dedup_window,
        )
    )
    existing_alerts = {(row.rule_id, row.host_id) for row in existing_result}

    for log_item in logs:
        # 跳过被屏蔽主机的日志
        if log_item.host_id and log_item.host_id in suppressed_host_ids:
            continue

        msg = (log_item.message or "").lower()
        level = (log_item.level or "").upper()
        svc = log_item.service or ""

        for rule in rules:
            keyword = (rule.log_keyword or "").lower()
            if not keyword or keyword not in msg:
                continue
            if rule.log_level and rule.log_level.upper() != level:
                continue
            if rule.log_service and rule.log_service != svc:
                continue

            # 去重：同一规则+主机在60秒内已有firing告警则跳过
            dedup_key = (rule.id, log_item.host_id)
            if dedup_key in existing_alerts:
                continue

            alert = Alert(
                rule_id=rule.id,
                host_id=log_item.host_id,
                severity=rule.severity,
                status="firing",
                title=f"日志关键字告警: {rule.name}",
                message=f"匹配关键字 '{rule.log_keyword}' in: {log_item.message[:200]}",
            )
            db.add(alert)
            # 将新创建的告警加入去重集合，避免同一批次重复
            existing_alerts.add(dedup_key)

    await db.commit()


# =============================================================================
# Agent WebSocket 更新通知
# =============================================================================

from fastapi import WebSocket, WebSocketDisconnect
from datetime import datetime
import asyncio
import hashlib
import hmac
import logging
import json

logger = logging.getLogger(__name__)

# 本进程内持有的 WebSocket 连接（每个 worker 各自维护）
agent_ws_clients: dict = {}  # host_id -> WebSocket

# Redis Pub/Sub channel 前缀，用于跨 worker 广播更新指令
AGENT_UPDATE_CHANNEL = "agent_update:"
# Redis key 前缀，记录哪些 host 当前有 WS 连接（跨 worker 可见）
AGENT_WS_ONLINE_KEY = "agent_ws_online"


async def _redis_pubsub_listener(host_id: int, websocket: WebSocket):
    """
    订阅 Redis channel，将收到的更新指令转发给本进程持有的 WebSocket。
    同时监听 cmd_to_agent channel，将命令下发到 Agent。
    每个 WebSocket 连接对应一个独立的订阅协程。
    """
    redis = await get_redis()
    update_channel = f"{AGENT_UPDATE_CHANNEL}{host_id}"
    cmd_channel = f"cmd_to_agent:{host_id}"
    pubsub = redis.pubsub()
    await pubsub.subscribe(update_channel, cmd_channel)
    logger.info(f"Subscribed to Redis channels: {update_channel}, {cmd_channel}")
    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            if host_id not in agent_ws_clients:
                break
            try:
                payload = json.loads(message["data"])
                await websocket.send_json(payload)
                logger.info(f"Forwarded message type={payload.get('type')} to host_id={host_id}")
            except Exception as e:
                logger.warning(f"Failed to forward message to host_id={host_id}: {e}")
                break
    except asyncio.CancelledError:
        pass
    finally:
        await pubsub.unsubscribe(update_channel, cmd_channel)
        await pubsub.close()


# ====== WebSocket 连接端点 ======
@router.websocket("/ws/{host_id}")
async def agent_websocket(
    websocket: WebSocket,
    host_id: int,
    token: str | None = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Agent WebSocket 连接端点

    用于实时通信，包括：
    - 更新通知推送（通过 Redis Pub/Sub 跨 worker 广播）
    - 心跳检测

    认证方式：
    1. Authorization header (推荐)
    2. 查询参数 ?token=xxx (备用)
    """
    # 先接受连接
    await websocket.accept()

    # 获取 token - 优先从 header，其次从查询参数
    auth_header = websocket.headers.get("authorization", "")
    raw_token = None

    if auth_header.startswith("Bearer "):
        raw_token = auth_header[7:]
    elif token:
        raw_token = token

    if not raw_token:
        logger.warning(f"WebSocket rejected: missing token for host_id={host_id}")
        await websocket.close(code=1008, reason="Missing token")
        return

    from app.core.config import settings
    token_hash = hmac.new(
        settings.agent_token_hmac_key.encode(),
        raw_token.encode(),
        hashlib.sha256,
    ).hexdigest()

    result = await db.execute(
        select(AgentToken).where(
            AgentToken.token_hash == token_hash,
            AgentToken.is_active == True,
        )
    )
    agent_token = result.scalar_one_or_none()
    if agent_token is None:
        logger.warning(f"WebSocket rejected: invalid token for host_id={host_id}")
        await websocket.close(code=1008, reason="Invalid token")
        return

    # 认证成功，存储本进程内的连接，并在 Redis 中标记在线
    agent_ws_clients[host_id] = websocket
    redis = await get_redis()
    await redis.sadd(AGENT_WS_ONLINE_KEY, host_id)
    logger.info(f"Agent WebSocket connected: host_id={host_id}")

    # 启动 Redis Pub/Sub 监听协程（跨 worker 接收更新指令）
    pubsub_task = asyncio.create_task(_redis_pubsub_listener(host_id, websocket))

    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
            except asyncio.TimeoutError:
                continue
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                elif msg.get("type") in ("command_output", "command_result"):
                    # 将命令执行结果路由到对应的 OpsAgentLoop（通过 Redis Pub/Sub）
                    await _route_command_result(host_id, msg)
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        logger.info(f"Agent WebSocket disconnected: host_id={host_id}")
    except Exception as e:
        logger.error(f"WebSocket error for host_id={host_id}: {e}", exc_info=True)
    finally:
        pubsub_task.cancel()
        if host_id in agent_ws_clients:
            del agent_ws_clients[host_id]
        # 从 Redis 在线集合中移除
        try:
            await redis.srem(AGENT_WS_ONLINE_KEY, host_id)
        except Exception:
            pass


# ====== 触发更新 API ======
@router.get("/ws-status")
async def get_ws_status(
    current_user: User = Depends(get_current_user)
):
    """获取当前 WebSocket 连接状态（跨所有 worker）"""
    redis = await get_redis()
    online_ids = await redis.smembers(AGENT_WS_ONLINE_KEY)
    connected_hosts = [int(h) for h in online_ids]
    return {
        "status": "ok",
        "connected_hosts": connected_hosts,
        "total_connections": len(connected_hosts)
    }


@router.post("/trigger-update/{host_id}")
async def trigger_agent_update(
    host_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    触发 Agent 更新。

    通过 Redis Pub/Sub 广播更新指令，持有该 Agent WebSocket 连接的
    worker 会收到并转发，解决多 worker 下连接不在同一进程的问题。
    """
    redis = await get_redis()

    # 检查 Agent 是否在线（跨 worker 可见）
    is_online = await redis.sismember(AGENT_WS_ONLINE_KEY, host_id)
    if not is_online:
        return {"status": "error", "message": "Agent not connected via WebSocket"}

    try:
        payload = json.dumps({
            "type": "update",
            "action": "upgrade",
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        # 发布到对应 channel，持有连接的 worker 会收到并转发
        receivers = await redis.publish(f"{AGENT_UPDATE_CHANNEL}{host_id}", payload)
        logger.info(f"Update triggered for host_id={host_id}, receivers={receivers}")
        return {"status": "ok", "message": "Update triggered successfully"}
    except Exception as e:
        logger.error(f"Failed to trigger update for host_id={host_id}: {e}")
        return {"status": "error", "message": str(e)}

# 添加安装脚本端点
from .agent_install_endpoint import add_install_endpoint
add_install_endpoint(router)


async def _route_command_result(host_id: int, msg: dict):
    """
    将 Agent 回传的命令输出/结果通过 Redis Pub/Sub 路由到对应的 OpsAgentLoop。
    同时通过 ops_ws channel 推送到前端 WebSocket。
    """
    request_id = msg.get("request_id")
    if not request_id:
        return

    redis = await get_redis()
    msg_type = msg.get("type")

    if msg_type == "command_output":
        # 推送流式输出到前端（通过 ops_ws channel，需要 session_id）
        # 通过 request_id 查找 session_id（存储在 Redis 中）
        session_id = await redis.get(f"cmd_req_session:{request_id}")
        if session_id:
            if isinstance(session_id, bytes):
                session_id = session_id.decode()
            from app.services.ops_agent_loop import OPS_WS_CHANNEL
            await redis.publish(
                f"{OPS_WS_CHANNEL}{session_id}",
                json.dumps({
                    "event": "command_output",
                    "message_id": request_id,
                    "stdout": msg.get("stdout", ""),
                    "stderr": msg.get("stderr", ""),
                }),
            )

    elif msg_type == "command_result":
        # 查找 session_id
        session_id = await redis.get(f"cmd_req_session:{request_id}")
        if session_id:
            if isinstance(session_id, bytes):
                session_id = session_id.decode()
            from app.services.ops_agent_loop import CMD_RESULT_CHANNEL, OPS_WS_CHANNEL
            # 通知 OpsAgentLoop（_wait_command_result 正在监听此 channel）
            await redis.publish(
                f"{CMD_RESULT_CHANNEL}{session_id}",
                json.dumps(msg),
            )
            # 同时推送到前端
            await redis.publish(
                f"{OPS_WS_CHANNEL}{session_id}",
                json.dumps({
                    "event": "command_result",
                    "message_id": request_id,
                    "exit_code": msg.get("exit_code", -1),
                    "duration_ms": msg.get("duration_ms", 0),
                }),
            )
            # 清理 Redis 中的映射
            await redis.delete(f"cmd_req_session:{request_id}")
