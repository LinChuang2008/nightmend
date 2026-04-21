"""告警管理 + 告警规则测试。"""
import pytest
from httpx import AsyncClient
from app.models.alert import Alert, AlertRule


@pytest.fixture
async def sample_alert_rule(db_session):
    rule = AlertRule(
        name="CPU High", severity="warning", metric="cpu_percent",
        operator=">", threshold=80.0, duration_seconds=300,
        is_builtin=False, is_enabled=True, target_type="host",
    )
    db_session.add(rule)
    await db_session.commit()
    await db_session.refresh(rule)
    return rule


@pytest.fixture
async def sample_alert(db_session, sample_alert_rule):
    alert = Alert(
        rule_id=sample_alert_rule.id, host_id=1, severity="warning",
        status="firing", title="CPU > 80%", message="CPU at 95%",
        metric_value=95.0, threshold=80.0,
    )
    db_session.add(alert)
    await db_session.commit()
    await db_session.refresh(alert)
    return alert


# ── Alert Rules ──

class TestAlertRules:
    async def test_list_rules(self, client: AsyncClient, auth_headers, sample_alert_rule):
        resp = await client.get("/api/v1/alert-rules", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    async def test_create_rule(self, client: AsyncClient, auth_headers):
        resp = await client.post("/api/v1/alert-rules", headers=auth_headers, json={
            "name": "Mem High", "severity": "critical", "metric": "memory_percent",
            "operator": ">", "threshold": 90, "duration_seconds": 60,
        })
        assert resp.status_code == 201
        assert resp.json()["name"] == "Mem High"

    async def test_get_rule(self, client: AsyncClient, auth_headers, sample_alert_rule):
        resp = await client.get(f"/api/v1/alert-rules/{sample_alert_rule.id}", headers=auth_headers)
        assert resp.status_code == 200

    async def test_update_rule(self, client: AsyncClient, auth_headers, sample_alert_rule):
        resp = await client.put(f"/api/v1/alert-rules/{sample_alert_rule.id}", headers=auth_headers, json={
            "threshold": 85.0,
        })
        assert resp.status_code == 200
        assert resp.json()["threshold"] == 85.0

    async def test_delete_rule(self, client: AsyncClient, auth_headers, sample_alert_rule):
        resp = await client.delete(f"/api/v1/alert-rules/{sample_alert_rule.id}", headers=auth_headers)
        assert resp.status_code == 204

    async def test_get_nonexistent_rule(self, client: AsyncClient, auth_headers):
        resp = await client.get("/api/v1/alert-rules/99999", headers=auth_headers)
        assert resp.status_code == 404


# ── Alerts ──

class TestAlerts:
    async def test_list_alerts(self, client: AsyncClient, auth_headers, sample_alert):
        resp = await client.get("/api/v1/alerts", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    async def test_list_alerts_filter_status(self, client: AsyncClient, auth_headers, sample_alert):
        resp = await client.get("/api/v1/alerts?status=resolved", headers=auth_headers)
        assert resp.json()["total"] == 0

    async def test_list_alerts_filter_severity(self, client: AsyncClient, auth_headers, sample_alert):
        resp = await client.get("/api/v1/alerts?severity=warning", headers=auth_headers)
        assert resp.json()["total"] >= 1

    async def test_get_alert(self, client: AsyncClient, auth_headers, sample_alert):
        resp = await client.get(f"/api/v1/alerts/{sample_alert.id}", headers=auth_headers)
        assert resp.status_code == 200

    async def test_get_nonexistent_alert(self, client: AsyncClient, auth_headers):
        resp = await client.get("/api/v1/alerts/99999", headers=auth_headers)
        assert resp.status_code == 404

    async def test_acknowledge_alert(self, client: AsyncClient, auth_headers, sample_alert):
        resp = await client.post(f"/api/v1/alerts/{sample_alert.id}/ack", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "acknowledged"
