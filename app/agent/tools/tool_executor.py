import inspect
from typing import Any

from app.agent.tools.register_tools import tool_registry


class ToolExecutor:
    def execute_tool_call(self, tool_call: dict[str, Any]) -> dict[str, Any]:
        tool_name = tool_call.get("tool")
        args = tool_call.get("args", {})

        if not tool_name:
            return {
                "tool": None,
                "status": "failed",
                "error": "tool_call 缺少 tool 字段",
                "result": None,
            }

        tool_meta = tool_registry.get_tool(tool_name)
        if not tool_meta:
            return {
                "tool": tool_name,
                "status": "failed",
                "error": f"未注册的工具: {tool_name}",
                "result": None,
            }

        handler = tool_meta["handler"]

        try:
            sig = inspect.signature(handler)
            allowed_params = set(sig.parameters.keys())

            safe_args = {
                k: v for k, v in args.items()
                if k in allowed_params
            }

            result = handler(**safe_args)

            return {
                "tool": tool_name,
                "status": "success",
                "error": None,
                "result": result,
                "used_args": safe_args,
                "ignored_args": {
                    k: v for k, v in args.items()
                    if k not in allowed_params
                },
            }

        except Exception as e:
            return {
                "tool": tool_name,
                "status": "failed",
                "error": str(e),
                "result": None,
            }

    def execute_tool_calls(self, tool_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
        results = []

        for tool_call in tool_calls:
            result = self.execute_tool_call(tool_call)
            results.append(result)

        return results


tool_executor = ToolExecutor()