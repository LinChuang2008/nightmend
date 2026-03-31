"""AI Analysis 路由深度测试 — analyze-logs, root-cause, insights, analyze。"""
import pytest
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

from app.models.log_entry import LogEntry
from app.models.host import Host
from app.models.host_metric import HostMetric
from app.models.alert import Alert, AlertRule
from app.models.service import Service
from app.models.ai_insight import AIInsight


class TestAnalyzeLogs:
    @pytest.mark.asyncio
    async def test_analyze_no_logs(self, client, auth_headers):
        resp = await client.post("/api/v1/ai/analyze-logs?hours=1", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["log_count"] == 0

    @pytest.mark.asyncio
    async def test_analyze_with_logs(self, client, auth_headers, db_session):
        now = datetime.now(timezone.utc)
        db_session.add(LogEntry(host_id=1, service="api", level="ERROR", message="OOM", timestamp=now - timedelta(minutes=5)))
        await db_session.commit()

        mock_response = json.dumps({
            "title": "OOM detected",
            "summary": "OOM found",
            "severity": "warning",
            "patterns": ["OOM"],
            "suggestions": ["add memory"],
        })
        with patch("app.routers.ai_analysis.chat_completion", new_callable=AsyncMock, return_value=mock_response):
            resp = await client.post("/api/v1/ai/analyze-logs?hours=1", headers=auth_headers)
            assert resp.status_code == 200
            assert resp.json()["log_count"] >= 1

    @pytest.mark.asyncio
    async def test_analyze_ai_error_returns_503(self, client, auth_headers, db_session):
        now = datetime.now(timezone.utc)
        db_session.add(LogEntry(host_id=1, service="api", level="ERROR", message="err", timestamp=now - timedelta(minutes=5)))
        await db_session.commit()

        from app.services.llm_client import LLMClientError
        with patch("app.routers.ai_analysis.chat_completion", new_callable=AsyncMock, side_effect=LLMClientError("AI down")):
            resp = await client.post("/api/v1/ai/analyze-logs?hours=1", headers=auth_headers)
            assert resp.status_code == 503


class TestInsights:
    @pytest.mark.asyncio
    async def test_list_empty(self, client, auth_headers):
        resp = await client.get("/api/v1/ai/insights", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    @pytest.mark.asyncio
    async def test_list_with_filter(self, client, auth_headers, db_session):
        db_session.add(AIInsight(
            insight_type="anomaly", severity="warning", title="Test",
            summary="test insight", details={}, status="new"
        ))
        db_session.add(AIInsight(
            insight_type="chat", severity="info", title="Chat",
            summary="chat insight", details={}, status="reviewed"
        ))
        await db_session.commit()

        resp = await client.get("/api/v1/ai/insights?severity=warning", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

        resp = await client.get("/api/v1/ai/insights?status=reviewed", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["total"] == 1


class TestRootCause:
    @pytest.mark.asyncio
    async def test_root_cause_not_found(self, client, auth_headers):
        resp = await client.post("/api/v1/ai/root-cause?alert_id=9999", headers=auth_headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_root_cause_success(self, client, auth_headers, db_session):
        rule = AlertRule(name="r", metric="cpu_percent", operator=">", threshold=80, severity="critical")
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        h = Host(hostname="rc-host", status="online", agent_token_id=1)
        db_session.add(h)
        await db_session.commit()
        await db_session.refresh(h)

        alert = Alert(
            rule_id=rule.id, host_id=h.id, severity="critical", status="firing",
            title="CPU Critical", message="cpu=99",
            fired_at=datetime.now(timezone.utc) - timedelta(minutes=10)
        )
        db_session.add(alert)
        await db_session.commit()
        await db_session.refresh(alert)

        mock_response = json.dumps({
            "root_cause": "Memory leak in app",
            "impact": "high",
            "suggestions": ["restart app"],
            "severity": "high",
        })
        with patch("app.routers.ai_analysis.chat_completion", new_callable=AsyncMock, return_value=mock_response):
            resp = await client.post(f"/api/v1/ai/root-cause?alert_id={alert.id}", headers=auth_headers)
            assert resp.status_code == 200
            data = resp.json()
            assert data["root_cause"] == "Memory leak in app"
