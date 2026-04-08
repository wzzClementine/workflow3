from __future__ import annotations

from app.agent.tools.base_tool import BaseTool


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        if not tool.name:
            raise ValueError("工具必须定义 name")

        self._tools[tool.name] = tool

    def get(self, tool_name: str) -> BaseTool:
        tool = self._tools.get(tool_name)
        if not tool:
            raise ValueError(f"未注册的工具: {tool_name}")
        return tool

    def has(self, tool_name: str) -> bool:
        return tool_name in self._tools

    def list_tool_names(self) -> list[str]:
        return list(self._tools.keys())