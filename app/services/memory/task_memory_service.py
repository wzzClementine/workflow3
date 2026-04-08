from __future__ import annotations

from typing import Any

from app.repositories.memory_repo import TaskMemoryRepository


class TaskMemoryService:
    def __init__(self, task_memory_repository: TaskMemoryRepository):
        self.task_memory_repository = task_memory_repository

    def get_memory(self, task_id: str) -> dict[str, Any] | None:
        return self.task_memory_repository.get_by_task_id(task_id)

    def init_memory_if_missing(
        self,
        task_id: str,
        current_stage: str,
    ) -> dict[str, Any]:
        existing = self.task_memory_repository.get_by_task_id(task_id)
        if existing:
            return existing

        created = self.task_memory_repository.upsert_memory(
            task_id=task_id,
            current_stage=current_stage,
            completed_steps_json="[]",
            files_summary_json="{}",
            processing_summary="任务记忆已初始化",
            last_error=None,
            next_action_hint=None,
        )

        if not created:
            raise ValueError(f"初始化任务记忆失败: {task_id}")

        return created

    def update_stage(
        self,
        task_id: str,
        current_stage: str,
        next_action_hint: str | None = None,
    ) -> dict[str, Any]:
        self.init_memory_if_missing(task_id, current_stage)

        updated = self.task_memory_repository.upsert_memory(
            task_id=task_id,
            current_stage=current_stage,
            next_action_hint=next_action_hint,
        )

        if not updated:
            raise ValueError(f"更新任务阶段记忆失败: {task_id}")

        return updated

    def update_processing_summary(
        self,
        task_id: str,
        current_stage: str,
        processing_summary: str,
    ) -> dict[str, Any]:
        self.init_memory_if_missing(task_id, current_stage)

        updated = self.task_memory_repository.upsert_memory(
            task_id=task_id,
            current_stage=current_stage,
            processing_summary=processing_summary,
        )

        if not updated:
            raise ValueError(f"更新处理摘要失败: {task_id}")

        return updated

    def update_last_error(
        self,
        task_id: str,
        current_stage: str,
        last_error: str,
    ) -> dict[str, Any]:
        self.init_memory_if_missing(task_id, current_stage)

        updated = self.task_memory_repository.upsert_memory(
            task_id=task_id,
            current_stage=current_stage,
            last_error=last_error,
        )

        if not updated:
            raise ValueError(f"更新任务错误失败: {task_id}")

        return updated

    def update_next_action_hint(
        self,
        task_id: str,
        current_stage: str,
        next_action_hint: str,
    ) -> dict[str, Any]:
        self.init_memory_if_missing(task_id, current_stage)

        updated = self.task_memory_repository.upsert_memory(
            task_id=task_id,
            current_stage=current_stage,
            next_action_hint=next_action_hint,
        )

        if not updated:
            raise ValueError(f"更新下一步提示失败: {task_id}")

        return updated