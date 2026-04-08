from __future__ import annotations

from app.agent.tools import BaseTool, ToolCall, ToolResult
from app.config import settings
from app.services.delivery import DeliveryService
from app.services.task import TaskService
from app.services.memory import TaskMemoryService


class DeliverResultsTool(BaseTool):
    name = "deliver_results"

    def __init__(
        self,
        delivery_service: DeliveryService,
        task_service: TaskService,
        task_memory_service: TaskMemoryService,
    ):
        self.delivery_service = delivery_service
        self.task_service = task_service
        self.task_memory_service = task_memory_service

    def execute(self, tool_call: ToolCall) -> ToolResult:
        task_id = tool_call.tool_args.get("task_id")
        local_package_path = tool_call.tool_args.get("local_package_path")
        parent_folder_token = tool_call.tool_args.get("parent_folder_token") or settings.feishu_drive_folder_token

        if not task_id:
            return ToolResult(
                tool_name=self.name,
                success=False,
                message="缺少 task_id",
                data={},
            )

        if not local_package_path:
            return ToolResult(
                tool_name=self.name,
                success=False,
                message="缺少 local_package_path",
                data={},
            )

        if not parent_folder_token:
            return ToolResult(
                tool_name=self.name,
                success=False,
                message="缺少飞书目标文件夹 token（也未在配置中提供 FEISHU_DRIVE_FOLDER_TOKEN）",
                data={},
            )

        try:
            self.task_memory_service.update_processing_summary(
                task_id=task_id,
                current_stage="delivering",
                processing_summary="开始上传最终交付目录到飞书云文件夹",
            )

            result = self.delivery_service.deliver_package_to_feishu(
                task_id=task_id,
                local_package_path=local_package_path,
                parent_folder_token=parent_folder_token,
            )

            self.task_service.mark_completed(task_id)
            self.task_memory_service.update_processing_summary(
                task_id=task_id,
                current_stage="completed",
                processing_summary="最终交付目录已上传飞书，任务完成",
            )
            self.task_memory_service.update_next_action_hint(
                task_id=task_id,
                current_stage="completed",
                next_action_hint="任务已完成，无需后续动作",
            )

            return ToolResult(
                tool_name=self.name,
                success=True,
                message="最终结果已上传到飞书云文件夹，任务已完成",
                data=result,
            )

        except Exception as e:
            self.task_service.mark_failed(task_id, str(e))
            self.task_memory_service.update_last_error(
                task_id=task_id,
                current_stage="failed",
                last_error=str(e),
            )

            return ToolResult(
                tool_name=self.name,
                success=False,
                message=f"交付失败: {e}",
                data={},
            )