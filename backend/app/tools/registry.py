"""
ToolRegistry — 工具注册表，支持自动发现和多格式输出

错误处理：
- 导入失败的模块跳过并记日志（不 crash 整个 registry）
- 重复工具名抛 ValueError（防止静默覆盖）
"""
from __future__ import annotations

import importlib
import logging
from pathlib import Path
from typing import Optional

from .base import OpsTool

logger = logging.getLogger(__name__)


class ToolRegistry:
    """工具注册表。"""

    def __init__(self) -> None:
        self._tools: dict[str, OpsTool] = {}

    def register(self, tool: OpsTool) -> None:
        """手动注册一个工具实例。重复名称抛异常。"""
        if tool.name in self._tools:
            raise ValueError(
                f"Duplicate tool name '{tool.name}': "
                f"already registered by {type(self._tools[tool.name]).__name__}, "
                f"conflict from {type(tool).__name__}"
            )
        self._tools[tool.name] = tool
        logger.info("Registered tool: %s", tool.name)

    def discover(self, *packages: str) -> None:
        """扫描 Python 包，自动发现所有 OpsTool 子类并注册。

        导入失败的模块会被跳过并记录警告，不会 crash 整个 registry。
        """
        for pkg in packages:
            try:
                module = importlib.import_module(pkg)
            except ImportError:
                logger.warning("Failed to import package %s, skipping", pkg, exc_info=True)
                continue

            pkg_path = Path(module.__file__).parent
            for file in sorted(pkg_path.glob("*.py")):
                if file.name.startswith("_"):
                    continue
                mod_name = f"{pkg}.{file.stem}"
                try:
                    mod = importlib.import_module(mod_name)
                except Exception:
                    logger.warning("Failed to import tool module %s, skipping", mod_name, exc_info=True)
                    continue

                for obj in vars(mod).values():
                    if (
                        isinstance(obj, type)
                        and issubclass(obj, OpsTool)
                        and obj is not OpsTool
                        and getattr(obj, "name", None)
                    ):
                        try:
                            instance = obj()
                            if instance.enabled:
                                self.register(instance)
                        except Exception:
                            logger.warning(
                                "Failed to instantiate tool %s from %s, skipping",
                                getattr(obj, "name", obj.__name__), mod_name,
                                exc_info=True,
                            )

    def get(self, name: str) -> Optional[OpsTool]:
        return self._tools.get(name)

    def list_tools(self, tags: Optional[list[str]] = None) -> list[OpsTool]:
        tools = list(self._tools.values())
        if tags:
            tag_set = set(tags)
            tools = [t for t in tools if tag_set & set(t.tags)]
        return tools

    def get_openai_schemas(self, tags: Optional[list[str]] = None) -> list[dict]:
        """生成 Ops Assistant 用的 TOOLS 列表。"""
        return [t.to_openai_schema() for t in self.list_tools(tags)]

    def get_mcp_tools(self) -> list[dict]:
        """生成 MCP server 用的工具列表。"""
        return [t.to_mcp_schema() for t in self.list_tools()]

    @property
    def tool_count(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
