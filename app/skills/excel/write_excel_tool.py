from __future__ import annotations

from app.agent.tools import BaseTool, ToolCall, ToolResult
from app.services.task import TaskService
from app.services.memory import TaskMemoryService

from app.skills.excel import ExcelWriter


class WriteExcelTool(BaseTool):
    name = "write_excel"

    def __init__(
        self,
        task_service: TaskService,
        task_memory_service: TaskMemoryService,
    ):
        self.task_service = task_service
        self.task_memory_service = task_memory_service
        self.writer = ExcelWriter()

    def execute(self, tool_call: ToolCall) -> ToolResult:
        task_id = tool_call.tool_args.get("task_id")
        manifest_path = tool_call.tool_args.get("manifest_path")
        output_path = tool_call.tool_args.get("output_path")

        school = tool_call.tool_args.get("school", "")
        year = tool_call.tool_args.get("year", "")
        paper_note = tool_call.tool_args.get("paper_note", "")

        try:
            excel_path = self.writer.write_manifest_to_excel(
                manifest_path=manifest_path,
                output_path=output_path,
                school=school,
                year=year,
                paper_note=paper_note,
            )

            self.task_memory_service.update_processing_summary(
                task_id=task_id,
                current_stage="processing",
                processing_summary="Excel 已生成",
            )

            return ToolResult(
                tool_name=self.name,
                success=True,
                message="Excel 生成完成",
                data={"excel_path": excel_path},
            )

        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                success=False,
                message=f"Excel 生成失败: {e}",
                data={},
            )