"""
告警诊断 SSE 流 + 诊断功能测试
Tests for alert diagnosis SSE stream and diagnosis-only mode.
"""
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.alert_sources.base import IncomingAlert
from app.core.config import settings


# ── Diagnosis Function Tests ─────────────────────────────────────────

class TestDiagnosisFlow:
    """_run_diagnosis() function tests."""

    @pytest.mark.asyncio
    async def test_diagnosis_happy_path(self):
        """AI returns result, event published to Redis."""
        from app.routers.webhooks import _run_diagnosis

        incoming = IncomingAlert(
            source="prometheus",
            external_id="test-1",
            alertname="HighCPU",
            instance="10.0.1.5:9090",
            severity="warning",
            status="firing",
            labels={"job": "node_exporter", "instance": "10.0.1.5:9090"},
            annotations={"summary": "CPU usage above 90%"},
            starts_at=datetime(2026, 3, 28, tzinfo=timezone.utc),
        )

        mock_result = {
            "root_cause": "High CPU due to runaway process",
            "confidence": 0.85,
            "evidence": ["CPU at 95%"],
            "recommendations": ["Kill the process"],
        }

        mock_redis = AsyncMock()

        with patch("app.routers.webhooks.AIEngine") as MockEngine, \
             patch("app.routers.webhooks.get_redis", return_value=mock_redis):
            MockEngine.return_value.analyze_root_cause = AsyncMock(return_value=mock_result)

            await _run_diagnosis(incoming, alert_id=42)

            # Verify Redis publish was called
            mock_redis.publish.assert_called_once()
            channel, data = mock_redis.publish.call_args[0]
            assert channel == "nightmend:alert:diagnosis"

            event = json.loads(data)
            assert event["alertname"] == "HighCPU"
            assert event["severity"] == "warning"
            assert event["diagnosis"]["root_cause"] == "High CPU due to runaway process"
            assert event["alert_id"] == 42

    @pytest.mark.asyncio
    async def test_diagnosis_ai_failure(self):
        """AI engine raises exception, error is logged, no Redis publish."""
        from app.routers.webhooks import _run_diagnosis

        incoming = IncomingAlert(
            source="prometheus",
            external_id="test-2",
            alertname="HighMemory",
            instance="10.0.1.6:9090",
            severity="critical",
            status="firing",
            labels={},
            annotations={},
            starts_at=datetime(2026, 3, 28, tzinfo=timezone.utc),
        )

        mock_redis = AsyncMock()

        with patch("app.routers.webhooks.AIEngine") as MockEngine, \
             patch("app.routers.webhooks.get_redis", return_value=mock_redis):
            MockEngine.return_value.analyze_root_cause = AsyncMock(
                side_effect=Exception("AI API timeout")
            )

            # Should not raise
            await _run_diagnosis(incoming, alert_id=None)

            # Redis publish should NOT be called
            mock_redis.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_diagnosis_redis_failure(self):
        """AI succeeds but Redis publish fails, error is logged."""
        from app.routers.webhooks import _run_diagnosis

        incoming = IncomingAlert(
            source="prometheus",
            external_id="test-3",
            alertname="DiskFull",
            instance="10.0.1.7:9090",
            severity="critical",
            status="firing",
            labels={"job": "node"},
            annotations={"summary": "Disk 95% full"},
            starts_at=datetime(2026, 3, 28, tzinfo=timezone.utc),
        )

        mock_redis = AsyncMock()
        mock_redis.publish = AsyncMock(side_effect=ConnectionError("Redis down"))

        with patch("app.routers.webhooks.AIEngine") as MockEngine, \
             patch("app.routers.webhooks.get_redis", return_value=mock_redis):
            MockEngine.return_value.analyze_root_cause = AsyncMock(
                return_value={"root_cause": "Disk full"}
            )

            # Should not raise
            await _run_diagnosis(incoming, alert_id=1)


# ── SSE Endpoint Tests ───────────────────────────────────────────────

class TestSSEEndpoint:
    """GET /api/v1/demo/alerts/stream tests."""

    @pytest.mark.asyncio
    async def test_sse_max_connections(self, client):
        """SSE returns 503 when at max connections."""
        from app.routers import alert_stream

        original_count = alert_stream._connection_count

        try:
            # Simulate being at max connections
            async with alert_stream._connection_lock:
                alert_stream._connection_count = settings.demo_sse_max_clients

            resp = await client.get("/api/v1/demo/alerts/stream")
            assert resp.status_code == 503
            assert "Too many connections" in resp.text
        finally:
            async with alert_stream._connection_lock:
                alert_stream._connection_count = original_count

    @pytest.mark.asyncio
    async def test_sse_endpoint_exists(self, client):
        """SSE endpoint is registered and reachable (not 404)."""
        from app.routers import alert_stream

        # Set max to 0 so we get 503 (confirms route exists, not 404)
        original = alert_stream._connection_count
        try:
            async with alert_stream._connection_lock:
                alert_stream._connection_count = settings.demo_sse_max_clients
            resp = await client.get("/api/v1/demo/alerts/stream")
            assert resp.status_code != 404
        finally:
            async with alert_stream._connection_lock:
                alert_stream._connection_count = original

    @pytest.mark.asyncio
    async def test_sse_no_auth_required(self, client):
        """SSE endpoint returns non-401 without authentication (503 at capacity is OK)."""
        from app.routers import alert_stream

        original = alert_stream._connection_count
        try:
            async with alert_stream._connection_lock:
                alert_stream._connection_count = settings.demo_sse_max_clients
            # No auth headers — should NOT get 401
            resp = await client.get("/api/v1/demo/alerts/stream")
            assert resp.status_code != 401
        finally:
            async with alert_stream._connection_lock:
                alert_stream._connection_count = original

    @pytest.mark.asyncio
    async def test_sse_per_ip_limit(self, client):
        """SSE returns 503 when per-IP limit reached."""
        from app.routers import alert_stream

        original_ip = dict(alert_stream._ip_connections)
        try:
            # httpx ASGITransport uses various IPs; fill all common ones
            async with alert_stream._connection_lock:
                for ip in ["127.0.0.1", "localhost", "testclient", "unknown"]:
                    alert_stream._ip_connections[ip] = alert_stream._MAX_PER_IP

            resp = await client.get("/api/v1/demo/alerts/stream")
            assert resp.status_code == 503
            assert "Too many connections" in resp.text
        finally:
            async with alert_stream._connection_lock:
                alert_stream._ip_connections.clear()
                alert_stream._ip_connections.update(original_ip)


# ── Config Default Tests ─────────────────────────────────────────────

class TestConfigDefaults:
    """Verify default config values."""

    def test_enable_remediation_default_true(self):
        """ENABLE_REMEDIATION defaults to True (don't break existing behavior)."""
        assert settings.enable_remediation is True

    def test_demo_sse_max_clients_default(self):
        """DEMO_SSE_MAX_CLIENTS defaults to 50."""
        assert settings.demo_sse_max_clients == 50
