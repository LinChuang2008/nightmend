"""Prometheus AlertManager Webhook 端点测试"""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.database import get_db
from app.models.host import Host


# ── Fixtures ──

def _fake_host(**overrides):
    h = MagicMock(spec=Host)
    h.id = overrides.get("id", 1)
    h.hostname = overrides.get("hostname", "web01")
    h.ip_address = overrides.get("ip_address", "10.0.1.5")
    h.private_ip = overrides.get("private_ip", "10.0.1.5")
    h.public_ip = overrides.get("public_ip", None)
    return h


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


@pytest.fixture
def client(mock_db):
    app.dependency_overrides[get_db] = lambda: mock_db
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    yield client
    app.dependency_overrides.clear()


VALID_AM_PAYLOAD = {
    "status": "firing",
    "alerts": [
        {
            "status": "firing",
            "labels": {
                "alertname": "HighCPU",
                "instance": "10.0.1.5:9090",
                "severity": "critical",
                "job": "node",
            },
            "annotations": {
                "summary": "CPU usage is above 90%",
            },
            "startsAt": "2026-03-24T12:00:00Z",
            "endsAt": "0001-01-01T00:00:00Z",
        }
    ],
}

RESOLVED_PAYLOAD = {
    "status": "resolved",
    "alerts": [
        {
            "status": "resolved",
            "labels": {"alertname": "HighCPU", "instance": "10.0.1.5:9090"},
            "annotations": {"summary": "CPU back to normal"},
            "startsAt": "2026-03-24T12:00:00Z",
            "endsAt": "2026-03-24T12:05:00Z",
        }
    ],
}


# ── Auth Tests ──

class TestWebhookAuth:
    @pytest.mark.asyncio
    async def test_no_token_returns_401(self, client):
        resp = await client.post("/api/v1/webhooks/alertmanager", json=VALID_AM_PAYLOAD)
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_token_returns_401(self, client):
        resp = await client.post(
            "/api/v1/webhooks/alertmanager",
            json=VALID_AM_PAYLOAD,
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    @patch("app.routers.webhooks.settings")
    async def test_unconfigured_token_returns_503(self, mock_settings, client):
        mock_settings.alertmanager_webhook_token = ""
        resp = await client.post(
            "/api/v1/webhooks/alertmanager",
            json=VALID_AM_PAYLOAD,
            headers={"Authorization": "Bearer some-token"},
        )
        assert resp.status_code == 503


# ── Parsing Tests ──

class TestPrometheusAdapter:
    def test_parse_standard_payload(self):
        from app.alert_sources.prometheus import PrometheusAdapter
        adapter = PrometheusAdapter()
        alerts = adapter.parse(VALID_AM_PAYLOAD)
        assert len(alerts) == 1
        assert alerts[0].alertname == "HighCPU"
        assert alerts[0].instance == "10.0.1.5:9090"
        assert alerts[0].severity == "critical"
        assert alerts[0].status == "firing"
        assert alerts[0].source == "prometheus"

    def test_parse_resolved_alert(self):
        from app.alert_sources.prometheus import PrometheusAdapter
        adapter = PrometheusAdapter()
        alerts = adapter.parse(RESOLVED_PAYLOAD)
        assert len(alerts) == 1
        assert alerts[0].status == "resolved"

    def test_parse_empty_alerts(self):
        from app.alert_sources.prometheus import PrometheusAdapter
        adapter = PrometheusAdapter()
        alerts = adapter.parse({"alerts": []})
        assert len(alerts) == 0

    def test_parse_missing_fields_uses_defaults(self):
        from app.alert_sources.prometheus import PrometheusAdapter
        adapter = PrometheusAdapter()
        alerts = adapter.parse({
            "alerts": [{"labels": {"alertname": "Test"}, "status": "firing"}]
        })
        assert len(alerts) == 1
        assert alerts[0].alertname == "Test"
        assert alerts[0].severity == "warning"  # default

    def test_alertname_mapping(self):
        from app.alert_sources.prometheus import PrometheusAdapter
        adapter = PrometheusAdapter()
        host = _fake_host()
        alerts = adapter.parse({
            "alerts": [{
                "labels": {"alertname": "HostCpuHigh", "instance": "10.0.1.5:9090"},
                "status": "firing",
                "startsAt": "2026-03-24T12:00:00Z",
            }]
        })

        # mock alert_db_id
        ra = adapter.to_remediation_alert(alerts[0], host, alert_db_id=1)
        assert ra.alert_type == "cpu_high"


# ── Host Mapping Tests ──

class TestHostMapping:
    @pytest.mark.asyncio
    async def test_map_by_ip(self):
        from app.alert_sources.prometheus import PrometheusAdapter
        from app.alert_sources.base import IncomingAlert

        adapter = PrometheusAdapter()
        alert = IncomingAlert(
            source="prometheus",
            external_id="test",
            alertname="HighCPU",
            instance="10.0.1.5:9090",
        )

        mock_db = AsyncMock()
        fake_host = _fake_host()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = fake_host
        mock_db.execute = AsyncMock(return_value=mock_result)

        host = await adapter.map_to_host(alert, mock_db)
        assert host is not None
        assert host.id == 1

    @pytest.mark.asyncio
    async def test_map_returns_none_for_unknown(self):
        from app.alert_sources.prometheus import PrometheusAdapter
        from app.alert_sources.base import IncomingAlert

        adapter = PrometheusAdapter()
        alert = IncomingAlert(
            source="prometheus",
            external_id="test",
            alertname="HighCPU",
            instance="192.168.99.99:9090",
        )

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        host = await adapter.map_to_host(alert, mock_db)
        assert host is None

    @pytest.mark.asyncio
    async def test_map_empty_instance(self):
        from app.alert_sources.prometheus import PrometheusAdapter
        from app.alert_sources.base import IncomingAlert

        adapter = PrometheusAdapter()
        alert = IncomingAlert(
            source="prometheus",
            external_id="test",
            alertname="HighCPU",
            instance="",
        )

        mock_db = AsyncMock()
        host = await adapter.map_to_host(alert, mock_db)
        assert host is None


# ── IP Extraction Tests ──

class TestIPExtraction:
    def test_ip_with_port(self):
        from app.alert_sources.prometheus import _extract_ip
        assert _extract_ip("10.0.1.5:9090") == "10.0.1.5"

    def test_ip_without_port(self):
        from app.alert_sources.prometheus import _extract_ip
        assert _extract_ip("10.0.1.5") == "10.0.1.5"

    def test_hostname_with_port(self):
        from app.alert_sources.prometheus import _extract_ip
        assert _extract_ip("web01.example.com:9090") == "web01.example.com"

    def test_hostname_without_port(self):
        from app.alert_sources.prometheus import _extract_ip
        assert _extract_ip("web01.example.com") == "web01.example.com"


# ── Remediation Gating Tests ────────────────────────────────────────

class TestRemediationGating:
    """ENABLE_REMEDIATION env var gates remediation vs diagnosis."""

    @pytest.mark.asyncio
    async def test_remediation_enabled_by_default(self):
        """Default: enable_remediation=True."""
        from app.core.config import settings
        assert settings.enable_remediation is True

    @pytest.mark.asyncio
    async def test_diagnosis_mode_no_host_runs_diagnosis(self):
        """When remediation disabled and no host match, diagnosis still runs."""
        from app.routers.webhooks import _process_alert
        from app.alert_sources.base import IncomingAlert
        from datetime import datetime, timezone
        from unittest.mock import patch, AsyncMock

        incoming = IncomingAlert(
            source="prometheus",
            external_id="gate-test-1",
            alertname="TestAlert",
            instance="10.0.0.1:9090",
            severity="warning",
            status="firing",
            labels={"job": "test"},
            annotations={"summary": "Test alert"},
            starts_at=datetime(2026, 3, 28, tzinfo=timezone.utc),
        )

        mock_db = AsyncMock()

        with patch("app.routers.webhooks._prometheus_adapter") as mock_adapter, \
             patch("app.routers.webhooks.settings") as mock_settings, \
             patch("app.routers.webhooks._run_diagnosis") as mock_diagnosis, \
             patch("app.routers.webhooks.asyncio") as mock_asyncio:
            mock_adapter.map_to_host = AsyncMock(return_value=None)
            mock_settings.enable_remediation = False

            result = await _process_alert(incoming, mock_db)

            assert result["status"] == "diagnosing"
            mock_asyncio.create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_remediation_enabled_no_host_skips(self):
        """When remediation enabled and no host match, alert is skipped (existing behavior)."""
        from app.routers.webhooks import _process_alert
        from app.alert_sources.base import IncomingAlert
        from datetime import datetime, timezone
        from unittest.mock import patch, AsyncMock

        incoming = IncomingAlert(
            source="prometheus",
            external_id="gate-test-2",
            alertname="TestAlert",
            instance="10.0.0.2:9090",
            severity="warning",
            status="firing",
            labels={},
            annotations={},
            starts_at=datetime(2026, 3, 28, tzinfo=timezone.utc),
        )

        mock_db = AsyncMock()

        with patch("app.routers.webhooks._prometheus_adapter") as mock_adapter, \
             patch("app.routers.webhooks.settings") as mock_settings:
            mock_adapter.map_to_host = AsyncMock(return_value=None)
            mock_settings.enable_remediation = True

            result = await _process_alert(incoming, mock_db)

            assert result["status"] == "skipped"
            assert result["reason"] == "host_not_found"
