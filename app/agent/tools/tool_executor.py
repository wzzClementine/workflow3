from __future__ import annotations

from app.agent.tools.tool_models import ToolCall, ToolResult
from app.agent.tools.tool_registry import ToolRegistry


class ToolExecutor:
    def __init__(self, tool_registry: ToolRegistry):
        self.tool_registry = tool_registry

    def execute(self, tool_call: ToolCall) -> ToolResult:
        tool = self.tool_registry.get(tool_call.tool_name)
        return tool.execute(tool_call)