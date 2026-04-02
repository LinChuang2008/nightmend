"""
ProvideConclusionTool — 提供最终结论并结束推理循环

迁移自 OpsAgentLoop._execute_tool 中 provide_conclusion 分支。
AI 助手调用此工具来给出最终结论，结束当前推理循环。
设置 stop=True 使调度器退出工具调用循环。

风险等级 READ_ONLY，无需用户确认。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from app.tools.base import OpsTool, RiskLevel, ToolEvent, ToolEventType

if TYPE_CHECKING:
    from app.tools.context import ToolContext


class ProvideConclusionTool(OpsTool):
    name = "provide_conclusion"
    description = (
        "Provide a final conclusion or answer to the user's question and end the current "
        "reasoning loop. Use this when you have gathered enough information to give a "
        "definitive answer or recommendation."
    )
    risk_level = RiskLevel.READ_ONLY

    @property
    def tags(self) -> list[str]:
        return ["interaction", "conclusion"]

    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "conclusion": {
                    "type": "string",
                    "description": (
                        "The final conclusion or answer to present to the user. "
                        "Should be a complete, well-structured response."
                    ),
                },
                "resolved": {
                    "type": "boolean",
                    "description": (
                        "Whether the issue or question has been fully resolved. "
                        "Defaults to true."
                    ),
                },
            },
            "required": ["conclusion"],
        }

    async def execute(self, args: dict, context: ToolContext):
        conclusion = args.get("conclusion", "")
        resolved = args.get("resolved", True)

        # 持久化结论消息
        if context.save_message is not None:
            await context.save_message("assistant", "text", {"text": conclusion})

        yield ToolEvent(
            type=ToolEventType.RESULT,
            data={
                "conclusion": conclusion,
                "resolved": resolved,
            },
            stop=True,
        )
