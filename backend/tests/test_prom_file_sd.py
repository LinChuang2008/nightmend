"""Prometheus file_sd 导出器单元测试。

覆盖点：
  - _target_from_host: IP 优先级 private > ip_address > public；缺失返回 None
  - _target_from_service: 支持 http://url / host:port 两种格式；URL 端口推断
  - build_*_targets 纯函数过滤 None
  - 原子写 JSON 覆盖、tmp 清理
  - sync_file_sd flag=off 短路
  - sync_file_sd 写 hosts.json + services.json 并统计正确
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import settings
from app.models.host import Host
from app.models.service import Service
from app.services import prom_file_sd


def _host(**kwargs) -> Host:
    h = Host()
    h.id = kwargs.get("id", 1)
    h.hostname = kwargs.get("hostname", "web-01")
    h.display_name = kwargs.get("display_name")
    h.ip_address = kwargs.get("ip_address")
    h.private_ip = kwargs.get("private_ip")
    h.public_ip = kwargs.get("public_ip")
    h.os = kwargs.get("os", "linux")
    h.os_version = kwargs.get("os_version")
    h.arch = kwargs.get("arch", "x86_64")
    h.cpu_cores = kwargs.get("cpu_cores")
    h.memory_total_mb = kwargs.get("memory_total_mb")
    h.agent_version = kwargs.get("agent_version")
    h.status = kwargs.get("status", "online")
    h.tags = kwargs.get("tags") or {}
    h.group_name = kwargs.get("group_name")
    h.network_info = kwargs.get("network_info")
    h.agent_token_id = kwargs.get("agent_token_id", 1)
    h.last_heartbeat = kwargs.get("last_heartbeat")
    return h


def _svc(**kwargs) -> Service:
    s = Service()
    s.id = kwargs.get("id", 1)
    s.name = kwargs.get("name", "api")
    s.type = kwargs.get("type", "http")
    s.target = kwargs.get("target", "http://example.com/health")
    s.check_interval = kwargs.get("check_interval", 60)
    s.timeout = kwargs.get("timeout", 10)
    s.expected_status = kwargs.get("expected_status")
    s.is_active = kwargs.get("is_active", True)
    s.status = kwargs.get("status", "up")
    s.host_id = kwargs.get("host_id")
    s.category = kwargs.get("category", "business")
    s.tags = kwargs.get("tags")
    return s


# ─── 纯函数测试 ──────────────────────────────────────────────────────────


def test_host_ip_priority_private_wins():
    h = _host(private_ip="10.0.0.1", ip_address="192.168.1.1", public_ip="1.2.3.4")
    t = prom_file_sd._target_from_host(h)
    assert t["targets"] == ["10.0.0.1:9100"]


def test_host_ip_fallback_public_last():
    h = _host(private_ip=None, ip_address=None, public_ip="1.2.3.4")
    t = prom_file_sd._target_from_host(h)
    assert t["targets"] == ["1.2.3.4:9100"]


def test_host_no_ip_returns_none():
    h = _host(private_ip=None, ip_address=None, public_ip=None)
    assert prom_file_sd._target_from_host(h) is None


def test_host_labels_include_hostname_group_status():
    h = _host(hostname="web-01", private_ip="10.0.0.1", group_name="prod", status="online", os="linux", arch="arm64")
    t = prom_file_sd._target_from_host(h)
    labels = t["labels"]
    assert labels["hostname"] == "web-01"
    assert labels["group"] == "prod"
    assert labels["nightmend_status"] == "online"
    assert labels["target_type"] == "host"
    assert labels["os"] == "linux"
    assert labels["arch"] == "arm64"


def test_host_group_default_when_empty():
    h = _host(private_ip="10.0.0.1", group_name=None)
    t = prom_file_sd._target_from_host(h)
    assert t["labels"]["group"] == "default"


def test_service_url_target_parses_port():
    s = _svc(type="http", target="https://api.example.com/health")
    t = prom_file_sd._target_from_service(s)
    assert t["targets"] == ["api.example.com:443"]
    assert t["labels"]["probe_module"] == "http_2xx"


def test_service_url_http_default_port_80():
    s = _svc(type="http", target="http://api.example.com/")
    t = prom_file_sd._target_from_service(s)
    assert t["targets"] == ["api.example.com:80"]


def test_service_url_explicit_port():
    s = _svc(type="http", target="http://api.example.com:8080/ping")
    t = prom_file_sd._target_from_service(s)
    assert t["targets"] == ["api.example.com:8080"]


def test_service_plain_host_port():
    s = _svc(type="tcp", target="db-01.internal:5432")
    t = prom_file_sd._target_from_service(s)
    assert t["targets"] == ["db-01.internal:5432"]
    assert t["labels"]["probe_module"] == "tcp_connect"
    assert t["labels"]["service_type"] == "tcp"


def test_service_bad_target_returns_none():
    assert prom_file_sd._target_from_service(_svc(target="")) is None
    assert prom_file_sd._target_from_service(_svc(target="/healthz")) is None


def test_build_host_targets_filters_unmatched():
    hosts = [_host(private_ip="10.0.0.1"), _host(private_ip=None, ip_address=None, public_ip=None)]
    result = prom_file_sd.build_host_targets(hosts)
    assert len(result) == 1


def test_build_service_targets_filters_unmatched():
    svcs = [_svc(target="http://ok.example.com/"), _svc(target="???")]
    result = prom_file_sd.build_service_targets(svcs)
    assert len(result) == 1


# ─── 原子写测试 ──────────────────────────────────────────────────────────


def test_atomic_write_json_round_trip(tmp_path):
    target = tmp_path / "sub" / "hosts.json"
    data = [{"targets": ["10.0.0.1:9100"], "labels": {"hostname": "h1"}}]
    prom_file_sd._atomic_write_json(str(target), data)
    assert json.loads(target.read_text()) == data
    # overwrite
    prom_file_sd._atomic_write_json(str(target), [])
    assert json.loads(target.read_text()) == []
    # 无 .nightmend-sd- 残留
    leftover = [p for p in target.parent.iterdir() if p.name.startswith(".nightmend-sd-")]
    assert leftover == []


# ─── sync 主入口 ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sync_file_sd_skipped_when_flag_disabled(tmp_path):
    with patch.object(settings, "prometheus_remote_enabled", False):
        result = await prom_file_sd.sync_file_sd(db=None, targets_dir=str(tmp_path))
    assert result["synced"] is False
    assert result["reason"] == "prometheus_remote_disabled"
    assert not (tmp_path / "hosts.json").exists()


@pytest.mark.asyncio
async def test_sync_file_sd_writes_both_files(tmp_path):
    hosts = [_host(id=1, private_ip="10.0.0.1"), _host(id=2, private_ip="10.0.0.2")]
    svcs = [_svc(id=10, target="http://ok.example.com/")]

    class _FakeScalars:
        def __init__(self, items):
            self._items = items

        def all(self):
            return self._items

    class _FakeResult:
        def __init__(self, items):
            self._items = items

        def scalars(self):
            return _FakeScalars(self._items)

    calls: list = []

    async def _execute(stmt):
        # 第一次 query Host，第二次 query Service
        if len(calls) == 0:
            calls.append("host")
            return _FakeResult(hosts)
        calls.append("service")
        return _FakeResult(svcs)

    fake_db = AsyncMock()
    fake_db.execute = AsyncMock(side_effect=_execute)

    with patch.object(settings, "prometheus_remote_enabled", True):
        result = await prom_file_sd.sync_file_sd(db=fake_db, targets_dir=str(tmp_path))

    assert result["synced"] is True
    assert result["hosts_count"] == 2
    assert result["services_count"] == 1
    hosts_data = json.loads((tmp_path / "hosts.json").read_text())
    svcs_data = json.loads((tmp_path / "services.json").read_text())
    assert len(hosts_data) == 2
    assert len(svcs_data) == 1
    assert hosts_data[0]["labels"]["target_type"] == "host"
    assert svcs_data[0]["labels"]["target_type"] == "service"
