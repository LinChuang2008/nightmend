"""
统一工具注册系统 — 一次定义，Ops Assistant / MCP / Remediation 三处可用。

使用方式：
    from app.tools import tool_registry
    schemas = tool_registry.get_openai_schemas()
    tool = tool_registry.get("list_hosts")
"""
from .registry import ToolRegistry

tool_registry = ToolRegistry()


def init_tool_registry() -> ToolRegistry:
    """应用启动时调用，发现并注册所有内置工具。"""
    tool_registry.discover(
        "app.tools.builtins",
        "app.tools.runbooks",
    )
    return tool_registry
