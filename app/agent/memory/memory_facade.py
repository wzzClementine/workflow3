from __future__ import annotations

import json
from typing import Any

from app.services.task import TaskService
from app.services.session import ChatSessionService
from app.services.memory import TaskMemoryService
from app.services.file import TaskFileService


class MemoryFacade:
    def __init__(
        self,
        task_service: TaskService,
        chat_session_service: ChatSessionService,
        task_memory_service: TaskMemoryService,
        task_file_service: TaskFileService,
    ):
        self.task_service = task_service
        self.chat_session_service = chat_session_service
        self.task_memory_service = task_memory_service
        self.task_file_service = task_file_service

    def get_chat_context(
        self,
        chat_id: str,
    ) -> dict[str, Any]:
        session = self.chat_session_service.get_session(chat_id)

        if not session:
            return {
                "session": None,
                "task": None,
                "task_memory": None,
            }

        current_task_id = session.get("current_task_id")
        task = self.task_service.get_task(current_task_id) if current_task_id else None
        task_memory = (
            self.task_memory_service.get_memory(current_task_id)
            if current_task_id
            else None
        )

        return {
            "session": session,
            "task": task,
            "task_memory": task_memory,
        }

    def get_task_context(
        self,
        task_id: str,
    ) -> dict[str, Any]:
        task = self.task_service.get_task(task_id)
        task_memory = self.task_memory_service.get_memory(task_id)

        return {
            "task": task,
            "task_memory": task_memory,
        }

    def _safe_load_json(self, raw: str | None, default: Any) -> Any:
        if not raw:
            return default
        try:
            return json.loads(raw)
        except Exception:
            return default

    def _fmt_material_pair(self, latest_materials_summary: dict[str, Any]) -> str:
        blank_name = latest_materials_summary.get("blank_pdf_name")
        solution_name = latest_materials_summary.get("solution_pdf_name")
        blank_pages = latest_materials_summary.get("blank_pdf_pages")
        solution_pages = latest_materials_summary.get("solution_pdf_pages")

        def _fmt(name: str | None, pages: int | None) -> str:
            if not name:
                return "未知文件"
            if isinstance(pages, int) and pages > 0:
                return f"{name}（{pages}页）"
            return name

        parts = []
        if blank_name:
            parts.append(_fmt(blank_name, blank_pages))
        if solution_name:
            parts.append(_fmt(solution_name, solution_pages))

        if parts:
            return " + ".join(parts)

        return "未识别到明确材料"

    def _build_current_task_summary(
        self,
        task: dict[str, Any] | None,
        task_memory: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if not task:
            return None

        task_id = task.get("task_id")
        files_summary = {}
        processing_summary = None
        last_error = None
        next_action_hint = None
        completed_steps = []
        latest_materials_summary = {}

        if task_memory:
            files_summary = self._safe_load_json(
                task_memory.get("files_summary_json"),
                {},
            )
            completed_steps = self._safe_load_json(
                task_memory.get("completed_steps_json"),
                [],
            )
            processing_summary = task_memory.get("processing_summary")
            last_error = task_memory.get("last_error")
            next_action_hint = task_memory.get("next_action_hint")

        if task_id:
            latest_materials_summary = self.task_file_service.get_latest_materials_summary(task_id)

        return {
            "task_id": task_id,
            "status": task.get("status"),
            "stage": task.get("current_stage"),
            "created_at": task.get("created_at"),
            "updated_at": task.get("updated_at"),
            "completed_at": task.get("completed_at"),
            "processing_summary": processing_summary,
            "last_error": last_error,
            "next_action_hint": next_action_hint,
            "files_summary": files_summary,
            "completed_steps": completed_steps,
            "latest_materials_summary": latest_materials_summary,
        }

    def _build_recent_tasks(
        self,
        chat_id: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        tasks = self.task_service.list_tasks_by_chat_id(chat_id) or []
        recent = tasks[:limit]

        results: list[dict[str, Any]] = []
        for task in recent:
            task_id = task.get("task_id")
            task_memory = self.task_memory_service.get_memory(task_id) if task_id else None

            processing_summary = None
            last_error = None
            if task_memory:
                processing_summary = task_memory.get("processing_summary")
                last_error = task_memory.get("last_error")

            latest_materials_summary = (
                self.task_file_service.get_latest_materials_summary(task_id)
                if task_id
                else {}
            )

            results.append(
                {
                    "task_id": task_id,
                    "status": task.get("status"),
                    "stage": task.get("current_stage"),
                    "created_at": task.get("created_at"),
                    "updated_at": task.get("updated_at"),
                    "completed_at": task.get("completed_at"),
                    "processing_summary": processing_summary,
                    "last_error": last_error,
                    "latest_materials_summary": latest_materials_summary,
                }
            )

        return results

    def _build_recent_tasks_readable(
        self,
        recent_tasks: list[dict[str, Any]],
        current_task_id: str | None,
    ) -> list[dict[str, Any]]:
        readable: list[dict[str, Any]] = []

        for task in recent_tasks:
            task_id = task.get("task_id")
            status = task.get("status")
            stage = task.get("stage")
            latest_materials_summary = task.get("latest_materials_summary") or {}
            materials_text = self._fmt_material_pair(latest_materials_summary)
            last_error = task.get("last_error")

            if task_id == current_task_id:
                relation = "current"
            else:
                relation = "history"

            if status == "completed":
                status_text = "已完成"
            elif status == "failed":
                status_text = "失败"
            else:
                if stage == "waiting_confirmation":
                    status_text = "等待确认"
                elif stage == "collecting_materials":
                    status_text = "收集材料中"
                elif stage == "processing":
                    status_text = "处理中"
                else:
                    status_text = "进行中"

            readable.append(
                {
                    "relation": relation,
                    "status_text": status_text,
                    "materials_text": materials_text,
                    "has_error": bool(last_error),
                    "error_text": last_error,
                    "completed_at": task.get("completed_at"),
                    "processing_summary": task.get("processing_summary"),
                }
            )

        return readable

    def build_agent_snapshot(
        self,
        chat_id: str,
    ) -> dict[str, Any]:
        context = self.get_chat_context(chat_id)

        session = context["session"]
        task = context["task"]
        task_memory = context["task_memory"]

        current_task_summary = self._build_current_task_summary(
            task=task,
            task_memory=task_memory,
        )
        recent_tasks = self._build_recent_tasks(chat_id=chat_id, limit=5)

        current_files_summary = {}
        current_task_id = session.get("current_task_id") if session else None

        if current_task_summary:
            current_files_summary = current_task_summary.get("latest_materials_summary") or {}

        recent_tasks_readable = self._build_recent_tasks_readable(
            recent_tasks=recent_tasks,
            current_task_id=current_task_id,
        )

        return {
            "chat_id": chat_id,
            "has_session": session is not None,
            "has_task": task is not None,
            "session": session,
            "task": task,
            "task_memory": task_memory,
            "current_task_id": current_task_id,
            "current_stage": task.get("current_stage") if task else None,
            "waiting_for": session.get("waiting_for") if session else None,
            "next_action_hint": task_memory.get("next_action_hint") if task_memory else None,
            "current_task_summary": current_task_summary,
            "recent_tasks": recent_tasks,
            "recent_tasks_readable": recent_tasks_readable,
            "current_files_summary": current_files_summary,
        }