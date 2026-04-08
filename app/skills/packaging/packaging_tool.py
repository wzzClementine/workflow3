from __future__ import annotations

from app.agent.tools import BaseTool, ToolCall, ToolResult
from app.services.task import TaskService
from app.services.memory import TaskMemoryService

from app.skills.packaging import PackagingService


class PackagingTool(BaseTool):
    name = "package_results"

    def __init__(
        self,
        task_service: TaskService,
        task_memory_service: TaskMemoryService,
    ):
        self.task_service = task_service
        self.task_memory_service = task_memory_service
        self.packaging_service = PackagingService()

    def execute(self, tool_call: ToolCall) -> ToolResult:
        task_id = tool_call.tool_args.get("task_id")
        task_root = tool_call.tool_args.get("task_root")

        excel_path = tool_call.tool_args.get("excel_path")
        question_dir = tool_call.tool_args.get("question_dir")
        analysis_dir = tool_call.tool_args.get("analysis_dir")
        cleaned_analysis_dir = tool_call.tool_args.get("cleaned_analysis_dir")
        manifest_path = tool_call.tool_args.get("manifest_path")

        # 新增：空白试卷 PDF 路径
        source_pdf_path = tool_call.tool_args.get("source_pdf_path")

        try:
            delivery_path = self.packaging_service.build_delivery_package(
                task_id=task_id,
                task_root=task_root,
                excel_path=excel_path,
                question_dir=question_dir,
                analysis_dir=analysis_dir,
                cleaned_analysis_dir=cleaned_analysis_dir,
                manifest_path=manifest_path,
                source_pdf_path=source_pdf_path,
            )

            self.task_memory_service.update_processing_summary(
                task_id=task_id,
                current_stage="processing",
                processing_summary="交付目录已打包",
            )

            return ToolResult(
                tool_name=self.name,
                success=True,
                message="打包完成",
                data={"local_package_path": delivery_path},
            )

        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                success=False,
                message=f"打包失败: {e}",
                data={},
            )