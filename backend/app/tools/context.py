"""
ToolContext — 工具执行上下文

替代 OpsAgentLoop 上散落的 self.* 引用。
MCP 模式下 approval_service 和 save_message 为 None。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Optional

if TYPE_CHECKING:
    from redis.asyncio import Redis
    from app.services.approval_service import ApprovalService
    from .safety import SafetyChecker


@dataclass
class ToolContext:
    """工具执行上下文。

    MCP 模式下 approval_service 和 save_message 为 None，
    需要确认的工具在 MCP 模式下自动拒绝执行（安全优先）。
    """
    session_id: str
    user_id: int
    db_session_factory: Callable
    redis: Redis
    safety_checker: SafetyChecker
    approval_service: Optional[ApprovalService] = None
    save_message: Optional[Callable] = None
    context_messages: Optional[list[dict]] = None
    caller: str = "ops_assistant"  # "ops_assistant" | "mcp" | "remediation"
