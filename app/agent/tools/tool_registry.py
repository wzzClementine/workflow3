from typing import Any, Callable


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, dict[str, Any]] = {}

    def register_tool(
        self,
        name: str,
        description: str,
        handler: Callable[..., Any],
    ) -> None:
        if name in self._tools:
            raise ValueError(f"工具已注册: {name}")

        self._tools[name] = {
            "name": name,
            "description": description,
            "handler": handler,
        }

    def get_tool(self, name: str) -> dict[str, Any] | None:
        return self._tools.get(name)

    def has_tool(self, name: str) -> bool:
        return name in self._tools

    def list_tools(self) -> list[dict[str, Any]]:
        return list(self._tools.values())