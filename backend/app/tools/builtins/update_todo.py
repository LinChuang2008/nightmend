"""
UpdateTodoTool — 更新 TODO 待办列表

迁移自 OpsAgentLoop._execute_tool 中的 update_todo 分支。
AI 助手用此工具向前端推送 TODO 列表更新（添加、修改状态、删除待办项）。
通过 TODO_UPDATE 事件通知前端，然后 yield 最终 RESULT。
"""
from __future__ import annotations

from app.tools.base import OpsTool, RiskLevel, ToolEvent, ToolEventType


class UpdateTodoTool(OpsTool):
    name = "update_todo"
    description = (
        "Update the TODO list displayed to the user. "
        "Accepts an array of todo items, each with id, text, and status. "
        "Used to propose action plans, track investigation steps, or show progress. "
        "The frontend renders these as an interactive checklist."
    )
    risk_level = RiskLevel.READ_ONLY

    @property
    def tags(self) -> list[str]:
        return ["interaction", "planning"]

    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "todos": {
                    "type": "array",
                    "description": "List of todo items to display.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {
                                "type": "string",
                                "description": "Unique identifier for the todo item.",
                            },
                            "text": {
                                "type": "string",
                                "description": "The todo item text / description.",
                            },
                            "status": {
                                "type": "string",
                                "enum": ["pending", "in_progress", "done"],
                                "description": "Current status of the todo item.",
                            },
                        },
                        "required": ["id", "text", "status"],
                    },
                },
            },
            "required": ["todos"],
        }

    async def execute(self, args: dict, context):
        todos = args.get("todos", [])

        # Emit a TODO_UPDATE event so the frontend can render the checklist
        yield ToolEvent(
            type=ToolEventType.TODO_UPDATE,
            data={"todos": todos},
        )

        # Persist the todo update message if a save_message callback is available
        if context.save_message:
            await context.save_message("assistant", "todo_update", args)

        # Final result — echo the todos back to the LLM for context continuity
        yield ToolEvent(
            type=ToolEventType.RESULT,
            data={"todos": todos},
        )
