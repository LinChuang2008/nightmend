"""报告生成服务深度测试 — mock DB 查询 + AI API。"""
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, patch

from app.services.report_generator import (
    generate_report,
    _collect_host_summary,
    _collect_service_summary,
    _collect_alert_summary,
    _collect_log_summary,
    _collect_db_summary,
)
from app.models.host import Host
from app.models.host_metric import HostMetric
from app.models.service import Service
from app.models.alert import Alert, AlertRule
from app.models.log_entry import LogEntry
from app.models.db_metric import MonitoredDatabase


@pytest.fixture
def period():
    start = datetime(2026, 2, 20, 0, 0, 0)
    end = datetime(2026, 2, 21, 0, 0, 0)
    return start, end


class TestCollectHostSummary:
    @pytest.mark.asyncio
    async def test_empty_db(self, db_session, period):
        result = await _collect_host_summary(db_session, *period)
        assert "主机总数: 0" in result

    @pytest.mark.asyncio
    async def test_with_hosts_and_metrics(self, db_session, period):
        h = Host(hostname="web-01", status="online", agent_token_id=1)
        db_session.add(h)
        await db_session.commit()
        await db_session.refresh(h)

        m = HostMetric(
            host_id=h.id, cpu_percent=50, memory_percent=60, disk_percent=40,
            recorded_at=datetime(2026, 2, 20, 12, 0, 0)
        )
        db_session.add(m)
        await db_session.commit()

        result = await _collect_host_summary(db_session, *period)
        assert "主机总数: 1" in result
        assert "在线: 1" in result
        assert "平均 CPU" in result

    @pytest.mark.asyncio
    async def test_no_metrics_in_range(self, db_session, period):
        h = Host(hostname="web-02", status="offline", agent_token_id=1)
        db_session.add(h)
        await db_session.commit()

        result = await _collect_host_summary(db_session, *period)
        assert "该时段无指标数据" in result


class TestCollectServiceSummary:
    @pytest.mark.asyncio
    async def test_empty(self, db_session):
        result = await _collect_service_summary(db_session)
        assert "服务总数: 0" in result

    @pytest.mark.asyncio
    async def test_with_services(self, db_session):
        db_session.add(Service(name="api", type="http", target="http://api", status="up"))
        db_session.add(Service(name="db", type="tcp", target="db:5432", status="down"))
        await db_session.commit()
        result = await _collect_service_summary(db_session)
        assert "服务总数: 2" in result
        assert "可用率: 50.0%" in result


class TestCollectAlertSummary:
    @pytest.mark.asyncio
    async def test_empty(self, db_session, period):
        result = await _collect_alert_summary(db_session, *period)
        assert "告警总数: 0" in result

    @pytest.mark.asyncio
    async def test_with_alerts(self, db_session, period):
        rule = AlertRule(name="r", metric="cpu_percent", operator=">", threshold=80, severity="warning")
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        a = Alert(
            rule_id=rule.id, host_id=1, severity="critical", status="firing",
            title="CPU", message="high", fired_at=datetime(2026, 2, 20, 12, 0, 0)
        )
        db_session.add(a)
        await db_session.commit()
        result = await _collect_alert_summary(db_session, *period)
        assert "告警总数: 1" in result
        assert "critical" in result


class TestCollectLogSummary:
    @pytest.mark.asyncio
    async def test_empty(self, db_session, period):
        result = await _collect_log_summary(db_session, *period)
        assert "无错误日志" in result

    @pytest.mark.asyncio
    async def test_with_errors(self, db_session, period):
        for i in range(3):
            db_session.add(LogEntry(
                host_id=1, service="api", level="ERROR",
                message=f"error {i}", timestamp=datetime(2026, 2, 20, 12, i, 0)
            ))
        await db_session.commit()
        result = await _collect_log_summary(db_session, *period)
        assert "错误日志总数: 3" in result
        assert "api" in result


class TestCollectDbSummary:
    @pytest.mark.asyncio
    async def test_empty(self, db_session):
        result = await _collect_db_summary(db_session)
        assert "未配置监控数据库" in result

    @pytest.mark.asyncio
    async def test_with_dbs(self, db_session):
        h = Host(hostname="db-host", status="online", agent_token_id=1)
        db_session.add(h)
        await db_session.commit()
        await db_session.refresh(h)
        db_session.add(MonitoredDatabase(host_id=h.id, name="mydb", db_type="postgres", status="healthy"))
        await db_session.commit()
        result = await _collect_db_summary(db_session)
        assert "监控数据库数量: 1" in result
        assert "mydb" in result


class TestGenerateReport:
    @pytest.mark.asyncio
    async def test_daily_report_success(self, db_session, period):
        ai_content = "# 日报\n内容\n【摘要】系统运行正常"
        with patch("app.services.report_generator.chat_completion", new_callable=AsyncMock, return_value=ai_content):
            report = await generate_report(db_session, "daily", period[0], period[1], generated_by=1)
            assert report.status == "completed"
            assert report.title.startswith("日报")
            assert "系统运行正常" in report.summary

    @pytest.mark.asyncio
    async def test_weekly_report_success(self, db_session):
        start = datetime(2026, 2, 14)
        end = datetime(2026, 2, 21)
        ai_content = "# 周报\n分析内容"
        with patch("app.services.report_generator.chat_completion", new_callable=AsyncMock, return_value=ai_content):
            report = await generate_report(db_session, "weekly", start, end)
            assert report.status == "completed"
            assert "周报" in report.title
            assert "..." in report.summary  # truncated since no 【摘要】

    @pytest.mark.asyncio
    async def test_report_ai_failure(self, db_session, period):
        with patch("app.services.report_generator.chat_completion", new_callable=AsyncMock, side_effect=Exception("AI down")):
            report = await generate_report(db_session, "daily", period[0], period[1])
            assert report.status == "failed"
            assert "AI down" in report.content
