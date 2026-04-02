"""
ListRunbooksTool — 列出所有可用的 Runbook

桥接工具：将 remediation.RunbookRegistry 暴露给统一工具注册系统。
列出所有内置 Runbook（从 app.remediation.runbooks 包加载）和
用户自定义 Runbook（从数据库热加载）。

每次调用都会重新从数据库加载自定义 Runbook，确保热加载生效。
"""
from __future__ import annotations

import importlib
import logging
from pathlib import Path

from app.tools.base import OpsTool, RiskLevel, ToolEvent, ToolEventType

logger = logging.getLogger(__name__)


def _load_builtin_runbooks(registry) -> None:
    """扫描 app.remediation.runbooks 包，将所有 RUNBOOK 常量注册到 registry。"""
    pkg = importlib.import_module("app.remediation.runbooks")
    pkg_path = Path(pkg.__file__).parent
    for file in sorted(pkg_path.glob("*.py")):
        if file.name.startswith("_"):
            continue
        mod_name = f"app.remediation.runbooks.{file.stem}"
        try:
            mod = importlib.import_module(mod_name)
            runbook = getattr(mod, "RUNBOOK", None)
            if runbook is not None:
                registry.register(runbook)
        except Exception:
            logger.warning("Failed to load built-in runbook from %s", mod_name, exc_info=True)


class ListRunbooksTool(OpsTool):
    name = "list_runbooks"
    description = (
        "List all available runbooks, including both built-in remediation runbooks "
        "and user-created custom runbooks. Returns name, description, and risk_level "
        "for each runbook."
    )
    risk_level = RiskLevel.READ_ONLY

    @property
    def tags(self) -> list[str]:
        return ["runbooks", "discovery"]

    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    async def execute(self, args: dict, context):
        from app.remediation.runbook_registry import RunbookRegistry

        registry = RunbookRegistry()

        # 加载内置 Runbook
        _load_builtin_runbooks(registry)

        # 从数据库热加载自定义 Runbook（每次调用都重新加载）
        async with context.db_session_factory() as db:
            await registry.load_from_db(db)

        runbooks = registry.list_all()

        yield ToolEvent(
            type=ToolEventType.RESULT,
            data={
                "runbooks": [
                    {
                        "name": rb.name,
                        "description": rb.description,
                        "risk_level": rb.risk_level.value,
                    }
                    for rb in runbooks
                ],
                "total": len(runbooks),
            },
        )
