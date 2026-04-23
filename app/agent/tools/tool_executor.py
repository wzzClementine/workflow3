from __future__ import annotations

from typing import Any

from app.agent.tools.tool_models import ToolCall, ToolResult
from app.agent.tools.tool_registry import ToolRegistry


class ToolExecutor:
    def __init__(self, tool_registry: ToolRegistry):
        self.tool_registry = tool_registry

    def execute(self, tool_call: ToolCall) -> ToolResult:
        """
        统一的工具执行入口。

        设计目标：
        1. 永远返回 ToolResult，不向上层抛出异常
        2. 统一标准化：
           - 未注册工具
           - tool.execute() 内部未捕获异常
        3. 不在这里做任何业务收口：
           - 不修改 task 状态
           - 不发送消息
           - 不处理 session
        """
        try:
            tool = self.tool_registry.get(tool_call.tool_name)
        except Exception as e:
            return self._build_error_result(
                tool_name=tool_call.tool_name,
                message=f"工具执行失败：无法获取工具 {tool_call.tool_name}",
                error_code="tool_not_found",
                exception=e,
                source="registry",
                retryable=False,
                extra_data={
                    "tool_args": tool_call.tool_args,
                },
            )

        try:
            result = tool.execute(tool_call)

            # 防御性校验：理论上所有 tool 都应返回 ToolResult
            if not isinstance(result, ToolResult):
                return self._build_error_result(
                    tool_name=tool_call.tool_name,
                    message=f"工具执行失败：工具 {tool_call.tool_name} 未返回合法的 ToolResult",
                    error_code="invalid_tool_result",
                    exception=TypeError(
                        f"Tool {tool_call.tool_name} returned {type(result).__name__}, expected ToolResult"
                    ),
                    source="executor",
                    retryable=False,
                    extra_data={
                        "tool_args": tool_call.tool_args,
                        "returned_type": type(result).__name__,
                    },
                )

            # 对失败结果做一次轻量补齐，避免上层拿不到统一字段
            if not result.success:
                merged_data = {
                    "error_code": "tool_execution_failed",
                    "exception_type": None,
                    "debug_message": result.message,
                    "retryable": False,
                    "source": "tool",
                    **(result.data or {}),
                }
                return ToolResult(
                    tool_name=result.tool_name,
                    success=False,
                    message=result.message,
                    data=merged_data,
                )

            return result

        except Exception as e:
            return self._build_error_result(
                tool_name=tool_call.tool_name,
                message=f"工具执行异常：{tool_call.tool_name}",
                error_code="tool_execution_error",
                exception=e,
                source="executor",
                retryable=False,
                extra_data={
                    "tool_args": tool_call.tool_args,
                },
            )

    def _build_error_result(
        self,
        tool_name: str,
        message: str,
        error_code: str,
        exception: Exception,
        source: str,
        retryable: bool = False,
        extra_data: dict[str, Any] | None = None,
    ) -> ToolResult:
        data: dict[str, Any] = {
            "error_code": error_code,
            "exception_type": type(exception).__name__,
            "debug_message": repr(exception),
            "retryable": retryable,
            "source": source,
        }

        if extra_data:
            data.update(extra_data)

        return ToolResult(
            tool_name=tool_name,
            success=False,
            message=f"{message}: {exception}",
            data=data,
        )