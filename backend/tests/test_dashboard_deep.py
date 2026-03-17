"""Dashboard 路由深度测试 — 趋势数据聚合。"""
import pytest
from datetime import datetime, timezone, timedelta

from app.models.host_metric import HostMetric
from app.models.alert import Alert, AlertRule
from app.models.log_entry import LogEntry
from app.models.host import Host


class TestDashboardTrends:
    @pytest.mark.asyncio
    async def test_trends_empty(self, client, auth_headers):
        resp = await client.get("/api/v1/dashboard/trends", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "trends" in data
        assert len(data["trends"]) == 24

    @pytest.mark.asyncio
    async def test_trends_with_data(self, client, auth_headers, db_session):
        h = Host(hostname="dash-host", status="online", agent_token_id=1)
        db_session.add(h)
        await db_session.commit()
        await db_session.refresh(h)

        now = datetime.now(timezone.utc)
        hour_ago = now - timedelta(hours=1)
        m = HostMetric(host_id=h.id, cpu_percent=75.0, memory_percent=60.0, recorded_at=hour_ago)
        db_session.add(m)

        rule = AlertRule(name="r", metric="cpu_percent", operator=">", threshold=80, severity="warning")
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        a = Alert(rule_id=rule.id, host_id=h.id, severity="warning", status="firing",
                  title="CPU", message="high", fired_at=hour_ago)
        db_session.add(a)

        le = LogEntry(host_id=h.id, service="api", level="ERROR", message="err", timestamp=hour_ago)
        db_session.add(le)
        await db_session.commit()

        resp = await client.get("/api/v1/dashboard/trends", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        trends = data["trends"]
        # At least one entry should have non-None avg_cpu
        has_cpu = any(t["avg_cpu"] is not None for t in trends)
        assert has_cpu

    @pytest.mark.asyncio
    async def test_trends_unauthorized(self, client):
        resp = await client.get("/api/v1/dashboard/trends")
        assert resp.status_code in (401, 403)
