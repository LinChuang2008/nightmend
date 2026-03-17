"""AI Analysis 路由深度测试 — analyze-logs, chat, root-cause, insights, system-summary。"""
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
        with patch("app.routers.ai_analysis.ai_engine") as mock_ai:
            mock_ai.analyze_logs = AsyncMock(return_value={
                "severity": "info", "title": "无日志数据",
                "summary": "无数据", "anomalies": [], "overall_assessment": "无",
            })
            resp = await client.post("/api/v1/ai/analyze-logs", json={"hours": 1}, headers=auth_headers)
            assert resp.status_code == 200
            assert resp.json()["success"] is True
            assert resp.json()["log_count"] == 0

    @pytest.mark.asyncio
    async def test_analyze_with_logs(self, client, auth_headers, db_session):
        now = datetime.now(timezone.utc)
        db_session.add(LogEntry(host_id=1, service="api", level="ERROR", message="OOM", timestamp=now - timedelta(minutes=5)))
        await db_session.commit()

        with patch("app.routers.ai_analysis.ai_engine") as mock_ai:
            mock_ai.analyze_logs = AsyncMock(return_value={
                "severity": "warning", "title": "OOM detected",
                "summary": "OOM found", "anomalies": [], "overall_assessment": "bad",
            })
            resp = await client.post("/api/v1/ai/analyze-logs", json={"hours": 1}, headers=auth_headers)
            assert resp.status_code == 200
            assert resp.json()["log_count"] >= 1

    @pytest.mark.asyncio
    async def test_analyze_with_host_filter(self, client, auth_headers, db_session):
        h = Host(hostname="filter-host", status="online", agent_token_id=1)
        db_session.add(h)
        await db_session.commit()
        await db_session.refresh(h)

        now = datetime.now(timezone.utc)
        db_session.add(LogEntry(host_id=h.id, service="api", level="ERROR", message="err", timestamp=now - timedelta(minutes=5)))
        db_session.add(LogEntry(host_id=999, service="api", level="ERROR", message="other", timestamp=now - timedelta(minutes=5)))
        await db_session.commit()

        with patch("app.routers.ai_analysis.ai_engine") as mock_ai:
            mock_ai.analyze_logs = AsyncMock(return_value={
                "severity": "info", "title": "ok", "summary": "ok", "anomalies": [], "overall_assessment": "ok",
            })
            resp = await client.post("/api/v1/ai/analyze-logs", json={"hours": 1, "host_id": h.id}, headers=auth_headers)
            assert resp.status_code == 200
            assert resp.json()["log_count"] == 1


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


class TestChat:
    @pytest.mark.asyncio
    async def test_chat_success(self, client, auth_headers):
        with patch("app.routers.ai_analysis.ai_engine") as mock_ai:
            mock_ai.chat = AsyncMock(return_value={
                "answer": "System is healthy", "sources": [], "memory_context": [],
            })
            resp = await client.post("/api/v1/ai/chat", json={"question": "How is the system?"}, headers=auth_headers)
            assert resp.status_code == 200
            assert "healthy" in resp.json()["answer"]

    @pytest.mark.asyncio
    async def test_chat_with_context_data(self, client, auth_headers, db_session):
        h = Host(hostname="ctx-host", status="online", agent_token_id=1)
        db_session.add(h)
        s = Service(name="ctx-svc", type="http", target="http://x", status="up", is_active=True)
        db_session.add(s)
        await db_session.commit()

        with patch("app.routers.ai_analysis.ai_engine") as mock_ai:
            mock_ai.chat = AsyncMock(return_value={
                "answer": "All good", "sources": [], "memory_context": [],
            })
            resp = await client.post("/api/v1/ai/chat", json={"question": "status?"}, headers=auth_headers)
            assert resp.status_code == 200


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

        with patch("app.routers.ai_analysis.ai_engine") as mock_ai:
            mock_ai.analyze_root_cause = AsyncMock(return_value={
                "root_cause": "Memory leak in app",
                "confidence": "high",
                "evidence": ["mem 99%"],
                "recommendations": ["restart app"],
                "memory_context": [],
            })
            resp = await client.post(f"/api/v1/ai/root-cause?alert_id={alert.id}", headers=auth_headers)
            assert resp.status_code == 200
            data = resp.json()
            assert data["analysis"]["root_cause"] == "Memory leak in app"


class TestSystemSummary:
    @pytest.mark.asyncio
    async def test_summary_empty(self, client, auth_headers):
        resp = await client.get("/api/v1/ai/system-summary", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["hosts"]["total"] == 0
        assert data["services"]["total"] == 0

    @pytest.mark.asyncio
    async def test_summary_with_data(self, client, auth_headers, db_session):
        h = Host(hostname="sum-host", status="online", agent_token_id=1)
        db_session.add(h)
        s = Service(name="sum-svc", type="http", target="http://s", status="up", is_active=True)
        db_session.add(s)
        await db_session.commit()
        await db_session.refresh(h)

        now = datetime.now(timezone.utc)
        db_session.add(HostMetric(host_id=h.id, cpu_percent=50, memory_percent=60, recorded_at=now - timedelta(minutes=5)))
        await db_session.commit()

        resp = await client.get("/api/v1/ai/system-summary", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["hosts"]["total"] >= 1
        assert data["hosts"]["online"] >= 1
        assert data["services"]["total"] >= 1
        assert data["avg_usage"]["cpu_percent"] is not None
