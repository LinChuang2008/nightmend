"""
仪表盘 WebSocket 实时推送模块 (Dashboard WebSocket Real-time Push Module)

功能说明：提供仪表盘数据的实时 WebSocket 推送服务，保持前端数据的实时性
核心职责：
  - 仪表盘数据的周期性收集和聚合（主机、服务、告警、日志）
  - WebSocket 连接管理和实时数据推送
  - 系统健康评分计算和趋势分析
  - 多维度系统状态监控数据汇总
  - 异常处理和连接状态管理
依赖关系：依赖 Host、Service、Alert、LogEntry、HostMetric 等数据模型
WebSocket端点：/api/v1/ws/dashboard

Push Frequency: 每30秒推送一次更新数据
Data Categories:
  - 主机状态统计（在线/离线数量）
  - 服务状态分布（运行/异常服务数量）
  - 告警活动统计（最近1小时告警数、活跃告警数）
  - 系统资源使用情况（CPU、内存、磁盘平均使用率）
  - 综合健康评分（0-100分，基于多指标加权计算）
  - 错误日志统计（最近1小时错误级别日志数量）

Author: NightMend Team
"""
import asyncio
import json
import logging
import math
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select, and_, func

from app.core.database import async_session
from app.models.host import Host
from app.models.host_metric import HostMetric
from app.models.service import Service
from app.models.alert import Alert
from app.models.log_entry import LogEntry
from app.models.notification import NotificationChannel

logger = logging.getLogger(__name__)

router = APIRouter()

# 推送间隔（秒）
PUSH_INTERVAL = 30


def _resource_penalty(value: float | None, *, warning: float, high: float, critical: float, max_points: int) -> int:
    """对单项资源使用率做分段扣分，避免中低负载被过度惩罚。"""
    if value is None or value <= warning:
        return 0

    if value <= high:
        penalty = (value - warning) * 0.2
    elif value <= critical:
        penalty = (high - warning) * 0.2 + (value - high) * 0.5
    else:
        penalty = (high - warning) * 0.2 + (critical - high) * 0.5 + (value - critical) * 0.9

    return min(max_points, max(1, round(penalty)))


def _ratio_penalty(problem_count: int, total: int, *, max_points: int, min_points_if_any: int = 0) -> int:
    """按异常占比扣分，避免节点数量变化导致评分畸变。"""
    if problem_count <= 0 or total <= 0:
        return 0

    penalty = round((problem_count / total) * max_points)
    return min(max_points, max(min_points_if_any, penalty))


def _build_health_breakdown(
    *,
    host_total: int,
    host_offline: int,
    svc_total: int,
    svc_down: int,
    firing_count: int,
    active_alert_total: int,
    error_log_count: int,
    avg_cpu: float | None,
    avg_mem: float | None,
    avg_disk: float | None,
    metrics_count: int,
) -> list[dict]:
    """构建健康评分扣分项。points 为负数，便于前端直接展示。"""
    deductions: list[dict] = []

    offline_penalty = _ratio_penalty(host_offline, host_total, max_points=30, min_points_if_any=8)
    if offline_penalty:
        deductions.append({"reason": f"离线主机 {host_offline}/{host_total}", "points": -offline_penalty})

    svc_penalty = _ratio_penalty(svc_down, svc_total, max_points=24, min_points_if_any=6)
    if svc_penalty:
        deductions.append({"reason": f"异常服务 {svc_down}/{svc_total}", "points": -svc_penalty})

    if firing_count > 0:
        firing_penalty = min(20, 4 + (firing_count - 1) * 4)
        deductions.append({"reason": f"触发中告警 {firing_count} 条", "points": -firing_penalty})
    elif active_alert_total > 0:
        acknowledged_penalty = min(8, 2 + active_alert_total)
        deductions.append({"reason": f"未关闭告警 {active_alert_total} 条", "points": -acknowledged_penalty})

    if error_log_count > 0:
        error_penalty = min(12, 2 + math.ceil(error_log_count / 10) * 2)
        deductions.append({"reason": f"近1小时错误日志 {error_log_count} 条", "points": -error_penalty})

    cpu_penalty = _resource_penalty(avg_cpu, warning=60, high=75, critical=90, max_points=16)
    if cpu_penalty:
        deductions.append({"reason": f"平均 CPU {avg_cpu:.1f}%", "points": -cpu_penalty})

    mem_penalty = _resource_penalty(avg_mem, warning=65, high=80, critical=92, max_points=18)
    if mem_penalty:
        deductions.append({"reason": f"平均内存 {avg_mem:.1f}%", "points": -mem_penalty})

    disk_penalty = _resource_penalty(avg_disk, warning=70, high=85, critical=95, max_points=14)
    if disk_penalty:
        deductions.append({"reason": f"平均磁盘 {avg_disk:.1f}%", "points": -disk_penalty})

    if host_total > 0 and metrics_count == 0:
        deductions.append({"reason": "最近1小时无资源指标上报", "points": -10})

    return sorted(deductions, key=lambda item: abs(item["points"]), reverse=True)


def _calc_health_score_from_breakdown(breakdown: list[dict]) -> int:
    total_penalty = sum(abs(int(item.get("points", 0))) for item in breakdown)
    return max(0, min(100, 100 - total_penalty))


async def _collect_dashboard_data() -> dict:
    """
    收集仪表盘汇总数据 (Collect Dashboard Summary Data)
    
    从多个数据源聚合系统监控数据，生成仪表盘所需的完整统计信息。
    数据收集包括主机状态、服务健康度、告警活动和资源使用情况。
    
    Returns:
        dict: 包含完整仪表盘数据的字典对象
        
    Data Collection Scope:
        - 主机状态：总数、在线数、离线数
        - 服务状态：总数、正常数、异常数
        - 告警活动：最近1小时告警数、当前活跃告警数
        - 资源使用：CPU、内存、磁盘的平均使用率
        - 系统健康：基于多指标的综合健康评分
        - 日志统计：最近1小时错误级别日志数量
        
    Performance Notes:
        - 使用独立数据库会话，避免与主应用会话冲突
        - 优化查询使用聚合函数，减少数据传输
        - 仅查询最近1小时数据，控制查询范围
    """
    async with async_session() as db:
        # 设置时间范围：最近1小时的数据
        since = datetime.now(timezone.utc) - timedelta(hours=1)

        # === 主机统计 (Host Statistics) ===
        host_total = (await db.execute(select(func.count(Host.id)))).scalar() or 0
        host_online = (await db.execute(
            select(func.count(Host.id)).where(Host.status == "online")
        )).scalar() or 0

        # === 服务统计 (Service Statistics) ===
        # 总的活跃服务数（排除已禁用的服务）
        svc_total = (await db.execute(
            select(func.count(Service.id)).where(Service.is_active == True)
        )).scalar() or 0
        
        # 运行正常的服务数
        svc_up = (await db.execute(
            select(func.count(Service.id)).where(
                and_(Service.is_active == True, Service.status == "up")
            )
        )).scalar() or 0
        
        # 异常的服务数
        svc_down = (await db.execute(
            select(func.count(Service.id)).where(
                and_(Service.is_active == True, Service.status == "down")
            )
        )).scalar() or 0

        # === 告警统计 (Alert Statistics) ===
        # 最近1小时新产生的告警数
        recent_alert_count = (await db.execute(
            select(func.count(Alert.id)).where(Alert.fired_at >= since)
        )).scalar() or 0

        # 当前正在触发的告警数
        firing_count = (await db.execute(
            select(func.count(Alert.id)).where(Alert.status == "firing")
        )).scalar() or 0

        # 所有活跃告警总数（firing + acknowledged）
        active_alert_total = (await db.execute(
            select(func.count(Alert.id)).where(Alert.status.in_(["firing", "acknowledged"]))
        )).scalar() or 0

        # === 通知渠道状态 (Notification Channel Status) ===
        enabled_channels = (await db.execute(
            select(func.count(NotificationChannel.id)).where(NotificationChannel.is_enabled == True)
        )).scalar() or 0

        # === 日志统计 (Log Statistics) ===
        # 最近1小时的错误级别日志数（ERROR/CRITICAL/FATAL），排除被屏蔽主机
        from app.services.suppression_service import SuppressionService
        suppressed_host_ids = await SuppressionService.get_suppressed_host_ids_for_logs(db)

        log_count_query = select(func.count(LogEntry.id)).where(and_(
            LogEntry.timestamp >= since,
            LogEntry.level.in_(["ERROR", "CRITICAL", "FATAL"]),
        ))
        if suppressed_host_ids:
            log_count_query = log_count_query.where(
                LogEntry.host_id.not_in(suppressed_host_ids)
            )
        error_log_count = (await db.execute(log_count_query)).scalar() or 0

        # === 资源使用率统计 (Resource Usage Statistics) ===
        # 构建子查询：获取每台主机在时间范围内的最新指标记录时间
        latest_metric_subq = (
            select(
                HostMetric.host_id,
                func.max(HostMetric.recorded_at).label("max_recorded_at"),
            )
            .where(HostMetric.recorded_at >= since)
            .group_by(HostMetric.host_id)
            .subquery()
        )

        # 查询每台主机的最新指标数据
        metric_q = (
            select(HostMetric)
            .join(latest_metric_subq, and_(
                HostMetric.host_id == latest_metric_subq.c.host_id,
                HostMetric.recorded_at == latest_metric_subq.c.max_recorded_at,
            ))
        )
        metric_result = await db.execute(metric_q)
        metrics = metric_result.scalars().all()

        # 计算所有主机的平均资源使用率
        avg_cpu = None
        avg_mem = None
        avg_disk = None
        if metrics:
            # 过滤掉空值并计算平均值
            cpu_vals = [m.cpu_percent for m in metrics if m.cpu_percent is not None]
            mem_vals = [m.memory_percent for m in metrics if m.memory_percent is not None]
            disk_vals = [m.disk_percent for m in metrics if m.disk_percent is not None]
            
            if cpu_vals:
                avg_cpu = round(sum(cpu_vals) / len(cpu_vals), 1)
            if mem_vals:
                avg_mem = round(sum(mem_vals) / len(mem_vals), 1)
            if disk_vals:
                avg_disk = round(sum(disk_vals) / len(disk_vals), 1)

        # === 系统健康评分计算 (Health Score Calculation) ===
        host_offline = host_total - host_online
        health_breakdown = _build_health_breakdown(
            host_total=host_total,
            host_offline=host_offline,
            svc_total=svc_total,
            svc_down=svc_down,
            firing_count=firing_count,
            active_alert_total=active_alert_total,
            error_log_count=error_log_count,
            avg_cpu=avg_cpu,
            avg_mem=avg_mem,
            avg_disk=avg_disk,
            metrics_count=len(metrics),
        )
        health_score = _calc_health_score_from_breakdown(health_breakdown)

        # 构建完整的仪表盘数据响应
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),  # 数据收集时间
            "hosts": {
                "total": host_total,
                "online": host_online,
                "offline": host_offline,
            },
            "services": {
                "total": svc_total,
                "up": svc_up,
                "down": svc_down,
            },
            "alerts": {
                "total": active_alert_total,  # 所有活跃告警（firing + acknowledged）
                "firing": firing_count,       # 当前触发中的告警
            },
            "recent_1h": {
                "alert_count": recent_alert_count,  # 最近1小时新告警数
                "error_log_count": error_log_count,  # 最近1小时错误日志数
            },
            "avg_usage": {
                "cpu_percent": avg_cpu,      # 平均CPU使用率
                "memory_percent": avg_mem,   # 平均内存使用率
                "disk_percent": avg_disk,    # 平均磁盘使用率
            },
            "health_score": health_score,    # 综合健康评分(0-100)
            "health_breakdown": health_breakdown,
            "notification_setup": {
                "configured": enabled_channels > 0,
                "enabled_count": enabled_channels,
            },
        }


def _calc_health_score(
    avg_cpu: float | None,
    avg_mem: float | None,
    avg_disk: float | None,
    svc_down: int,
) -> int:
    """
    计算系统综合健康评分 (Calculate System Health Score)
    
    基于多个关键指标计算系统的整体健康状况，评分范围为 0-100 分。
    该评分用于快速判断系统运行状态，帮助运维人员识别系统问题。
    
    Args:
        avg_cpu: 平均CPU使用率百分比（0-100）
        avg_mem: 平均内存使用率百分比（0-100）
        avg_disk: 平均磁盘使用率百分比（0-100）
        svc_down: 异常服务数量
        
    Returns:
        int: 健康评分，范围 0-100（100分表示系统完全健康）
        
    Algorithm:
        健康评分 = 100 - (资源使用惩罚 + 服务异常惩罚)
        
        资源使用惩罚 = CPU权重×CPU使用率 + 内存权重×内存使用率 + 磁盘权重×磁盘使用率
        - CPU权重: 0.3 （CPU是性能的关键指标）
        - 内存权重: 0.3 （内存不足会导致系统不稳定）
        - 磁盘权重: 0.2 （磁盘使用率影响相对较小）
        
        服务异常惩罚 = 异常服务数 × 5 （每个异常服务扣5分）
        
    Scoring Guide:
        - 90-100分: 系统健康，资源充足，无服务异常
        - 80-89分: 系统良好，可能有轻微资源压力
        - 70-79分: 系统一般，需要关注资源使用或服务状态
        - 60-69分: 系统告警，资源紧张或多个服务异常
        - 0-59分: 系统危险，需要立即处理
        
    Examples:
        - CPU 20%, 内存 30%, 磁盘 40%, 0个异常服务 → 评分 82
        - CPU 80%, 内存 70%, 磁盘 60%, 2个异常服务 → 评分 20
        - CPU 50%, 内存 null, 磁盘 60%, 1个异常服务 → 评分 68
    """
    breakdown = _build_health_breakdown(
        host_total=0,
        host_offline=0,
        svc_total=max(svc_down, 1) if svc_down else 0,
        svc_down=svc_down,
        firing_count=0,
        active_alert_total=0,
        error_log_count=0,
        avg_cpu=avg_cpu,
        avg_mem=avg_mem,
        avg_disk=avg_disk,
        metrics_count=1 if any(v is not None for v in (avg_cpu, avg_mem, avg_disk)) else 0,
    )
    return _calc_health_score_from_breakdown(breakdown)


@router.websocket("/api/v1/ws/dashboard")
async def dashboard_ws(websocket: WebSocket):
    """
    仪表盘 WebSocket 实时推送端点 (Dashboard WebSocket Real-time Push Endpoint)
    需要通过 query 参数 token 或 cookie 传递 JWT 进行认证。
    """
    # 安全: WebSocket 连接认证
    from app.core.ws_auth import validate_ws_token
    payload = await validate_ws_token(websocket)
    if payload is None:
        await websocket.close(code=4401, reason="Authentication required")
        return

    await websocket.accept()  # 认证通过，接受 WebSocket 连接
    logger.info("仪表盘 WebSocket 客户端已连接")
    
    try:
        # 进入数据推送循环
        while True:
            try:
                # 收集最新的仪表盘数据
                data = await _collect_dashboard_data()

                # 将数据序列化为 JSON 并推送给客户端
                # ensure_ascii=False 支持中文字符正确显示
                # 添加 5 秒超时，防止慢消费者阻塞推送循环
                await asyncio.wait_for(
                    websocket.send_text(json.dumps(data, ensure_ascii=False)),
                    timeout=5.0,
                )

            except asyncio.TimeoutError:
                # 发送超时，客户端消费过慢，显式关闭连接防止资源泄露
                logger.warning("仪表盘 WebSocket 发送超时(5s)，断开慢消费者连接")
                await websocket.close(code=4000, reason="Send timeout")
                break
            except (WebSocketDisconnect, RuntimeError):
                # 客户端主动断开连接或连接异常，正常退出循环
                break
            except Exception as e:
                # 数据收集失败，记录警告但继续运行
                logger.warning(f"收集仪表盘数据失败: {e}")
                
            # 等待指定间隔后进行下一次推送
            await asyncio.sleep(PUSH_INTERVAL)
            
    except WebSocketDisconnect:
        # WebSocket 正常断开，无需额外处理
        pass
    except Exception as e:
        # 其他未预期的异常，记录错误日志
        logger.error(f"仪表盘 WebSocket 异常: {e}")
    finally:
        # 清理资源，记录连接断开日志
        logger.info("仪表盘 WebSocket 客户端已断开")
