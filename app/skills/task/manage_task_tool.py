from __future__ import annotations

from app.agent.tools import BaseTool, ToolCall, ToolResult
from app.services.task import TaskService


class ManageTaskTool(BaseTool):
    name = "manage_task"

    def __init__(self, task_service: TaskService):
        self.task_service = task_service

    def execute(self, tool_call: ToolCall) -> ToolResult:
        action = tool_call.tool_args.get("action")
        task_id = tool_call.tool_args.get("task_id")

        if not task_id:
            return ToolResult(
                tool_name=self.name,
                success=False,
                message="缺少 task_id",
                data={},
            )

        if action == "advance_stage":
            target_stage = tool_call.tool_args.get("target_stage")
            next_action_hint = tool_call.tool_args.get("next_action_hint")

            if not target_stage:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    message="缺少 target_stage",
                    data={},
                )

            task = self.task_service.advance_stage(
                task_id=task_id,
                current_stage=target_stage,
                next_action_hint=next_action_hint,
            )

            return ToolResult(
                tool_name=self.name,
                success=True,
                message=f"任务已推进到阶段: {target_stage}",
                data={"task": task},
            )

        if action == "mark_failed":
            error_message = tool_call.tool_args.get("error_message", "未提供错误信息")

            task = self.task_service.mark_failed(
                task_id=task_id,
                error_message=error_message,
            )

            return ToolResult(
                tool_name=self.name,
                success=True,
                message="任务已标记为失败",
                data={"task": task},
            )

        return ToolResult(
            tool_name=self.name,
            success=False,
            message=f"不支持的 action: {action}",
            data={},
        )