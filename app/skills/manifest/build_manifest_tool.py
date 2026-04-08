from __future__ import annotations

from app.agent.tools import BaseTool, ToolCall, ToolResult
from app.services.task import TaskService
from app.services.memory import TaskMemoryService

from app.skills.manifest import LLMManifestBuilder


class BuildManifestTool(BaseTool):
    name = "build_manifest"

    def __init__(
        self,
        task_service: TaskService,
        task_memory_service: TaskMemoryService,
        vision_llm_client,
    ):
        self.task_service = task_service
        self.task_memory_service = task_memory_service
        self.builder = LLMManifestBuilder(vision_llm_client)

    def execute(self, tool_call: ToolCall) -> ToolResult:
        task_id = tool_call.tool_args.get("task_id")
        question_root_dir = tool_call.tool_args.get("question_root_dir")
        analysis_root_dir = tool_call.tool_args.get("analysis_root_dir")
        cleaned_analysis_root_dir = tool_call.tool_args.get("cleaned_analysis_root_dir")
        output_path = tool_call.tool_args.get("output_path")

        try:
            result = self.builder.build_manifest(
                question_root_dir=question_root_dir,
                analysis_root_dir=analysis_root_dir,
                cleaned_analysis_root_dir=cleaned_analysis_root_dir,
                output_path=output_path,
            )

            self.task_memory_service.update_processing_summary(
                task_id=task_id,
                current_stage="processing",
                processing_summary="manifest 已生成",
            )

            return ToolResult(
                tool_name=self.name,
                success=True,
                message="manifest 构建完成",
                data={
                    "manifest_path": result.manifest_path,
                    "item_count": result.total_count,
                },
            )

        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                success=False,
                message=f"manifest 构建失败: {e}",
                data={},
            )