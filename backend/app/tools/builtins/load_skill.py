"""
LoadSkillTool — 加载 Skill 知识库

迁移自 OpsAgentLoop._tool_load_skill。
从 skills/ 目录加载指定的 Markdown 知识库文件，
将内容注入对话上下文供 AI 参考。

风险等级 READ_ONLY，无需用户确认。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from app.tools.base import OpsTool, RiskLevel, ToolEvent, ToolEventType

if TYPE_CHECKING:
    from app.tools.context import ToolContext


class LoadSkillTool(OpsTool):
    name = "load_skill"
    description = (
        "Load a skill knowledge base by name. "
        "Returns the skill content which will be injected into the conversation context. "
        "Use list_skills first if you don't know what skills are available."
    )
    risk_level = RiskLevel.READ_ONLY

    @property
    def tags(self) -> list[str]:
        return ["knowledge"]

    def parameters_schema(self) -> dict:
        # 动态构建可用 skill 列表作为 enum
        from app.services.ops_skill_loader import list_skills

        available = [s["name"] for s in list_skills()]
        schema = {
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": "Name of the skill to load.",
                },
            },
            "required": ["skill_name"],
        }
        if available:
            schema["properties"]["skill_name"]["enum"] = available
        return schema

    async def execute(self, args: dict, context: ToolContext):
        from app.services.ops_skill_loader import load_skill

        skill_name = args["skill_name"]
        content = load_skill(skill_name)

        if not content:
            yield ToolEvent(
                type=ToolEventType.RESULT,
                data={"error": f"Skill '{skill_name}' not found"},
            )
            return

        # 持久化 skill_load 消息
        if context.save_message is not None:
            await context.save_message("assistant", "skill_load", {
                "skill_name": skill_name,
                "description": f"已加载 {skill_name} 技能知识库",
            })

        yield ToolEvent(
            type=ToolEventType.SKILL_LOADED,
            data={
                "skill_name": skill_name,
                "content": content,
            },
        )
        yield ToolEvent(
            type=ToolEventType.RESULT,
            data={
                "skill_name": skill_name,
                "loaded": True,
                "content_length": len(content),
                "skill_content": content,
            },
        )
