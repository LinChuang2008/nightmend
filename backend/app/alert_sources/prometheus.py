"""
Prometheus AlertManager 适配器 (Prometheus AlertManager Adapter)

解析 AlertManager webhook payload，映射到 NightMend Host，
转换为 RemediationAlert 供自动修复管道使用。

AlertManager webhook payload 格式:
{
    "status": "firing",
    "alerts": [{
        "status": "firing",
        "labels": {"alertname": "HighCPU", "instance": "10.0.1.5:9090", "severity": "critical"},
        "annotations": {"summary": "CPU usage > 90%"},
        "startsAt": "2026-03-24T12:00:00Z",
        "endsAt": "0001-01-01T00:00:00Z"
    }]
}
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.host import Host
from app.remediation.models import RemediationAlert

from .base import AlertSourceAdapter, IncomingAlert

logger = logging.getLogger("nightmend.alert_sources.prometheus")

# Prometheus alertname → NightMend alert_type 映射
_ALERTNAME_MAP: dict[str, str] = {
    "highcpu": "cpu_high",
    "cpuhigh": "cpu_high",
    "hostcpuhigh": "cpu_high",
    "highmemory": "memory_high",
    "memoryhigh": "memory_high",
    "hostmemoryusagehigh": "memory_high",
    "diskfull": "disk_full",
    "diskspacehigh": "disk_full",
    "hostdiskspacefull": "disk_full",
    "servicedown": "service_down",
    "instancedown": "service_down",
    "targetdown": "service_down",
    "containercrash": "container_crash",
    "containerhighrestart": "container_crash",
    "kubepodcrashlooping": "container_crash",
}

# Prometheus severity → NightMend severity 映射
_SEVERITY_MAP: dict[str, str] = {
    "critical": "critical",
    "error": "critical",
    "warning": "warning",
    "warn": "warning",
    "info": "info",
    "none": "info",
}


def _extract_ip(instance: str) -> str:
    """从 Prometheus instance label 中提取 IP (去掉端口号)。

    Examples:
        "10.0.1.5:9090" → "10.0.1.5"
        "web01.example.com:9090" → "web01.example.com"
        "10.0.1.5" → "10.0.1.5"
    """
    # 去掉端口
    match = re.match(r"^(.+?)(?::\d+)?$", instance)
    return match.group(1) if match else instance


class PrometheusAdapter(AlertSourceAdapter):
    """Prometheus AlertManager webhook 适配器"""

    def parse(self, raw_payload: dict) -> list[IncomingAlert]:
        """解析 AlertManager webhook payload。"""
        alerts_raw = raw_payload.get("alerts", [])
        result: list[IncomingAlert] = []

        for alert_data in alerts_raw:
            labels = alert_data.get("labels", {})
            annotations = alert_data.get("annotations", {})
            alertname = labels.get("alertname", "unknown")
            instance = labels.get("instance", "")
            severity = labels.get("severity", "warning")
            status = alert_data.get("status", "firing")

            # 解析时间
            starts_at_str = alert_data.get("startsAt", "")
            try:
                starts_at = datetime.fromisoformat(starts_at_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                starts_at = datetime.now(timezone.utc)

            ends_at = None
            ends_at_str = alert_data.get("endsAt", "")
            if ends_at_str and not ends_at_str.startswith("0001"):
                try:
                    ends_at = datetime.fromisoformat(ends_at_str.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    pass

            # 构建去重 key
            external_id = f"prom:{alertname}:{instance}:{starts_at.isoformat()}"

            result.append(IncomingAlert(
                source="prometheus",
                external_id=external_id,
                alertname=alertname,
                instance=instance,
                severity=_SEVERITY_MAP.get(severity.lower(), "warning"),
                status=status,
                labels=labels,
                annotations=annotations,
                starts_at=starts_at,
                ends_at=ends_at,
            ))

        return result

    async def map_to_host(self, alert: IncomingAlert, db: AsyncSession) -> Optional[Host]:
        """将 Prometheus instance 映射到 NightMend Host。

        匹配策略:
        1. 自定义 label nightmend_host_id → 直接按 ID 查
        2. 提取 IP → 匹配 Host.ip_address / private_ip / public_ip
        3. 提取 hostname → 匹配 Host.hostname
        """
        # 策略 1: 自定义 label
        host_id_str = alert.labels.get("nightmend_host_id")
        if host_id_str:
            try:
                result = await db.execute(
                    select(Host).where(Host.id == int(host_id_str))
                )
                host = result.scalar_one_or_none()
                if host:
                    return host
            except (ValueError, TypeError):
                pass

        # 无 instance → 无法映射
        if not alert.instance:
            return None

        identifier = _extract_ip(alert.instance)

        # 策略 2: IP 匹配
        result = await db.execute(
            select(Host).where(
                or_(
                    Host.ip_address == identifier,
                    Host.private_ip == identifier,
                    Host.public_ip == identifier,
                )
            )
        )
        host = result.scalar_one_or_none()
        if host:
            return host

        # 策略 3: hostname 匹配
        result = await db.execute(
            select(Host).where(Host.hostname == identifier)
        )
        return result.scalar_one_or_none()

    def to_remediation_alert(self, incoming: IncomingAlert, host: Host, alert_db_id: int) -> RemediationAlert:
        """转换为 RemediationAlert。"""
        alertname_lower = incoming.alertname.lower().replace("-", "").replace("_", "")
        alert_type = _ALERTNAME_MAP.get(alertname_lower, incoming.alertname.lower())

        summary = incoming.annotations.get("summary", "")
        description = incoming.annotations.get("description", "")
        message = summary or description or f"Prometheus alert: {incoming.alertname}"

        return RemediationAlert(
            alert_id=alert_db_id,
            alert_type=alert_type,
            severity=incoming.severity,
            host=host.hostname or host.private_ip or host.ip_address or "unknown",
            host_id=host.id,
            message=message,
            labels={
                **incoming.labels,
                "source": "prometheus",
                "alertname": incoming.alertname,
            },
            timestamp=incoming.starts_at,
        )
