"""
SearchLogsTool — 搜索主机日志

迁移自 OpsAgentLoop._tool_search_logs。
按 host_id、关键字、日志级别和时间范围搜索日志条目。
默认搜索最近 1 小时内的日志，最多返回 50 条，按时间降序排列。
"""
from __future__ import annotations

from app.tools.base import OpsTool, RiskLevel, ToolEvent, ToolEventType


class SearchLogsTool(OpsTool):
    name = "search_logs"
    description = (
        "Search log entries for a specific host by keyword. "
        "Supports filtering by log level and time range. "
        "Returns timestamp, level, service, and message for each matching entry, "
        "plus total count. Returns an empty list if no logs match."
    )
    risk_level = RiskLevel.READ_ONLY

    @property
    def tags(self) -> list[str]:
        return ["monitoring", "logs"]

    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "host_id": {
                    "type": "integer",
                    "description": "The ID of the host to search logs for.",
                },
                "keyword": {
                    "type": "string",
                    "description": "Keyword to search for in log messages (substring match).",
                },
                "level": {
                    "type": "string",
                    "enum": ["DEBUG", "INFO", "WARN", "ERROR", "FATAL"],
                    "description": "Filter logs by level.",
                },
                "hours_back": {
                    "type": "number",
                    "default": 1,
                    "description": "How many hours back to search (default 1).",
                },
                "limit": {
                    "type": "integer",
                    "default": 50,
                    "description": "Maximum number of log entries to return (default 50).",
                },
            },
            "required": ["host_id", "keyword"],
        }

    async def execute(self, args: dict, context):
        from datetime import datetime, timedelta, timezone

        from sqlalchemy import select
        from app.models.log_entry import LogEntry

        host_id = args["host_id"]
        keyword = args["keyword"]
        hours_back = args.get("hours_back", 1)
        limit = args.get("limit", 50)

        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        query = (
            select(LogEntry)
            .where(LogEntry.host_id == host_id)
            .where(LogEntry.timestamp > cutoff)
            .where(LogEntry.message.contains(keyword))
        )

        if args.get("level"):
            query = query.where(LogEntry.level == args["level"])

        async with context.db_session_factory() as db:
            result = await db.execute(
                query.order_by(LogEntry.timestamp.desc()).limit(limit)
            )
            logs = result.scalars().all()

        yield ToolEvent(
            type=ToolEventType.RESULT,
            data={
                "logs": [
                    {
                        "timestamp": log.timestamp.isoformat(),
                        "level": log.level,
                        "service": log.service,
                        "message": log.message,
                    }
                    for log in logs
                ],
                "count": len(logs),
            },
        )
