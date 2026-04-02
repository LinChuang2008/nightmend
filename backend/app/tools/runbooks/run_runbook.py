"""
RunRunbookTool — 执行指定的修复 Runbook

桥接工具：将 remediation Runbook 执行暴露给统一工具注册系统。
风险等级 CRITICAL，需要用户确认后才会执行。
MCP 模式下（approval_service 为 None）自动拒绝执行。

Phase 2 桥接：当前返回 Runbook 信息和 pending 状态，
完整的 RemediationAgent 执行集成将在后续阶段实现。
"""
from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from app.tools.base import OpsTool, RiskLevel, ToolEvent, ToolEventType

if TYPE_CHECKING:
    from app.tools.context import ToolContext

logger = logging.getLogger(__name__)

# Runbook 确认超时（秒）
RUNBOOK_CONFIRM_TIMEOUT = 120


class RunRunbookTool(OpsTool):
    name = "run_runbook"
    description = (
        "Execute a specified remediation runbook on a target host. "
        "Requires user confirmation before execution. "
        "Supports dry_run mode (default) for safe preview of actions."
    )
    risk_level = RiskLevel.CRITICAL
    requires_approval = True

    @property
    def tags(self) -> list[str]:
        return ["runbooks", "execution"]

    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "runbook_name": {
                    "type": "string",
                    "description": "The name of the runbook to execute (e.g. 'disk_cleanup', 'service_restart').",
                },
                "host_id": {
                    "type": "integer",
                    "description": "The ID of the target host to run the runbook on.",
                },
                "dry_run": {
                    "type": "boolean",
                    "default": True,
                    "description": "If true (default), preview the runbook steps without executing. Set to false for actual execution.",
                },
            },
            "required": ["runbook_name", "host_id"],
        }

    async def execute(self, args: dict, context: ToolContext):
        from app.remediation.runbook_registry import RunbookRegistry
        from app.tools.runbooks.list_runbooks import _load_builtin_runbooks

        runbook_name = args["runbook_name"]
        host_id = args["host_id"]
        dry_run = args.get("dry_run", True)
        msg_id = str(uuid.uuid4())

        # MCP 模式下不支持需要确认的工具
        if context.approval_service is None:
            yield ToolEvent(
                type=ToolEventType.RESULT,
                data={
                    "error": "run_runbook requires user approval and is not available in MCP mode.",
                },
            )
            return

        # 加载 Runbook 注册表（内置 + 自定义）
        registry = RunbookRegistry()
        _load_builtin_runbooks(registry)

        async with context.db_session_factory() as db:
            await registry.load_from_db(db)

        # 查找指定的 Runbook
        runbook = registry.get(runbook_name)
        if runbook is None:
            available = [rb.name for rb in registry.list_all()]
            yield ToolEvent(
                type=ToolEventType.RESULT,
                data={
                    "error": f"Runbook '{runbook_name}' not found.",
                    "available_runbooks": available,
                },
            )
            return

        # 获取主机名
        from sqlalchemy import select
        from app.models.host import Host

        async with context.db_session_factory() as db:
            result = await db.execute(select(Host).where(Host.id == host_id))
            host = result.scalar_one_or_none()

        if host is None:
            yield ToolEvent(
                type=ToolEventType.RESULT,
                data={"error": f"Host with id={host_id} not found."},
            )
            return

        host_name = host.display_hostname if host else f"host-{host_id}"

        # 构建确认请求描述
        step_descriptions = [step.description for step in runbook.commands]
        reason = (
            f"Execute runbook '{runbook_name}' on {host_name} "
            f"({'dry-run' if dry_run else 'LIVE'}): "
            f"{runbook.description}"
        )

        # 持久化确认请求消息
        if context.save_message is not None:
            await context.save_message("assistant", "runbook_request", {
                "runbook_name": runbook_name,
                "host_id": host_id,
                "host_name": host_name,
                "dry_run": dry_run,
                "reason": reason,
                "steps": step_descriptions,
                "risk_level": runbook.risk_level.value,
                "status": "pending",
            }, message_id=msg_id)

        await context.approval_service.register(msg_id, "runbook_request")

        # 向前端推送确认请求
        yield ToolEvent(
            type=ToolEventType.APPROVAL_REQUEST,
            data={
                "event": "runbook_request",
                "message_id": msg_id,
                "runbook_name": runbook_name,
                "host_id": host_id,
                "host_name": host_name,
                "dry_run": dry_run,
                "reason": reason,
                "steps": step_descriptions,
                "risk_level": runbook.risk_level.value,
            },
        )

        # 等待用户确认
        reply = await context.approval_service.wait_for_reply(
            msg_id,
            timeout=RUNBOOK_CONFIRM_TIMEOUT,
            timeout_action="expired",
        )
        action = reply.get("action", "reject")

        if action == "confirm":
            # Phase 2 桥接：返回 Runbook 信息和待实现状态
            # 完整的 RemediationAgent.for_tool_bridge() 集成将在后续阶段实现
            yield ToolEvent(
                type=ToolEventType.PROGRESS,
                data={
                    "event": "runbook_approved",
                    "message_id": msg_id,
                    "runbook_name": runbook_name,
                    "host_name": host_name,
                },
            )
            yield ToolEvent(
                type=ToolEventType.RESULT,
                data={
                    "status": "pending_implementation",
                    "runbook_name": runbook_name,
                    "description": runbook.description,
                    "host_id": host_id,
                    "host_name": host_name,
                    "dry_run": dry_run,
                    "risk_level": runbook.risk_level.value,
                    "steps": [
                        {
                            "description": step.description,
                            "command": step.command,
                            "timeout_seconds": step.timeout_seconds,
                        }
                        for step in runbook.commands
                    ],
                    "verify_steps": [
                        {
                            "description": step.description,
                            "command": step.command,
                            "timeout_seconds": step.timeout_seconds,
                        }
                        for step in runbook.verify_commands
                    ],
                    "message": (
                        "Runbook approved and loaded. "
                        "Full execution integration is pending (Phase 2 bridge). "
                        "The steps above would be executed on the target host."
                    ),
                },
            )

        elif action == "reject":
            yield ToolEvent(
                type=ToolEventType.PROGRESS,
                data={"event": "runbook_rejected", "message_id": msg_id, "reason": "rejected"},
            )
            yield ToolEvent(
                type=ToolEventType.RESULT,
                data={"error": "User rejected runbook execution.", "action": "rejected"},
            )
        else:
            yield ToolEvent(
                type=ToolEventType.PROGRESS,
                data={"event": "runbook_expired", "message_id": msg_id, "reason": "timeout"},
            )
            yield ToolEvent(
                type=ToolEventType.RESULT,
                data={"error": "Runbook confirmation timed out, automatically cancelled.", "action": "expired"},
            )
