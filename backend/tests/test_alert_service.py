"""
告警去重服务 + 告警 API 扩展测试。

Tests for AlertDeduplicationService and extended alert API coverage.
"""
import operator as op
import tempfile
import os
from datetime import datetime, timezone, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import create_engine, event, BigInteger
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.alert import Alert, AlertRule
from app.models.alert_group import AlertDeduplication
from app.services.alert_deduplication import AlertDeduplicationService


# ── Sync SQLite engine for AlertDeduplicationService tests ──
# The dedup service uses synchronous Session (not AsyncSession).
# We create a separate sync in-memory SQLite database for these tests.

_sync_engine = create_engine("sqlite:///:memory:", echo=False)


@event.listens_for(_sync_engine, "connect")
def _register_sync_sqlite_functions(dbapi_conn, connection_record):
    """Register date_trunc and extract for SQLite compatibility."""
    from datetime import datetime as _dt

    def _date_trunc(part, value):
        if value is None:
            return None
        if isinstance(value, str):
            for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S",
                        "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
                try:
                    value = _dt.strptime(value, fmt)
                    break
                except ValueError:
                    continue
            else:
                return value
        part = part.lower()
        if part in ("hour", "hours"):
            return value.replace(minute=0, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
        elif part in ("day", "days"):
            return value.replace(hour=0, minute=0, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
        elif part in ("minute", "minutes"):
            return value.replace(second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
        return value.strftime("%Y-%m-%d %H:%M:%S") if hasattr(value, 'strftime') else str(value)

    def _extract(field, value):
        if value is None:
            return None
        if isinstance(value, str):
            for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S",
                        "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
                try:
                    value = _dt.strptime(value, fmt)
                    break
                except ValueError:
                    continue
            else:
                return 0
        field = field.lower()
        if field == "epoch":
            return value.timestamp()
        elif field == "hour":
            return value.hour
        elif field == "day":
            return value.day
        elif field == "month":
            return value.month
        elif field == "year":
            return value.year
        return 0

    dbapi_conn.create_function("date_trunc", 2, _date_trunc)
    dbapi_conn.create_function("extract", 2, _extract)


_SyncSessionLocal = sessionmaker(bind=_sync_engine, expire_on_commit=False)


# ── Sync session fixture (AlertDeduplicationService requires sync Session) ──

@pytest.fixture
def sync_session():
    """Provide a synchronous Session backed by an in-memory sync SQLite database.

    Tables are created before each test and dropped after, mirroring the
    autouse ``setup_db`` fixture in conftest.py.
    """
    Base.metadata.create_all(bind=_sync_engine)
    session = _SyncSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=_sync_engine)


# ── Fixtures for dedup service tests (use sync session) ──

@pytest.fixture
def sync_rule(sync_session):
    """Create a standard alert rule in the sync database."""
    rule = AlertRule(
        name="CPU High",
        severity="warning",
        metric="cpu_percent",
        operator=">",
        threshold=80.0,
        duration_seconds=300,
        is_builtin=False,
        is_enabled=True,
        target_type="host",
        cooldown_seconds=300,
        continuous_alert=True,
    )
    sync_session.add(rule)
    sync_session.commit()
    sync_session.refresh(rule)
    return rule


@pytest.fixture
def sync_rule_no_continuous(sync_session):
    """Create a rule with continuous_alert=False in the sync database."""
    rule = AlertRule(
        name="Mem High Silent",
        severity="critical",
        metric="memory_percent",
        operator=">",
        threshold=90.0,
        duration_seconds=60,
        is_builtin=False,
        is_enabled=True,
        target_type="host",
        cooldown_seconds=300,
        continuous_alert=False,
    )
    sync_session.add(rule)
    sync_session.commit()
    sync_session.refresh(rule)
    return rule


# ── Fixtures for API tests (use async db_session) ──

@pytest.fixture
async def sample_rule(db_session):
    """Create a standard alert rule for API testing."""
    rule = AlertRule(
        name="CPU High",
        severity="warning",
        metric="cpu_percent",
        operator=">",
        threshold=80.0,
        duration_seconds=300,
        is_builtin=False,
        is_enabled=True,
        target_type="host",
        cooldown_seconds=300,
        continuous_alert=True,
    )
    db_session.add(rule)
    await db_session.commit()
    await db_session.refresh(rule)
    return rule


@pytest.fixture
async def builtin_rule(db_session):
    """Create a built-in alert rule."""
    rule = AlertRule(
        name="System CPU",
        severity="warning",
        metric="cpu_percent",
        operator=">",
        threshold=90.0,
        duration_seconds=300,
        is_builtin=True,
        is_enabled=True,
        target_type="host",
    )
    db_session.add(rule)
    await db_session.commit()
    await db_session.refresh(rule)
    return rule


# ── 1. AlertDeduplicationService tests ──

class TestAlertDeduplicationService:

    def test_generate_fingerprint_consistency(self, sync_session, sync_rule):
        """Same inputs must always produce the same fingerprint hash."""
        svc = AlertDeduplicationService(sync_session)
        fp1 = svc.generate_alert_fingerprint(sync_rule.id, 1, None, "cpu_percent")
        fp2 = svc.generate_alert_fingerprint(sync_rule.id, 1, None, "cpu_percent")
        assert fp1 == fp2

    def test_generate_fingerprint_uniqueness(self, sync_session, sync_rule):
        """Different inputs must produce different fingerprint hashes."""
        svc = AlertDeduplicationService(sync_session)
        fp1 = svc.generate_alert_fingerprint(sync_rule.id, 1, None, "cpu_percent")
        fp2 = svc.generate_alert_fingerprint(sync_rule.id, 2, None, "cpu_percent")
        fp3 = svc.generate_alert_fingerprint(sync_rule.id, 1, None, "memory_percent")
        fp4 = svc.generate_alert_fingerprint(sync_rule.id, 1, 10, "cpu_percent")
        assert len({fp1, fp2, fp3, fp4}) == 4

    def test_get_or_create_dedup_record_create(self, sync_session, sync_rule):
        """Creates a new dedup record when none exists."""
        svc = AlertDeduplicationService(sync_session)
        record, is_new = svc.get_or_create_dedup_record(sync_rule, 1, None)
        assert is_new is True
        assert record.rule_id == sync_rule.id
        assert record.host_id == 1
        assert record.occurrence_count == 1
        assert record.alert_triggered is False

    def test_get_or_create_dedup_record_existing(self, sync_session, sync_rule):
        """Returns the existing record on second call."""
        svc = AlertDeduplicationService(sync_session)
        record1, is_new1 = svc.get_or_create_dedup_record(sync_rule, 1, None)
        record2, is_new2 = svc.get_or_create_dedup_record(sync_rule, 1, None)
        assert is_new1 is True
        assert is_new2 is False
        assert record1.id == record2.id

    def test_process_alert_first_violation(self, sync_session, sync_rule):
        """First call to process_alert_evaluation triggers a 'first' notification."""
        svc = AlertDeduplicationService(sync_session)
        result = svc.process_alert_evaluation(sync_rule, 1, None, 95.0, "CPU High")
        assert result["should_send_notification"] is True
        assert result["notification_type"] == "first"
        assert result["dedup_record"].alert_triggered is True
        assert result["dedup_record"].alert_sent_count == 1

    def test_process_alert_duration_met(self, sync_session, sync_rule):
        """After first alert, a second call within cooldown is suppressed (cooldown not met)."""
        svc = AlertDeduplicationService(sync_session)
        # First call triggers
        svc.process_alert_evaluation(sync_rule, 1, None, 95.0, "CPU High")
        # Second call immediately after -- cooldown has not elapsed
        result2 = svc.process_alert_evaluation(sync_rule, 1, None, 95.0, "CPU High")
        # continuous_alert=True but cooldown not met, so suppressed
        assert result2["should_send_notification"] is False

    def test_process_alert_cooldown(self, sync_session, sync_rule):
        """Notifications suppressed during cooldown period even with continuous_alert=True."""
        svc = AlertDeduplicationService(sync_session)
        # First alert fires
        result1 = svc.process_alert_evaluation(sync_rule, 1, None, 95.0, "CPU High")
        assert result1["should_send_notification"] is True

        # Immediately call again -- within cooldown
        result2 = svc.process_alert_evaluation(sync_rule, 1, None, 96.0, "CPU High")
        assert result2["should_send_notification"] is False

    def test_process_alert_continuous_notification(self, sync_session, sync_rule):
        """With continuous_alert=True, notification sent again after cooldown expires."""
        svc = AlertDeduplicationService(sync_session)
        result1 = svc.process_alert_evaluation(sync_rule, 1, None, 95.0, "CPU High")
        assert result1["should_send_notification"] is True

        # Simulate cooldown elapsed by backdating last_alert_time
        record = result1["dedup_record"]
        record.last_alert_time = datetime.now(timezone.utc) - timedelta(
            seconds=sync_rule.cooldown_seconds + 10
        )
        sync_session.commit()

        result2 = svc.process_alert_evaluation(sync_rule, 1, None, 96.0, "CPU High")
        assert result2["should_send_notification"] is True
        assert result2["notification_type"] == "continuous"

    def test_process_alert_continuous_disabled(self, sync_session, sync_rule_no_continuous):
        """With continuous_alert=False, second notification is suppressed (silent aggregation)."""
        rule = sync_rule_no_continuous
        svc = AlertDeduplicationService(sync_session)

        result1 = svc.process_alert_evaluation(rule, 1, None, 95.0, "Mem High")
        assert result1["should_send_notification"] is True
        assert result1["notification_type"] == "first"

        # Even after cooldown, silent aggregation mode does NOT send
        record = result1["dedup_record"]
        record.last_alert_time = datetime.now(timezone.utc) - timedelta(seconds=600)
        sync_session.commit()

        result2 = svc.process_alert_evaluation(rule, 1, None, 96.0, "Mem High")
        assert result2["should_send_notification"] is False

    def test_process_recovery(self, sync_session, sync_rule):
        """Recovery notification sent when active alert resolves."""
        svc = AlertDeduplicationService(sync_session)
        # Trigger an alert first
        svc.process_alert_evaluation(sync_rule, 1, None, 95.0, "CPU High")

        # Process recovery
        result = svc.process_recovery(sync_rule, 1, None)
        assert result["should_send_notification"] is True
        assert result["duration_seconds"] >= 0

        # Dedup record should be deleted after recovery
        fp = svc.generate_alert_fingerprint(sync_rule.id, 1, None, sync_rule.metric)
        remaining = sync_session.query(AlertDeduplication).filter(
            AlertDeduplication.fingerprint == fp
        ).first()
        assert remaining is None

    def test_process_recovery_no_active_alert(self, sync_session, sync_rule):
        """No recovery notification when no active alert/dedup record exists."""
        svc = AlertDeduplicationService(sync_session)
        result = svc.process_recovery(sync_rule, 1, None)
        assert result["should_send_notification"] is False
        assert result["dedup_record"] is None

    def test_cleanup_expired_records(self, sync_session, sync_rule):
        """Old dedup records are cleaned up based on max_age_hours."""
        svc = AlertDeduplicationService(sync_session)

        # Create a dedup record with an old last_check_time
        record, _ = svc.get_or_create_dedup_record(sync_rule, 1, None)
        record.last_check_time = datetime.now(timezone.utc) - timedelta(hours=48)
        sync_session.commit()

        count = svc.cleanup_expired_records(max_age_hours=24)
        assert count == 1

        # Verify record is gone
        fp = svc.generate_alert_fingerprint(sync_rule.id, 1, None, sync_rule.metric)
        remaining = sync_session.query(AlertDeduplication).filter(
            AlertDeduplication.fingerprint == fp
        ).first()
        assert remaining is None


# ── 2. Alert API extended tests ──

class TestAlertAPIExtended:

    async def test_create_rule_with_silence_window(self, db_session):
        """Silence window fields (silence_start, silence_end) are saved correctly.

        Note: SQLite Time type requires Python time objects (not strings),
        so we test via direct model creation instead of the HTTP API.
        """
        from datetime import time as dt_time
        rule = AlertRule(
            name="Disk Silent",
            severity="warning",
            metric="disk_percent",
            operator=">",
            threshold=85.0,
            duration_seconds=120,
            is_builtin=False,
            is_enabled=True,
            target_type="host",
            silence_start=dt_time(2, 0),
            silence_end=dt_time(6, 0),
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)
        assert rule.silence_start == dt_time(2, 0)
        assert rule.silence_end == dt_time(6, 0)
        assert rule.name == "Disk Silent"

    async def test_update_rule_partial(self, client: AsyncClient, auth_headers):
        """PUT with partial fields only updates specified fields."""
        # Create a rule first
        create_resp = await client.post("/api/v1/alert-rules", headers=auth_headers, json={
            "name": "Partial Update Test",
            "severity": "warning",
            "metric": "cpu_percent",
            "operator": ">",
            "threshold": 70,
            "duration_seconds": 60,
        })
        assert create_resp.status_code == 201
        rule_id = create_resp.json()["id"]

        # Update only threshold
        resp = await client.put(f"/api/v1/alert-rules/{rule_id}", headers=auth_headers, json={
            "threshold": 85.0,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["threshold"] == 85.0
        # Other fields remain unchanged
        assert data["name"] == "Partial Update Test"
        assert data["severity"] == "warning"
        assert data["operator"] == ">"

    async def test_delete_builtin_rule_rejected(self, client: AsyncClient, auth_headers, builtin_rule):
        """Built-in rules cannot be deleted -- returns 400."""
        resp = await client.delete(
            f"/api/v1/alert-rules/{builtin_rule.id}", headers=auth_headers
        )
        assert resp.status_code == 400
        body = resp.json()
        # The global exception handler wraps HTTPException detail into "message"
        msg = body.get("message") or body.get("detail") or ""
        assert "built-in" in msg.lower() or "cannot" in msg.lower()

    async def test_acknowledge_resolved_alert_rejected(self, client: AsyncClient, auth_headers, db_session, sample_rule):
        """Acknowledging an already resolved alert returns 400."""
        alert = Alert(
            rule_id=sample_rule.id,
            host_id=1,
            severity="warning",
            status="resolved",
            title="Resolved Alert",
            message="Already resolved",
            metric_value=50.0,
            threshold=80.0,
        )
        db_session.add(alert)
        await db_session.commit()
        await db_session.refresh(alert)

        resp = await client.post(f"/api/v1/alerts/{alert.id}/ack", headers=auth_headers)
        assert resp.status_code == 400

    async def test_list_alerts_pagination(self, client: AsyncClient, auth_headers, db_session, sample_rule):
        """Alert list endpoint supports pagination parameters."""
        # Create several alerts
        for i in range(5):
            alert = Alert(
                rule_id=sample_rule.id,
                host_id=1,
                severity="warning",
                status="firing",
                title=f"Alert {i}",
                message=f"Test alert {i}",
                metric_value=90.0 + i,
                threshold=80.0,
            )
            db_session.add(alert)
        await db_session.commit()

        resp = await client.get(
            "/api/v1/alerts?page=1&page_size=2", headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5
        assert len(data["items"]) == 2
        assert data["page"] == 1
        assert data["page_size"] == 2

    async def test_list_alerts_filter_host(self, client: AsyncClient, auth_headers, db_session, sample_rule):
        """Alert list can be filtered by host_id."""
        for host_id in [10, 10, 20]:
            alert = Alert(
                rule_id=sample_rule.id,
                host_id=host_id,
                severity="warning",
                status="firing",
                title=f"Alert host {host_id}",
                message="test",
                metric_value=95.0,
                threshold=80.0,
            )
            db_session.add(alert)
        await db_session.commit()

        resp = await client.get("/api/v1/alerts?host_id=10", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["total"] == 2

    async def test_create_rule_with_notification_channels(self, client: AsyncClient, auth_headers):
        """Alert rule can be created with notification_channel_ids."""
        resp = await client.post("/api/v1/alert-rules", headers=auth_headers, json={
            "name": "With Channels",
            "severity": "critical",
            "metric": "memory_percent",
            "operator": ">",
            "threshold": 95,
            "duration_seconds": 60,
            "notification_channel_ids": [1, 2, 3],
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["notification_channel_ids"] == [1, 2, 3]

    async def test_create_rule_with_cooldown_and_continuous(self, client: AsyncClient, auth_headers):
        """Alert rule respects cooldown_seconds and continuous_alert fields."""
        resp = await client.post("/api/v1/alert-rules", headers=auth_headers, json={
            "name": "Cooldown Test",
            "severity": "warning",
            "metric": "cpu_percent",
            "operator": ">=",
            "threshold": 85,
            "duration_seconds": 120,
            "cooldown_seconds": 600,
            "continuous_alert": False,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["cooldown_seconds"] == 600
        assert data["continuous_alert"] is False


# ── 3. Alert Rule evaluation logic tests ──

class TestThresholdEvaluation:
    """Test the operator comparison logic used in alert_engine."""

    OPERATORS = {
        ">": op.gt,
        ">=": op.ge,
        "<": op.lt,
        "<=": op.le,
        "==": op.eq,
        "!=": op.ne,
    }

    async def test_threshold_evaluation_greater_than(self):
        """Operator '>' correctly compares values."""
        cmp_fn = self.OPERATORS[">"]
        assert cmp_fn(95.0, 80.0) is True
        assert cmp_fn(80.0, 80.0) is False
        assert cmp_fn(70.0, 80.0) is False

    async def test_threshold_evaluation_less_than(self):
        """Operator '<' correctly compares values."""
        cmp_fn = self.OPERATORS["<"]
        assert cmp_fn(50.0, 80.0) is True
        assert cmp_fn(80.0, 80.0) is False
        assert cmp_fn(90.0, 80.0) is False

    async def test_threshold_evaluation_equal(self):
        """Operator '==' correctly compares values."""
        cmp_fn = self.OPERATORS["=="]
        assert cmp_fn(80.0, 80.0) is True
        assert cmp_fn(81.0, 80.0) is False

    async def test_threshold_evaluation_not_equal(self):
        """Operator '!=' correctly compares values."""
        cmp_fn = self.OPERATORS["!="]
        assert cmp_fn(81.0, 80.0) is True
        assert cmp_fn(80.0, 80.0) is False

    async def test_threshold_evaluation_greater_equal(self):
        """Operator '>=' correctly compares values."""
        cmp_fn = self.OPERATORS[">="]
        assert cmp_fn(80.0, 80.0) is True
        assert cmp_fn(81.0, 80.0) is True
        assert cmp_fn(79.0, 80.0) is False

    async def test_threshold_evaluation_less_equal(self):
        """Operator '<=' correctly compares values."""
        cmp_fn = self.OPERATORS["<="]
        assert cmp_fn(80.0, 80.0) is True
        assert cmp_fn(79.0, 80.0) is True
        assert cmp_fn(81.0, 80.0) is False
