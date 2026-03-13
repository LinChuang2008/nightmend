"""通知服务深度测试 — mock 5个渠道 + 降噪逻辑。"""
import pytest
from datetime import datetime, timezone, time as dt_time
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.notifier import (
    _build_template_vars,
    _render_template,
    _remediation_success_message,
    _remediation_failure_message,
    _remediation_approval_message,
    _dingtalk_sign,
    _feishu_sign,
    send_alert_notification,
    _send_to_channel,
    _send_webhook,
    _send_dingtalk,
    _send_feishu,
    _send_wecom,
    _send_email,
    send_remediation_notification,
    _get_default_template,
)


def _make_alert(**overrides):
    alert = MagicMock()
    alert.id = overrides.get("id", 1)
    alert.title = overrides.get("title", "Test Alert")
    alert.severity = overrides.get("severity", "warning")
    alert.message = overrides.get("message", "CPU high")
    alert.status = overrides.get("status", "firing")
    alert.host_id = overrides.get("host_id", 1)
    alert.service_id = overrides.get("service_id", None)
    alert.metric_value = overrides.get("metric_value", 95.0)
    alert.threshold = overrides.get("threshold", 80.0)
    alert.fired_at = overrides.get("fired_at", datetime(2026, 2, 21, 0, 0, 0))
    alert.resolved_at = overrides.get("resolved_at", None)
    alert.rule_id = overrides.get("rule_id", 10)
    return alert


def _make_channel(ch_type="webhook", config=None, name="test-channel", is_enabled=True):
    ch = MagicMock()
    ch.id = 1
    ch.name = name
    ch.type = ch_type
    ch.config = config or {}
    ch.is_enabled = is_enabled
    return ch


class TestTemplateVars:
    @pytest.mark.asyncio
    async def test_full_alert(self):
        from app.core.database import async_session
        alert = _make_alert()
        async with async_session() as db:
            v = await _build_template_vars(db, alert)
        assert v["title"] == "Test Alert"
        assert v["severity"] == "warning"
        assert v["metric_value"] == 95.0
        assert "2026" in v["fired_at"]

    @pytest.mark.asyncio
    async def test_none_values(self):
        from app.core.database import async_session
        alert = _make_alert(metric_value=None, threshold=None, host_id=None, fired_at=None)
        async with async_session() as db:
            v = await _build_template_vars(db, alert)
        assert v["metric_value"] == ""
        assert v["threshold"] == ""
        assert v["host_id"] == ""
        assert v["fired_at"] == ""


class TestRenderTemplate:
    def test_render_with_vars(self):
        tmpl = MagicMock()
        tmpl.subject_template = "[Alert] {title}"
        tmpl.body_template = "Severity: {severity}, Message: {message}"
        subj, body = _render_template(tmpl, {"title": "CPU", "severity": "critical", "message": "overload"})
        assert subj == "[Alert] CPU"
        assert "critical" in body

    def test_render_missing_var(self):
        tmpl = MagicMock()
        tmpl.subject_template = "{nonexistent}"
        tmpl.body_template = "{also_missing}"
        subj, body = _render_template(tmpl, {"title": "x"})
        assert subj == "{nonexistent}"  # kept as-is
        assert body == "{also_missing}"

    def test_render_no_subject(self):
        tmpl = MagicMock()
        tmpl.subject_template = None
        tmpl.body_template = "body {title}"
        subj, body = _render_template(tmpl, {"title": "hi"})
        assert subj is None
        assert body == "body hi"


class TestRemediationMessages:
    def test_success(self):
        msg = _remediation_success_message("CPU High", "web-01", "restart", "30s")
        assert "CPU High" in msg and "web-01" in msg and "restart" in msg

    def test_failure(self):
        msg = _remediation_failure_message("CPU High", "web-01", "timeout")
        assert "失败" in msg and "timeout" in msg

    def test_approval(self):
        msg = _remediation_approval_message("CPU High", "web-01", "restart svc", "http://approve")
        assert "审批" in msg and "http://approve" in msg


class TestSignatures:
    def test_dingtalk_sign(self):
        ts, sign = _dingtalk_sign("my-secret")
        assert len(ts) > 10
        assert len(sign) > 10

    def test_feishu_sign(self):
        ts, sign = _feishu_sign("my-secret")
        assert len(ts) > 5
        assert len(sign) > 10


class TestSendWebhook:
    @pytest.mark.asyncio
    async def test_webhook_no_url(self):
        alert = _make_alert()
        ch = _make_channel("webhook", config={})
        result = await _send_webhook(alert, ch, None, {})
        assert result is None

    @pytest.mark.asyncio
    async def test_webhook_with_template(self):
        alert = _make_alert()
        ch = _make_channel("webhook", config={"url": "http://example.com/hook"})
        tmpl = MagicMock()
        tmpl.subject_template = None
        tmpl.body_template = "Alert: {title}"
        with patch("app.services.notifier.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_client.post.return_value = mock_resp
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            code = await _send_webhook(alert, ch, tmpl, {"title": "CPU"})
            assert code == 200

    @pytest.mark.asyncio
    async def test_webhook_without_template(self):
        alert = _make_alert()
        ch = _make_channel("webhook", config={"url": "http://example.com/hook"})
        with patch("app.services.notifier.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_client.post.return_value = mock_resp
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            code = await _send_webhook(alert, ch, None, _build_template_vars(alert))
            assert code == 200


class TestSendDingtalk:
    @pytest.mark.asyncio
    async def test_dingtalk_no_url(self):
        result = await _send_dingtalk(_make_alert(), _make_channel("dingtalk", {}), None, {})
        assert result is None

    @pytest.mark.asyncio
    async def test_dingtalk_with_secret(self):
        ch = _make_channel("dingtalk", {"webhook_url": "http://ding.test/hook", "secret": "sec123"})
        with patch("app.services.notifier.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_client.post.return_value = mock_resp
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            code = await _send_dingtalk(_make_alert(), ch, None, {"title": "t", "severity": "w", "message": "m", "fired_at": "f"})
            assert code == 200


class TestSendFeishu:
    @pytest.mark.asyncio
    async def test_feishu_no_url(self):
        result = await _send_feishu(_make_alert(), _make_channel("feishu", {}), None, {})
        assert result is None

    @pytest.mark.asyncio
    async def test_feishu_with_secret(self):
        ch = _make_channel("feishu", {"webhook_url": "http://feishu.test/hook", "secret": "sec"})
        with patch("app.services.notifier.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_client.post.return_value = mock_resp
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            code = await _send_feishu(_make_alert(), ch, None, {"title": "t", "severity": "w", "message": "m", "fired_at": "f"})
            assert code == 200


class TestSendWecom:
    @pytest.mark.asyncio
    async def test_wecom_no_url(self):
        result = await _send_wecom(_make_alert(), _make_channel("wecom", {}), None, {})
        assert result is None

    @pytest.mark.asyncio
    async def test_wecom_success(self):
        ch = _make_channel("wecom", {"webhook_url": "http://wecom.test/hook"})
        with patch("app.services.notifier.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_client.post.return_value = mock_resp
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            code = await _send_wecom(_make_alert(), ch, None, {"title": "t", "severity": "w", "message": "m", "fired_at": "f"})
            assert code == 200


class TestSendEmail:
    @pytest.mark.asyncio
    async def test_email_no_recipients(self):
        ch = _make_channel("email", {"smtp_host": "smtp.test", "recipients": []})
        result = await _send_email(_make_alert(), ch, None, {})
        assert result is None

    @pytest.mark.asyncio
    async def test_email_success(self):
        ch = _make_channel("email", {
            "smtp_host": "smtp.test", "smtp_port": 465, "smtp_user": "u@t.com",
            "smtp_password": "pass", "smtp_ssl": True, "recipients": ["r@t.com"]
        })
        with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
            code = await _send_email(
                _make_alert(), ch, None,
                {"title": "t", "severity": "w", "message": "m", "metric_value": "90",
                 "threshold": "80", "host_id": "1", "fired_at": "2026-01-01"}
            )
            assert code == 200
            mock_send.assert_called_once()


class TestSendAlertNotification:
    """Test the main send_alert_notification function with silence/cooldown."""

    @pytest.mark.asyncio
    async def test_silence_window_blocks(self, db_session):
        """Alert within silence window should be suppressed."""
        from app.models.alert import AlertRule, Alert as AlertModel
        now = datetime.now()
        rule = AlertRule(
            name="test-rule", metric="cpu_percent", operator=">",
            threshold=80, severity="warning",
            silence_start=dt_time(0, 0), silence_end=dt_time(23, 59),
            cooldown_seconds=0,
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        alert = AlertModel(
            rule_id=rule.id, host_id=1, severity="warning", status="firing",
            title="CPU High", message="cpu=90"
        )
        db_session.add(alert)
        await db_session.commit()
        await db_session.refresh(alert)

        # Should be silenced, not raise any error
        from conftest import fake_redis
        with patch("app.services.notifier.get_redis", new_callable=AsyncMock, return_value=fake_redis):
            await send_alert_notification(db_session, alert)

    @pytest.mark.asyncio
    async def test_cooldown_blocks_second_alert(self, db_session):
        """Second alert within cooldown should be suppressed."""
        from app.models.alert import AlertRule, Alert as AlertModel
        rule = AlertRule(
            name="test-rule2", metric="cpu_percent", operator=">",
            threshold=80, severity="warning", cooldown_seconds=300,
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        alert = AlertModel(
            rule_id=rule.id, host_id=1, severity="warning", status="firing",
            title="CPU High", message="cpu=90"
        )
        db_session.add(alert)
        await db_session.commit()
        await db_session.refresh(alert)

        from conftest import fake_redis
        # Set cooldown key
        await fake_redis.set(f"alert:cooldown:{rule.id}", "1")

        with patch("app.services.notifier.get_redis", new_callable=AsyncMock, return_value=fake_redis):
            await send_alert_notification(db_session, alert)
            # Check cooldown count incremented
            count = await fake_redis.get(f"alert:cooldown:count:{rule.id}")
            assert count == "1"

        # Cleanup
        await fake_redis.delete(f"alert:cooldown:{rule.id}", f"alert:cooldown:count:{rule.id}")


class TestSendRemediationNotification:
    @pytest.mark.asyncio
    async def test_send_remediation_success(self, db_session):
        from app.models.notification import NotificationChannel
        ch = NotificationChannel(
            name="test-webhook", type="webhook",
            config={"url": "http://example.com/hook"}, is_enabled=True
        )
        db_session.add(ch)
        await db_session.commit()

        with patch("app.services.notifier.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_client.post.return_value = mock_resp
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            await send_remediation_notification(
                db_session, kind="success",
                alert_name="CPU High", host="web-01",
                runbook="restart", duration="10s"
            )

    @pytest.mark.asyncio
    async def test_send_remediation_failure_kind(self, db_session):
        await send_remediation_notification(
            db_session, kind="failure",
            alert_name="Disk Full", host="db-01", reason="no space"
        )

    @pytest.mark.asyncio
    async def test_send_remediation_approval_kind(self, db_session):
        await send_remediation_notification(
            db_session, kind="approval",
            alert_name="Mem", host="h1", action="restart", approval_url="http://approve"
        )


class TestGetDefaultTemplate:
    @pytest.mark.asyncio
    async def test_no_template(self, db_session):
        tmpl = await _get_default_template(db_session, "webhook")
        assert tmpl is None

    @pytest.mark.asyncio
    async def test_specific_template(self, db_session):
        from app.models.notification_template import NotificationTemplate
        t = NotificationTemplate(
            name="webhook-default", channel_type="webhook", is_default=True,
            body_template="Alert: {title}", subject_template=None
        )
        db_session.add(t)
        await db_session.commit()
        tmpl = await _get_default_template(db_session, "webhook")
        assert tmpl is not None
        assert tmpl.name == "webhook-default"

    @pytest.mark.asyncio
    async def test_fallback_to_all(self, db_session):
        from app.models.notification_template import NotificationTemplate
        t = NotificationTemplate(
            name="all-default", channel_type="all", is_default=True,
            body_template="Alert: {title}", subject_template=None
        )
        db_session.add(t)
        await db_session.commit()
        tmpl = await _get_default_template(db_session, "dingtalk")
        assert tmpl is not None
        assert tmpl.channel_type == "all"
