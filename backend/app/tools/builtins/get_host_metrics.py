"""
GetHostMetricsTool — 获取主机最新指标

迁移自 OpsAgentLoop._tool_get_host_metrics。
根据 host_id 查询最近一条 HostMetric 记录，返回 CPU、内存、磁盘、负载等核心指标。
若无指标数据则返回 error 字段。
"""
from __future__ import annotations

from app.tools.base import OpsTool, RiskLevel, ToolEvent, ToolEventType


class GetHostMetricsTool(OpsTool):
    name = "get_host_metrics"
    description = (
        "Get the latest performance metrics for a specific host. "
        "Returns cpu_percent, memory_percent, disk_percent, cpu_load_1, cpu_load_5, "
        "and recorded_at. Returns an error if no metrics are found for the given host_id."
    )
    risk_level = RiskLevel.READ_ONLY

    @property
    def tags(self) -> list[str]:
        return ["monitoring", "metrics"]

    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "host_id": {
                    "type": "integer",
                    "description": "The ID of the host to retrieve metrics for.",
                },
            },
            "required": ["host_id"],
        }

    async def execute(self, args: dict, context):
        from sqlalchemy import select
        from app.models.host_metric import HostMetric

        host_id = args["host_id"]

        async with context.db_session_factory() as db:
            result = await db.execute(
                select(HostMetric)
                .where(HostMetric.host_id == host_id)
                .order_by(HostMetric.recorded_at.desc())
                .limit(1)
            )
            metric = result.scalar_one_or_none()

        if not metric:
            yield ToolEvent(
                type=ToolEventType.RESULT,
                data={"error": f"No metrics found for host_id={host_id}"},
            )
            return

        yield ToolEvent(
            type=ToolEventType.RESULT,
            data={
                "host_id": host_id,
                "cpu_percent": metric.cpu_percent,
                "memory_percent": metric.memory_percent,
                "disk_percent": metric.disk_percent,
                "cpu_load_1": metric.cpu_load_1,
                "cpu_load_5": metric.cpu_load_5,
                "recorded_at": metric.recorded_at.isoformat(),
            },
        )
