"""异常扫描服务深度测试。"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

from app.models.log_entry import LogEntry
from app.models.ai_insight import AIInsight
from app.services.anomaly_scanner import scan_recent_logs


class TestScanRecentLogs:
    @pytest.mark.asyncio
    async def test_no_logs(self, db_session):
        with patch("app.services.anomaly_scanner.async_session") as mock_sess:
            mock_sess.return_value.__aenter__ = AsyncMock(return_value=db_session)
            mock_sess.return_value.__aexit__ = AsyncMock(return_value=False)
            await scan_recent_logs(hours=1)
            # No insight should be created
            from sqlalchemy import select
            result = await db_session.execute(select(AIInsight))
            assert result.scalars().all() == []

    @pytest.mark.asyncio
    async def test_with_error_logs(self, db_session):
        # Add recent error logs
        now = datetime.now(timezone.utc)
        for i in range(3):
            db_session.add(LogEntry(
                host_id=1, service="api", level="ERROR",
                message=f"Connection refused {i}",
                timestamp=now - timedelta(minutes=i + 1),
            ))
        await db_session.commit()

        ai_result = {
            "severity": "warning",
            "title": "Connection errors detected",
            "summary": "Multiple connection refused",
            "anomalies": [],
            "overall_assessment": "needs attention",
        }
        with patch("app.services.anomaly_scanner.async_session") as mock_sess:
            mock_sess.return_value.__aenter__ = AsyncMock(return_value=db_session)
            mock_sess.return_value.__aexit__ = AsyncMock(return_value=False)
            with patch("app.services.anomaly_scanner.analyze_logs_brief", new_callable=AsyncMock, return_value=ai_result):
                await scan_recent_logs(hours=1)

        from sqlalchemy import select
        result = await db_session.execute(select(AIInsight))
        insights = result.scalars().all()
        assert len(insights) == 1
        assert insights[0].title == "Connection errors detected"

    @pytest.mark.asyncio
    async def test_ai_error_no_insight_saved(self, db_session):
        now = datetime.now(timezone.utc)
        db_session.add(LogEntry(
            host_id=1, service="app", level="WARN",
            message="slow query", timestamp=now - timedelta(minutes=5),
        ))
        await db_session.commit()

        with patch("app.services.anomaly_scanner.async_session") as mock_sess:
            mock_sess.return_value.__aenter__ = AsyncMock(return_value=db_session)
            mock_sess.return_value.__aexit__ = AsyncMock(return_value=False)
            with patch("app.services.anomaly_scanner.analyze_logs_brief", new_callable=AsyncMock, return_value={"error": True, "summary": "failed"}):
                await scan_recent_logs(hours=1)

        from sqlalchemy import select
        result = await db_session.execute(select(AIInsight))
        assert result.scalars().all() == []

    @pytest.mark.asyncio
    async def test_exception_handled(self, db_session):
        """scan_recent_logs should not raise even if DB fails."""
        with patch("app.services.anomaly_scanner.async_session") as mock_sess:
            mock_sess.return_value.__aenter__ = AsyncMock(side_effect=Exception("db down"))
            mock_sess.return_value.__aexit__ = AsyncMock(return_value=False)
            await scan_recent_logs(hours=1)  # should not raise
