"""通知服务测试（mock 外部渠道）。"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestNotifierService:
    async def test_import_notifier_functions(self):
        from app.services.notifier import send_alert_notification
        assert callable(send_alert_notification)

    async def test_build_template_vars(self):
        from app.services.notifier import _build_template_vars
        from app.core.database import async_session
        # Create a mock alert
        alert = MagicMock()
        alert.id = 1
        alert.title = "Test Alert"
        alert.severity = "warning"
        alert.message = "CPU high"
        alert.status = "firing"
        alert.host_id = 1
        alert.metric_value = 95.0
        alert.threshold = 80.0
        from datetime import datetime
        alert.fired_at = datetime(2026, 2, 21, 0, 0, 0)
        async with async_session() as db:
            result = await _build_template_vars(db, alert)
        assert isinstance(result, dict)
        assert result["title"] == "Test Alert"

    async def test_remediation_success_message(self):
        from app.services.notifier import _remediation_success_message
        msg = _remediation_success_message("CPU High", "web-01", "service_restart", "30s")
        assert "CPU High" in msg
        assert "web-01" in msg
