from __future__ import annotations

from abc import ABC, abstractmethod

from app.agent.tools.tool_models import ToolCall, ToolResult


class BaseTool(ABC):
    name: str = ""

    @abstractmethod
    def execute(self, tool_call: ToolCall) -> ToolResult:
        raise NotImplementedError