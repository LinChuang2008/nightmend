"""
OpsTool 基类 — 统一工具注册系统的核心抽象

所有 Ops Assistant / MCP / Remediation 工具继承此基类。
一个 Python 文件 = 一个工具，零配置自动发现。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, AsyncGenerator

if TYPE_CHECKING:
    from .context import ToolContext


class RiskLevel(Enum):
    """工具风险等级。

    与 remediation RiskLevel 的映射：
      remediation.AUTO   → READ_ONLY / LOW
      remediation.CONFIRM → HIGH
      remediation.BLOCK   → CRITICAL
    统一后废弃 remediation 的 RiskLevel。
    """
    READ_ONLY = "read_only"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ToolEventType(Enum):
    RESULT = "result"
    PROGRESS = "progress"
    APPROVAL_REQUEST = "approval"
    TEXT = "text"
    TODO_UPDATE = "todo"
    SKILL_LOADED = "skill"


@dataclass
class ToolEvent:
    type: ToolEventType
    data: dict = field(default_factory=dict)
    stop: bool = False  # True = 结束推理循环


class OpsTool(ABC):
    """
    所有工具的基类。

    子类必须定义 name, description 为类属性。
    子类应覆盖 tags 属性。

    错误处理约定：
    - 工具内部异常由 registry 调度器统一捕获
    - 调度器会 yield ToolEvent(type=RESULT, data={"error": str(e)})
    - 调度器有执行超时保护（默认 300 秒）
    """

    name: str
    description: str
    risk_level: RiskLevel = RiskLevel.READ_ONLY
    requires_approval: bool = False
    enabled: bool = True

    @property
    def tags(self) -> list[str]:
        return []

    @abstractmethod
    def parameters_schema(self) -> dict:
        """返回 OpenAI function-calling 格式的参数 JSON Schema。"""
        ...

    @abstractmethod
    async def execute(
        self, args: dict, context: ToolContext
    ) -> AsyncGenerator[ToolEvent, None]:
        """执行工具，yield ToolEvent 流。最后必须 yield type=RESULT。"""
        ...
        yield  # type: ignore  # pragma: no cover

    def to_openai_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema(),
            },
        }

    def to_mcp_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.parameters_schema(),
        }
