from __future__ import annotations

import os

from app.agent.tools import BaseTool, ToolCall, ToolResult
from app.services.task import TaskService
from app.services.file import TaskFileService
from app.services.memory import TaskMemoryService
from app.services.session import ChatSessionService


class RerunLastTaskTool(BaseTool):
    name = "rerun_last_task"

    def __init__(
        self,
        task_service: TaskService,
        task_file_service: TaskFileService,
        task_memory_service: TaskMemoryService,
        chat_session_service: ChatSessionService,
    ):
        self.task_service = task_service
        self.task_file_service = task_file_service
        self.task_memory_service = task_memory_service
        self.chat_session_service = chat_session_service

    def execute(self, tool_call: ToolCall) -> ToolResult:
        chat_id = tool_call.tool_args.get("chat_id")
        current_task_id = tool_call.tool_args.get("current_task_id")

        if not chat_id:
            return ToolResult(
                tool_name=self.name,
                success=False,
                message="缺少 chat_id",
                data={},
            )

        tasks = self.task_service.list_tasks_by_chat_id(chat_id) or []
        if not tasks:
            return ToolResult(
                tool_name=self.name,
                success=False,
                message="我暂时没有找到可直接重跑的历史处理记录。你可以重新上传试卷 PDF 和解析 PDF，我会为你创建一个新的任务再处理。",
                data={},
            )

        source_task = self._find_latest_history_task_with_materials(
            tasks=tasks,
            current_task_id=current_task_id,
        )
        if not source_task:
            return ToolResult(
                tool_name=self.name,
                success=False,
                message="我没有找到一条可直接重跑的历史任务，或者那次任务缺少可用材料。你可以重新上传试卷 PDF 和解析 PDF，我会为你创建新的任务继续处理。",
                data={},
            )

        source_task_id = source_task["task_id"]
        latest_materials = self.task_file_service.get_latest_materials_summary(source_task_id)
        blank_record = latest_materials.get("blank_pdf_record")
        solution_record = latest_materials.get("solution_pdf_record")

        if not blank_record or not solution_record:
            return ToolResult(
                tool_name=self.name,
                success=False,
                message="上一条历史任务缺少完整的试卷或解析材料，所以我不能直接重跑。请重新上传试卷 PDF 和解析 PDF，我会重新为你创建任务。",
                data={},
            )

        blank_local_path = blank_record.get("local_path")
        solution_local_path = solution_record.get("local_path")

        if not blank_local_path or not os.path.exists(blank_local_path):
            return ToolResult(
                tool_name=self.name,
                success=False,
                message="上一条历史任务对应的本地试卷材料已经不存在了，所以我不能直接重跑。请重新上传试卷 PDF 和解析 PDF，我会为你创建一个新的任务再处理。",
                data={},
            )

        if not solution_local_path or not os.path.exists(solution_local_path):
            return ToolResult(
                tool_name=self.name,
                success=False,
                message="上一条历史任务对应的本地解析材料已经不存在了，所以我不能直接重跑。请重新上传试卷 PDF 和解析 PDF，我会为你创建一个新的任务再处理。",
                data={},
            )

        new_task = self.task_service.create_task(
            chat_id=chat_id,
            created_by="agent_rerun",
        )
        new_task_id = new_task["task_id"]

        clone_result = self.task_file_service.clone_latest_materials_to_task(
            source_task_id=source_task_id,
            target_task_id=new_task_id,
        )

        latest_new_materials = clone_result["latest_materials_summary"]
        if not latest_new_materials.get("is_ready"):
            return ToolResult(
                tool_name=self.name,
                success=False,
                message="我已经创建了新的任务，但历史材料复制后仍不完整，暂时不能继续处理。请重新上传试卷 PDF 和解析 PDF，我会接着为你处理。",
                data={
                    "new_task_id": new_task_id,
                    "source_task_id": source_task_id,
                },
            )

        materials_text = self.task_file_service.build_user_friendly_materials_text(new_task_id)

        self.task_memory_service.update_processing_summary(
            task_id=new_task_id,
            current_stage="collecting_materials",
            processing_summary=f"{materials_text} 已基于上一条历史任务创建新的待处理任务，等待你确认是否开始处理。",
        )
        self.task_memory_service.update_next_action_hint(
            task_id=new_task_id,
            current_stage="collecting_materials",
            next_action_hint="等待用户确认材料",
        )

        self.task_service.advance_stage(
            task_id=new_task_id,
            current_stage="waiting_confirmation",
            next_action_hint="请用户确认是否开始重新处理",
        )

        self.chat_session_service.bind_task(
            chat_id=chat_id,
            task_id=new_task_id,
        )
        self.chat_session_service.update_summary_memory(
            chat_id=chat_id,
            summary_memory=f"已基于历史任务 {source_task_id} 创建新的重跑任务 {new_task_id}",
        )

        blank_name = latest_new_materials.get("blank_pdf_name")
        solution_name = latest_new_materials.get("solution_pdf_name")

        return ToolResult(
            tool_name=self.name,
            success=True,
            message=(
                f"我已经基于上一条历史任务的材料创建了一个新的待处理任务。"
                f"当前材料已就绪：试卷 {blank_name}，解析 {solution_name}。"
                f"回复“开始”即可重新处理。"
            ),
            data={
                "source_task_id": source_task_id,
                "new_task_id": new_task_id,
                "latest_materials_summary": latest_new_materials,
            },
        )

    def _find_latest_history_task_with_materials(
        self,
        tasks: list[dict],
        current_task_id: str | None,
    ) -> dict | None:
        for task in tasks:
            task_id = task.get("task_id")
            if not task_id:
                continue

            if current_task_id and task_id == current_task_id:
                continue

            latest_materials = self.task_file_service.get_latest_materials_summary(task_id)
            blank_record = latest_materials.get("blank_pdf_record")
            solution_record = latest_materials.get("solution_pdf_record")

            if blank_record and solution_record:
                return task

        return None