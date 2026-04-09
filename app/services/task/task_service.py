from __future__ import annotations

import uuid
from typing import Any

from app.repositories.task_repo import TaskRepository
from app.repositories.memory_repo import TaskMemoryRepository


class TaskService:
    def __init__(
        self,
        task_repository: TaskRepository,
        task_memory_repository: TaskMemoryRepository,
    ):
        self.task_repository = task_repository
        self.task_memory_repository = task_memory_repository

    def create_task(
        self,
        chat_id: str | None,
        created_by: str | None = None,
        initial_status: str = "created",
        initial_stage: str = "collecting_materials",
    ) -> dict[str, Any]:
        task_id = f"task_{uuid.uuid4().hex[:12]}"

        task = self.task_repository.create_task(
            task_id=task_id,
            chat_id=chat_id,
            status=initial_status,
            current_stage=initial_stage,
            created_by=created_by,
        )

        self.task_memory_repository.upsert_memory(
            task_id=task_id,
            current_stage=initial_stage,
            completed_steps_json='["task_created"]',
            files_summary_json='{"blank_pdf": false, "solution_pdf": false}',
            processing_summary="任务已创建，等待上传材料",
            last_error=None,
            next_action_hint="等待上传 blank_pdf 和 solution_pdf",
        )

        if not task:
            raise ValueError("任务创建失败")

        return task

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        return self.task_repository.get_by_task_id(task_id)

    def list_tasks_by_chat_id(self, chat_id: str) -> list[dict[str, Any]]:
        return self.task_repository.list_by_chat_id(chat_id)

    def advance_stage(
        self,
        task_id: str,
        current_stage: str,
        next_action_hint: str | None = None,
    ) -> dict[str, Any]:
        task = self.task_repository.update_stage(task_id, current_stage)
        self.task_memory_repository.upsert_memory(
            task_id=task_id,
            current_stage=current_stage,
            next_action_hint=next_action_hint,
        )

        if not task:
            raise ValueError(f"任务不存在: {task_id}")

        return task

    def update_status(
        self,
        task_id: str,
        status: str,
    ) -> dict[str, Any]:
        task = self.task_repository.update_status(task_id, status)
        if not task:
            raise ValueError(f"任务不存在: {task_id}")
        return task

    def mark_completed(
        self,
        task_id: str,
    ) -> dict[str, Any]:
        task = self.task_repository.mark_completed(task_id)

        self.task_memory_repository.upsert_memory(
            task_id=task_id,
            current_stage="completed",
            next_action_hint="任务已完成，无需后续动作",
            processing_summary="任务处理完成",
        )

        if not task:
            raise ValueError(f"任务不存在: {task_id}")

        return task

    def mark_failed(
        self,
        task_id: str,
        error_message: str,
    ) -> dict[str, Any]:
        task = self.task_repository.mark_failed(task_id, error_message)

        self.task_memory_repository.upsert_memory(
            task_id=task_id,
            current_stage="failed",
            last_error=error_message,
            next_action_hint="请检查错误并决定是否重试",
        )

        if not task:
            raise ValueError(f"任务不存在: {task_id}")

        return task

    def mark_cancelled(
        self,
        task_id: str,
    ) -> dict[str, Any]:
        task = self.task_repository.update_status(task_id, "cancelled")
        task = self.task_repository.update_stage(task_id, "cancelled")

        self.task_memory_repository.upsert_memory(
            task_id=task_id,
            current_stage="cancelled",
            processing_summary="任务已取消",
            next_action_hint="如需继续，请重新开始或重新上传材料",
        )

        if not task:
            raise ValueError(f"任务不存在: {task_id}")

        return task