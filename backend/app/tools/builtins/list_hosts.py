"""
ListHostsTool — 列出受监控主机

迁移自 OpsAgentLoop._tool_list_hosts。
按状态筛选主机列表，返回主机基本信息（ID、主机名、IP、状态、分组、标签）。
最多返回 50 条记录。
"""
from __future__ import annotations

from app.tools.base import OpsTool, RiskLevel, ToolEvent, ToolEventType


class ListHostsTool(OpsTool):
    name = "list_hosts"
    description = (
        "List monitored hosts, optionally filtered by status. "
        "Returns up to 50 hosts with id, hostname, display_name, ip, status, "
        "group_name, and tags. Returns an empty list if no hosts match the filter."
    )
    risk_level = RiskLevel.READ_ONLY

    @property
    def tags(self) -> list[str]:
        return ["monitoring", "hosts"]

    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["online", "offline", "all"],
                    "default": "online",
                    "description": "Filter hosts by status. 'all' returns both online and offline.",
                },
            },
            "required": [],
        }

    async def execute(self, args: dict, context):
        from sqlalchemy import select
        from app.models.host import Host

        status_filter = args.get("status", "online")
        query = select(Host)
        if status_filter != "all":
            query = query.where(Host.status == status_filter)

        async with context.db_session_factory() as db:
            result = await db.execute(query.limit(50))
            hosts = result.scalars().all()

        yield ToolEvent(
            type=ToolEventType.RESULT,
            data={
                "hosts": [
                    {
                        "id": h.id,
                        "hostname": h.hostname,
                        "display_name": h.display_name,
                        "ip": h.display_ip,
                        "status": h.status,
                        "group_name": h.group_name,
                        "tags": h.tags,
                    }
                    for h in hosts
                ]
            },
        )
