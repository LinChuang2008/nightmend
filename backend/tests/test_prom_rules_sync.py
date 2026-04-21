"""Prometheus rules.yml 同步器单元测试。

覆盖点：
  - build_rules_yaml 纯函数：只取 query_expr 非空 + is_enabled，输出 Prom 规范结构
  - _atomic_write 真写文件、覆写安全
  - sync_rules_to_prometheus 在 flag=off 时跳过
  - flag=on 时写入 + 触发 reload + 回填 prom_rule_synced_at
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import yaml

from app.core.config import settings
from app.models.alert import AlertRule
from app.services import prom_rules_sync


def _make_rule(**kwargs) -> AlertRule:
    """构造一条 in-memory AlertRule，不触碰 DB。"""
    defaults = dict(
        id=1,
        name="high_5xx",
        description="too many server errors",
        severity="critical",
        metric="http_5xx",
        operator=">",
        threshold=0.1,
        duration_seconds=60,
        is_builtin=False,
        is_enabled=True,
        target_type="host",
        target_filter=None,
        rule_type="metric",
        cooldown_seconds=300,
        continuous_alert=True,
        query_expr='rate(http_requests_total{status=~"5.."}[5m]) > 0.1',
        for_duration_seconds=120,
        prom_rule_synced_at=None,
    )
    defaults.update(kwargs)
    rule = AlertRule()
    for k, v in defaults.items():
        setattr(rule, k, v)
    return rule


# ─── 纯函数测试 ───────────────────────────────────────────────────────────────


def test_build_rules_yaml_shape():
    rules = [_make_rule(id=1), _make_rule(id=2, name="rule2")]
    out = prom_rules_sync.build_rules_yaml(rules)
    parsed = yaml.safe_load(out)
    assert isinstance(parsed["groups"], list)
    assert len(parsed["groups"]) == 2
    g = parsed["groups"][0]
    assert g["name"] == "nightmend_1"
    assert g["rules"][0]["alert"] == "high_5xx"
    assert g["rules"][0]["expr"].startswith("rate(")
    assert g["rules"][0]["for"] == "120s"
    assert g["rules"][0]["labels"]["severity"] == "critical"
    assert g["rules"][0]["labels"]["nightmend_rule_id"] == "1"
    assert "summary" in g["rules"][0]["annotations"]


def test_build_rules_yaml_skips_disabled_or_missing_expr():
    rules = [
        _make_rule(id=1, is_enabled=False),                # 停用 → 跳过
        _make_rule(id=2, query_expr=None),                  # 无 expr → 跳过（老 metric 规则）
        _make_rule(id=3, name="keep_me"),                   # 留下
    ]
    parsed = yaml.safe_load(prom_rules_sync.build_rules_yaml(rules))
    assert len(parsed["groups"]) == 1
    assert parsed["groups"][0]["name"] == "nightmend_3"


def test_build_rules_yaml_falls_back_to_duration_when_for_missing():
    r = _make_rule(for_duration_seconds=None, duration_seconds=180)
    parsed = yaml.safe_load(prom_rules_sync.build_rules_yaml([r]))
    assert parsed["groups"][0]["rules"][0]["for"] == "180s"


def test_build_rules_yaml_minimum_for_60s_when_duration_tiny():
    """duration=0 时至少给 60s，避免 Prometheus 抛空/负值错误。"""
    r = _make_rule(for_duration_seconds=None, duration_seconds=0)
    parsed = yaml.safe_load(prom_rules_sync.build_rules_yaml([r]))
    assert parsed["groups"][0]["rules"][0]["for"] == "60s"


# ─── 原子写测试 ──────────────────────────────────────────────────────────────


def test_atomic_write_creates_and_overwrites(tmp_path):
    target = tmp_path / "sub" / "rules.yml"
    prom_rules_sync._atomic_write(str(target), "groups: []\n")
    assert target.read_text() == "groups: []\n"
    prom_rules_sync._atomic_write(str(target), "groups:\n  - name: x\n")
    assert "name: x" in target.read_text()
    # 无 tmp 残留
    tmp_siblings = [p for p in target.parent.iterdir() if p.name.startswith(".nightmend-rules-")]
    assert tmp_siblings == []


# ─── sync 主入口（不走真实 DB） ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sync_skipped_when_flag_disabled(tmp_path):
    target = tmp_path / "rules.yml"
    with patch.object(settings, "prometheus_remote_enabled", False):
        result = await prom_rules_sync.sync_rules_to_prometheus(
            db=None,  # 不会用到
            rules_path=str(target),
        )
    assert result["skipped"] is True
    assert result["reason"] == "prometheus_remote_disabled"
    assert not target.exists()


@pytest.mark.asyncio
async def test_sync_writes_file_and_triggers_reload(tmp_path):
    target = tmp_path / "rules.yml"
    rule = _make_rule(id=42)

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

    async def _fake_execute(stmt):
        # 第一次是 select，第二次是 update；我们只关心第一次返回
        return _FakeResult([rule])

    fake_db = AsyncMock()
    fake_db.execute = AsyncMock(side_effect=_fake_execute)
    fake_db.commit = AsyncMock()

    # httpx post 返回 200
    class _Resp:
        status_code = 200
        text = "ok"

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url):
            return _Resp()

    with patch.object(settings, "prometheus_remote_enabled", True), \
         patch("app.services.prom_rules_sync.httpx.AsyncClient", return_value=_Client()):
        result = await prom_rules_sync.sync_rules_to_prometheus(
            db=fake_db,
            rules_path=str(target),
            reload_sidecar=True,
        )

    assert target.exists()
    content = yaml.safe_load(target.read_text())
    assert content["groups"][0]["name"] == "nightmend_42"
    assert result["synced"] == 1
    assert result["reloaded"] is True
    fake_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_sync_survives_reload_failure(tmp_path):
    """reload 调用失败不能让 sync 抛异常——文件已落盘即视为半成功。"""
    target = tmp_path / "rules.yml"
    rule = _make_rule()

    class _FakeScalars:
        def all(self):
            return [rule]

    class _FakeResult:
        def scalars(self):
            return _FakeScalars()

    fake_db = AsyncMock()
    fake_db.execute = AsyncMock(return_value=_FakeResult())
    fake_db.commit = AsyncMock()

    import httpx

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url):
            raise httpx.ConnectError("dns fail")

    with patch.object(settings, "prometheus_remote_enabled", True), \
         patch("app.services.prom_rules_sync.httpx.AsyncClient", return_value=_Client()):
        result = await prom_rules_sync.sync_rules_to_prometheus(
            db=fake_db,
            rules_path=str(target),
            reload_sidecar=True,
        )

    assert target.exists()
    assert result["reloaded"] is False
    assert result["synced"] == 1
