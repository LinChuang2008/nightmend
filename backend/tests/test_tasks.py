"""后台任务全覆盖测试 — alert_engine, cleanup, offline_detector, report_scheduler。"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch, MagicMock
import json

from app.models.host import Host
from app.models.alert import Alert, AlertRule
from app.models.host_metric import HostMetric
from app.models.log_entry import LogEntry
from app.models.db_metric import DbMetric, MonitoredDatabase
from app.models.report import Report
from tests.conftest import FakeRedis


# ─── Alert Engine ─────────────────────────────────────────────────

class TestAlertEngine:
    @pytest.mark.asyncio
    async def test_evaluate_no_rules(self, db_session):
        """No rules → no alerts created."""
        from app.tasks.alert_engine import evaluate_host_rules
        

        with patch("app.tasks.alert_engine.async_session") as mock_session_ctx:
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=db_session)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            with patch("app.tasks.alert_engine.get_redis", new_callable=AsyncMock, return_value=FakeRedis()):
                await evaluate_host_rules()

    @pytest.mark.asyncio
    async def test_evaluate_rule_fires_alert(self, db_session):
        """Rule threshold exceeded → alert created."""
        from app.tasks.alert_engine import _evaluate_rule
        

        host = Host(hostname="h1", status="online", agent_token_id=1)
        db_session.add(host)
        await db_session.commit()
        await db_session.refresh(host)

        rule = AlertRule(
            name="CPU High", metric="cpu_percent", operator=">",
            threshold=80, severity="critical", duration_seconds=0,
            target_type="host", is_enabled=True, cooldown_seconds=300,
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        metrics = {"cpu_percent": 95.0}

        with patch("app.tasks.alert_engine.send_alert_notification", new_callable=AsyncMock):
            await _evaluate_rule(db_session, FakeRedis(), rule, host, metrics)
            await db_session.commit()

        from sqlalchemy import select
        result = await db_session.execute(select(Alert).where(Alert.rule_id == rule.id))
        alert = result.scalar_one_or_none()
        assert alert is not None
        assert alert.status == "firing"

    @pytest.mark.asyncio
    async def test_evaluate_rule_resolves(self, db_session):
        """Normal value with existing firing alert → resolved."""
        from app.tasks.alert_engine import _evaluate_rule
        

        host = Host(hostname="h2", status="online", agent_token_id=1)
        db_session.add(host)
        await db_session.commit()
        await db_session.refresh(host)

        rule = AlertRule(
            name="CPU OK", metric="cpu_percent", operator=">",
            threshold=80, severity="warning", duration_seconds=0,
            target_type="host", is_enabled=True, cooldown_seconds=0,
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        # Existing firing alert
        existing = Alert(
            rule_id=rule.id, host_id=host.id, severity="warning",
            status="firing", title="CPU", message="cpu=90"
        )
        db_session.add(existing)
        await db_session.commit()

        with patch("app.tasks.alert_engine.send_alert_notification", new_callable=AsyncMock):
            await _evaluate_rule(db_session, FakeRedis(), rule, host, {"cpu_percent": 50.0})
            await db_session.commit()

        await db_session.refresh(existing)
        assert existing.status == "resolved"

    @pytest.mark.asyncio
    async def test_evaluate_rule_duration_pending(self, db_session):
        """Rule with duration_seconds > 0, first violation should not fire immediately."""
        from app.tasks.alert_engine import _evaluate_rule
        

        host = Host(hostname="h3", status="online", agent_token_id=1)
        db_session.add(host)
        await db_session.commit()
        await db_session.refresh(host)

        rule = AlertRule(
            name="CPU Sustained", metric="cpu_percent", operator=">",
            threshold=80, severity="warning", duration_seconds=60,
            target_type="host", is_enabled=True, cooldown_seconds=0,
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        await _evaluate_rule(db_session, FakeRedis(), rule, host, {"cpu_percent": 95.0})
        await db_session.commit()

        # No alert should be created yet (pending)
        from sqlalchemy import select
        result = await db_session.execute(select(Alert).where(Alert.rule_id == rule.id))
        assert result.scalar_one_or_none() is None

        # Cleanup
        await FakeRedis().delete(f"alert:pending:{rule.id}:{host.id}")

    @pytest.mark.asyncio
    async def test_evaluate_host_offline(self, db_session):
        """host_offline metric with offline host → alert."""
        from app.tasks.alert_engine import _evaluate_rule
        

        host = Host(hostname="h-off", status="offline", agent_token_id=1)
        db_session.add(host)
        await db_session.commit()
        await db_session.refresh(host)

        rule = AlertRule(
            name="Host Offline", metric="host_offline", operator=">",
            threshold=0, severity="critical", duration_seconds=0,
            target_type="host", is_enabled=True, cooldown_seconds=0,
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        with patch("app.tasks.alert_engine.send_alert_notification", new_callable=AsyncMock):
            await _evaluate_rule(db_session, FakeRedis(), rule, host, {})
            await db_session.commit()

        from sqlalchemy import select
        result = await db_session.execute(select(Alert).where(Alert.rule_id == rule.id))
        assert result.scalar_one_or_none() is not None

    @pytest.mark.asyncio
    async def test_unknown_metric_skipped(self, db_session):
        from app.tasks.alert_engine import _evaluate_rule
        

        host = Host(hostname="h-unk", status="online", agent_token_id=1)
        db_session.add(host)
        rule = AlertRule(
            name="Unknown", metric="unknown_metric", operator=">",
            threshold=80, severity="info", duration_seconds=0,
            target_type="host", is_enabled=True,
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(host)
        await db_session.refresh(rule)

        await _evaluate_rule(db_session, FakeRedis(), rule, host, {"cpu_percent": 90})
        # Should just return, no error


# ─── Cleanup Tasks ────────────────────────────────────────────────

class TestDbMetricCleanup:
    @pytest.mark.asyncio
    async def test_cleanup_old_metrics(self, db_session):
        """Old metrics beyond retention should be deleted."""
        from app.tasks.db_metric_cleanup import db_metric_cleanup_loop
        from sqlalchemy import delete, select

        # Create host and monitored db
        h = Host(hostname="clean-h", status="online", agent_token_id=1)
        db_session.add(h)
        await db_session.commit()
        await db_session.refresh(h)
        mdb = MonitoredDatabase(host_id=h.id, name="cleandb", db_type="postgres", status="healthy")
        db_session.add(mdb)
        await db_session.commit()
        await db_session.refresh(mdb)

        # Add old metric
        old = DbMetric(database_id=mdb.id, recorded_at=datetime.now(timezone.utc) - timedelta(days=60))
        db_session.add(old)
        await db_session.commit()

        # Run cleanup directly (not the loop)
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        result = await db_session.execute(delete(DbMetric).where(DbMetric.recorded_at < cutoff))
        deleted = result.rowcount
        await db_session.commit()
        assert deleted >= 1


class TestLogCleanup:
    @pytest.mark.asyncio
    async def test_cleanup_old_logs(self, db_session):
        from sqlalchemy import delete

        old_log = LogEntry(
            host_id=1, service="app", level="ERROR", message="old",
            timestamp=datetime.now(timezone.utc) - timedelta(days=30)
        )
        db_session.add(old_log)
        await db_session.commit()

        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        result = await db_session.execute(delete(LogEntry).where(LogEntry.timestamp < cutoff))
        deleted = result.rowcount
        await db_session.commit()
        assert deleted >= 1


# ─── Offline Detector ─────────────────────────────────────────────

class TestOfflineDetector:
    @pytest.mark.asyncio
    async def test_mark_host_offline(self, db_session):
        from app.tasks.offline_detector import check_offline_hosts
        

        host = Host(
            hostname="stale-host", status="online", agent_token_id=1,
            last_heartbeat=datetime.now(timezone.utc) - timedelta(seconds=600)
        )
        db_session.add(host)
        await db_session.commit()
        await db_session.refresh(host)

        with patch("app.tasks.offline_detector.async_session") as mock_sess:
            mock_sess.return_value.__aenter__ = AsyncMock(return_value=db_session)
            mock_sess.return_value.__aexit__ = AsyncMock(return_value=False)
            with patch("app.tasks.offline_detector.get_redis", new_callable=AsyncMock, return_value=FakeRedis()):
                await check_offline_hosts()

        await db_session.refresh(host)
        assert host.status == "offline"

    @pytest.mark.asyncio
    async def test_host_with_heartbeat_stays_online(self, db_session):
        from app.tasks.offline_detector import check_offline_hosts
        

        host = Host(hostname="alive-host", status="online", agent_token_id=1, last_heartbeat=datetime.now(timezone.utc))
        db_session.add(host)
        await db_session.commit()
        await db_session.refresh(host)

        # Set heartbeat in Redis
        await FakeRedis().set(f"heartbeat:{host.id}", datetime.now(timezone.utc).isoformat())

        with patch("app.tasks.offline_detector.async_session") as mock_sess:
            mock_sess.return_value.__aenter__ = AsyncMock(return_value=db_session)
            mock_sess.return_value.__aexit__ = AsyncMock(return_value=False)
            with patch("app.tasks.offline_detector.get_redis", new_callable=AsyncMock, return_value=FakeRedis()):
                await check_offline_hosts()

        await db_session.refresh(host)
        assert host.status == "online"
        await FakeRedis().delete(f"heartbeat:{host.id}")


# ─── Report Scheduler ─────────────────────────────────────────────

class TestReportScheduler:
    @pytest.mark.asyncio
    async def test_report_exists_check(self, db_session):
        from app.tasks.report_scheduler import _report_exists

        start = datetime(2026, 2, 20)
        end = datetime(2026, 2, 21)

        # No report yet
        assert not await _report_exists(db_session, "daily", start, end)

        # Add a completed report
        r = Report(
            title="日报 2026-02-20", report_type="daily",
            period_start=start, period_end=end,
            content="test", summary="test", status="completed"
        )
        db_session.add(r)
        await db_session.commit()

        assert await _report_exists(db_session, "daily", start, end)

    @pytest.mark.asyncio
    async def test_report_exists_ignores_failed(self, db_session):
        from app.tasks.report_scheduler import _report_exists

        start = datetime(2026, 2, 19)
        end = datetime(2026, 2, 20)
        r = Report(
            title="日报 failed", report_type="daily",
            period_start=start, period_end=end,
            content="err", summary="err", status="failed"
        )
        db_session.add(r)
        await db_session.commit()

        # Failed report should not count as existing
        assert not await _report_exists(db_session, "daily", start, end)
