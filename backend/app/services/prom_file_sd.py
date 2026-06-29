"""Prometheus file_sd targets 导出器 (Prometheus file_sd Targets Exporter)

顶层逻辑：
    NightMend 的 Host / Service 表是"真源"，Prometheus sidecar 需要订阅这个真源
    才能动态发现 scrape 目标。这里把两类来源合成 Prometheus file_sd 文件：

      - host_exporter_port: 每台主机若暴露了 node_exporter（默认 9100），导出为一条
        {targets: ["host_ip:9100"], labels: {hostname, group, target_type=host}}
      - Service: type=http/tcp 且有可提取 host:port 的，导出为服务级 target

    Prometheus 用 file_sd_configs 订阅 /etc/prometheus/targets/*.json，Prom 进程
    每 refresh_interval（30s）重读文件，无需 reload。

输出文件：
    /etc/prometheus/targets/hosts.json
    /etc/prometheus/targets/services.json

配置规范：
    https://prometheus.io/docs/prometheus/latest/configuration/configuration/#file_sd_config
    JSON 顶层是 list<{ "targets": [str], "labels": {str: str} }>
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.host import Host
from app.models.service import Service

logger = logging.getLogger(__name__)

DEFAULT_TARGETS_DIR = os.environ.get(
    "NIGHTMEND_PROM_TARGETS_DIR",
    "/etc/prometheus/targets",
)

# node_exporter 默认端口；允许通过 env 覆盖
DEFAULT_NODE_EXPORTER_PORT = int(os.environ.get("NIGHTMEND_NODE_EXPORTER_PORT", "9100"))


def _primary_ip(host: Host) -> str | None:
    """取主机的可达 IP：优先 private，其次 ip_address，最后 public。"""
    return host.private_ip or host.ip_address or host.public_ip


def _sanitize_label(value: Any) -> str:
    """Prom label value 必须是字符串，None / 数字统一转 str，裁掉换行防 JSON 污染。"""
    if value is None:
        return ""
    return str(value).replace("\n", " ").strip()


def _target_from_host(host: Host) -> dict[str, Any] | None:
    ip = _primary_ip(host)
    if not ip:
        return None
    return {
        "targets": [f"{ip}:{DEFAULT_NODE_EXPORTER_PORT}"],
        "labels": {
            "hostname": _sanitize_label(host.hostname),
            "host_id": str(host.id),
            "group": _sanitize_label(host.group_name) or "default",
            "target_type": "host",
            "os": _sanitize_label(host.os),
            "arch": _sanitize_label(host.arch),
            # 便于后续写 PromQL：status='online' | 'offline'
            "nightmend_status": _sanitize_label(host.status),
        },
    }


def _target_from_service(svc: Service) -> dict[str, Any] | None:
    """从 service.target 推 host:port；URL 型取 netloc，host:port 型直接用。"""
    raw = (svc.target or "").strip()
    if not raw:
        return None
    host_port: str | None = None
    if "://" in raw:
        parsed = urlparse(raw)
        if parsed.hostname:
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            host_port = f"{parsed.hostname}:{port}"
    elif ":" in raw and "/" not in raw:
        # "host:port" 裸格式
        host_port = raw
    if not host_port:
        return None

    return {
        "targets": [host_port],
        "labels": {
            "service_name": _sanitize_label(svc.name),
            "service_id": str(svc.id),
            "service_type": _sanitize_label(svc.type),
            "category": _sanitize_label(svc.category) or "business",
            "target_type": "service",
            # blackbox_exporter 用得上这个标签区分 module
            "probe_module": "http_2xx" if svc.type == "http" else "tcp_connect",
        },
    }


def build_host_targets(hosts: Iterable[Host]) -> list[dict[str, Any]]:
    """纯函数：Host list → Prom file_sd 列表；None 项过滤。"""
    out: list[dict[str, Any]] = []
    for h in hosts:
        t = _target_from_host(h)
        if t is not None:
            out.append(t)
    return out


def build_service_targets(services: Iterable[Service]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for s in services:
        t = _target_from_service(s)
        if t is not None:
            out.append(t)
    return out


def _atomic_write_json(path: str, data: Any) -> None:
    """原子写 JSON：tmp + rename 防止 Prom 读半截。"""
    directory = os.path.dirname(path) or "."
    Path(directory).mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".nightmend-sd-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


async def sync_file_sd(
    db: AsyncSession,
    *,
    targets_dir: str | None = None,
) -> dict[str, Any]:
    """
    全量导出 Host + Service 到 file_sd targets。

    sidecar 未启用时短路；file_sd 依赖文件系统，不依赖 sidecar 可达。
    """
    if not settings.prometheus_remote_enabled:
        return {"synced": False, "reason": "prometheus_remote_disabled"}

    directory = targets_dir or DEFAULT_TARGETS_DIR

    # 只导出已启用/在线的 Host + 监控开启的 Service，避免给 Prom 打脏目标
    host_rows = (
        await db.execute(select(Host).where(Host.status.in_(["online", "unknown"])))
    ).scalars().all()
    svc_rows = (
        await db.execute(select(Service).where(Service.is_active.is_(True)))
    ).scalars().all()

    host_targets = build_host_targets(host_rows)
    svc_targets = build_service_targets(svc_rows)

    hosts_path = os.path.join(directory, "hosts.json")
    services_path = os.path.join(directory, "services.json")
    _atomic_write_json(hosts_path, host_targets)
    _atomic_write_json(services_path, svc_targets)

    logger.info(
        "file_sd exported: dir=%s hosts=%d services=%d",
        directory, len(host_targets), len(svc_targets),
    )
    return {
        "synced": True,
        "dir": directory,
        "hosts_count": len(host_targets),
        "services_count": len(svc_targets),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
