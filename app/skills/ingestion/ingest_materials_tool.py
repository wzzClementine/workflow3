from __future__ import annotations

from app.agent.tools import BaseTool, ToolCall, ToolResult
from app.services.file import TaskFileService
from app.services.task import TaskService
from app.services.memory import TaskMemoryService
from app.skills.ingestion.file_fetch_service import FileFetchService


class IngestMaterialsTool(BaseTool):
    name = "ingest_materials"

    def __init__(
        self,
        task_file_service: TaskFileService,
        task_service: TaskService,
        task_memory_service: TaskMemoryService,
        file_fetch_service: FileFetchService,
    ):
        self.task_file_service = task_file_service
        self.task_service = task_service
        self.task_memory_service = task_memory_service
        self.file_fetch_service = file_fetch_service

    def execute(self, tool_call: ToolCall) -> ToolResult:
        task_id = tool_call.tool_args.get("task_id")
        files = tool_call.tool_args.get("files", [])

        if not task_id:
            return ToolResult(
                tool_name=self.name,
                success=False,
                message="缺少 task_id",
                data={},
            )

        if not files:
            return ToolResult(
                tool_name=self.name,
                success=False,
                message="没有可导入的文件",
                data={},
            )

        created_records: list[dict] = []

        for item in files:
            file_name = item.get("file_name")
            file_key = item.get("file_key")
            message_id = item.get("message_id")

            if not file_name:
                continue

            role = self._infer_file_role(file_name)
            if role == "unknown":
                continue

            local_path = None
            page_count = None

            # 有 message_id + file_key 就下载到本地
            if file_key and message_id:
                local_path = self.file_fetch_service.download_uploaded_file_to_task_dir(
                    task_id=task_id,
                    file_name=file_name,
                    file_key=file_key,
                    message_id=message_id,
                )
                page_count = self._get_pdf_page_count(local_path)

            record = self.task_file_service.create_file_record(
                task_id=task_id,
                file_role=role,
                file_name=file_name,
                storage_type="feishu",
                local_path=local_path,
                remote_key=file_key,
                page_count=page_count,
                metadata=item,
            )

            if record:
                created_records.append(record)

        materials_summary = self.task_file_service.get_materials_summary(task_id)
        latest_materials_summary = self.task_file_service.get_latest_materials_summary(task_id)
        materials_text = self.task_file_service.build_user_friendly_materials_text(task_id)

        if latest_materials_summary["is_ready"]:
            processing_summary = f"{materials_text} 当前材料已齐全，等待你确认是否开始处理。"
        else:
            processing_summary = f"{materials_text} 当前材料还未收齐，请继续上传缺失文件。"

        self.task_memory_service.update_processing_summary(
            task_id=task_id,
            current_stage="collecting_materials",
            processing_summary=processing_summary,
        )

        self.task_memory_service.update_next_action_hint(
            task_id=task_id,
            current_stage="collecting_materials",
            next_action_hint=(
                "等待用户确认材料"
                if materials_summary["is_ready"]
                else "继续上传缺失材料"
            ),
        )

        if materials_summary["is_ready"]:
            self.task_service.advance_stage(
                task_id=task_id,
                current_stage="waiting_confirmation",
                next_action_hint="请用户确认材料是否正确",
            )

            return ToolResult(
                tool_name=self.name,
                success=True,
                message="材料已齐全，文件已准备好，请确认是否开始处理。回复“开始”即可继续。",
                data={
                    "created_records": created_records,
                    "materials_summary": materials_summary,
                    "latest_materials_summary": latest_materials_summary,
                },
            )

        return ToolResult(
            tool_name=self.name,
            success=True,
            message="文件已记录并下载到本地，但材料暂未齐全",
            data={
                "created_records": created_records,
                "materials_summary": materials_summary,
                "latest_materials_summary": latest_materials_summary,
            },
        )

    def _infer_file_role(self, file_name: str) -> str:
        lowered = file_name.lower()

        if not lowered.endswith(".pdf"):
            return "unknown"

        if "解析" in file_name or "answer" in lowered or "solution" in lowered:
            return "solution_pdf"

        if "试卷" in file_name or "blank" in lowered or "question" in lowered:
            return "blank_pdf"

        return "unknown"

    def _get_pdf_page_count(self, local_path: str | None) -> int | None:
        if not local_path:
            return None

        # 优先尝试 pypdf，再尝试 PyPDF2；都没有就返回 None
        try:
            from pypdf import PdfReader  # type: ignore
            reader = PdfReader(local_path)
            return len(reader.pages)
        except Exception:
            pass

        try:
            from PyPDF2 import PdfReader  # type: ignore
            reader = PdfReader(local_path)
            return len(reader.pages)
        except Exception:
            return None