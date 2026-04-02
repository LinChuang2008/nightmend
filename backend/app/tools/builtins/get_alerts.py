"""
GetAlertsTool — 查询活跃告警

迁移自 OpsAgentLoop._tool_get_alerts。
查询 status="firing" 的告警事件，支持按 host_id 和 severity 过滤，
按 fired_at 降序排列，默认返回最多 20 条。
"""
from __future__ import annotations

from app.tools.base import OpsTool, RiskLevel, ToolEvent, ToolEventType


class GetAlertsTool(OpsTool):
    name = "get_alerts"
    description = (
        "Get currently firing alerts, optionally filtered by host_id and severity. "
        "Returns alert id, title, severity, status, message, fired_at, and host_id. "
        "Only returns alerts with status='firing'. Returns an empty list if none match."
    )
    risk_level = RiskLevel.READ_ONLY

    @property
    def tags(self) -> list[str]:
        return ["monitoring", "alerts"]

    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "host_id": {
                    "type": "integer",
                    "description": "Filter alerts by host ID. Omit to get alerts for all hosts.",
                },
                "severity": {
                    "type": "string",
                    "enum": ["critical", "warning", "info"],
                    "description": "Filter alerts by severity level.",
                },
                "limit": {
                    "type": "integer",
                    "default": 20,
                    "description": "Maximum number of alerts to return (default 20).",
                },
            },
            "required": [],
        }

    async def execute(self, args: dict, context):
        from sqlalchemy import select
        from app.models.alert import Alert

        query = select(Alert).where(Alert.status == "firing")

        if args.get("host_id"):
            query = query.where(Alert.host_id == args["host_id"])
        if args.get("severity"):
            query = query.where(Alert.severity == args["severity"])

        limit = args.get("limit", 20)

        async with context.db_session_factory() as db:
            result = await db.execute(
                query.order_by(Alert.fired_at.desc()).limit(limit)
            )
            alerts = result.scalars().all()

        yield ToolEvent(
            type=ToolEventType.RESULT,
            data={
                "alerts": [
                    {
                        "id": a.id,
                        "title": a.title,
                        "severity": a.severity,
                        "status": a.status,
                        "message": a.message,
                        "fired_at": a.fired_at.isoformat(),
                        "host_id": a.host_id,
                    }
                    for a in alerts
                ]
            },
        )
