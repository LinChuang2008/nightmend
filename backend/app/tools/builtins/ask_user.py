"""
AskUserTool — 向用户提问并等待回答

迁移自 OpsAgentLoop._tool_ask_user。
支持 radio / checkbox / text 三种输入类型。
通过 approval_service 等待用户回答（最长 5 分钟）。

风险等级 READ_ONLY，但因需要用户交互所以 requires_approval = True。
MCP 模式下（approval_service 为 None）自动拒绝执行。
"""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from app.tools.base import OpsTool, RiskLevel, ToolEvent, ToolEventType

if TYPE_CHECKING:
    from app.tools.context import ToolContext

# 用户回答超时（秒）
ASK_USER_TIMEOUT = 300


class AskUserTool(OpsTool):
    name = "ask_user"
    description = (
        "Ask the user a question and wait for their response. "
        "Supports radio (single choice), checkbox (multiple choice), and text (free text) input types. "
        "Use this when you need clarification or a decision from the user before proceeding."
    )
    risk_level = RiskLevel.READ_ONLY
    requires_approval = True

    @property
    def tags(self) -> list[str]:
        return ["interaction"]

    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The question to ask the user.",
                },
                "input_type": {
                    "type": "string",
                    "enum": ["radio", "checkbox", "text"],
                    "description": (
                        "The type of input expected: "
                        "'radio' for single choice, 'checkbox' for multiple choice, "
                        "'text' for free text."
                    ),
                },
                "options": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "List of options for radio/checkbox input types. "
                        "Not required for text input."
                    ),
                },
            },
            "required": ["question", "input_type"],
        }

    async def execute(self, args: dict, context: ToolContext):
        question = args["question"]
        input_type = args["input_type"]
        options = args.get("options", [])
        msg_id = str(uuid.uuid4())

        # MCP 模式下不支持需要确认的工具
        if context.approval_service is None:
            yield ToolEvent(
                type=ToolEventType.RESULT,
                data={
                    "error": "ask_user requires user interaction and is not available in MCP mode.",
                },
            )
            return

        # 持久化 ask_user 消息
        if context.save_message is not None:
            await context.save_message("assistant", "ask_user", {
                "question": question,
                "input_type": input_type,
                "options": options,
                "status": "pending",
                "answer": None,
            }, message_id=msg_id)

        await context.approval_service.register(msg_id, "ask_user")

        # 向前端推送提问事件
        yield ToolEvent(
            type=ToolEventType.APPROVAL_REQUEST,
            data={
                "event": "ask_user",
                "message_id": msg_id,
                "question": question,
                "input_type": input_type,
                "options": options,
            },
        )

        # 等待用户回答（5 分钟超时）
        reply = await context.approval_service.wait_for_reply(
            msg_id,
            timeout=ASK_USER_TIMEOUT,
            timeout_action="expired",
        )
        answer = reply.get("answer", "") or ""

        yield ToolEvent(
            type=ToolEventType.RESULT,
            data={"answer": answer},
        )
