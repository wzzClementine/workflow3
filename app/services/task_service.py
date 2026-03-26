from datetime import datetime
from uuid import uuid4
from typing import Any

from app.db.sqlite_manager import sqlite_manager
from app.utils.logger import setup_logger
from app.config import settings

logger = setup_logger(settings.log_level, settings.logs_dir)


class TaskService:
    VALID_STATUSES = {
        "created",
        "running",
        "waiting_manual",
        "success",
        "failed",
    }

    def generate_task_id(self) -> str:
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = uuid4().hex[:4]
        return f"task_{now}_{suffix}"

    def create_task(
        self,
        task_type: str = "workflow3",
        paper_id: str | None = None,
        created_by: str | None = None,
        input_path: str | None = None,
        output_path: str | None = None,
    ) -> dict[str, Any]:
        task_id = self.generate_task_id()
        now = datetime.now().isoformat(timespec="seconds")

        sqlite_manager.execute(
            """
            INSERT INTO tasks (
                task_id, task_type, paper_id, status,
                input_path, output_path, error_message,
                created_by, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                task_type,
                paper_id,
                "created",
                input_path,
                output_path,
                None,
                created_by,
                now,
                now,
            )
        )

        task = sqlite_manager.fetch_one(
            "SELECT * FROM tasks WHERE task_id = ?",
            (task_id,),
        )

        logger.info("Task created successfully: %s", task_id)
        return task

    def get_task_by_id(self, task_id: str) -> dict[str, Any] | None:
        return sqlite_manager.fetch_one(
            "SELECT * FROM tasks WHERE task_id = ?",
            (task_id,),
        )

    def is_valid_status(self, status: str) -> bool:
        return status in self.VALID_STATUSES

    def update_task_status(
        self,
        task_id: str,
        status: str,
        error_message: str | None = None,
        output_path: str | None = None,
    ) -> dict[str, Any]:
        if not self.is_valid_status(status):
            raise ValueError(f"非法状态: {status}")

        task = self.get_task_by_id(task_id)
        if not task:
            raise ValueError(f"任务不存在: {task_id}")

        now = datetime.now().isoformat(timespec="seconds")

        sqlite_manager.execute(
            """
            UPDATE tasks
            SET status = ?, error_message = ?, output_path = ?, updated_at = ?
            WHERE task_id = ?
            """,
            (
                status,
                error_message,
                output_path,
                now,
                task_id,
            )
        )

        updated_task = self.get_task_by_id(task_id)
        logger.info("Task status updated successfully: %s -> %s", task_id, status)
        return updated_task

    def attach_paper_to_task(self, task_id: str, paper_id: str) -> dict[str, Any]:
        task = self.get_task_by_id(task_id)
        if not task:
            raise ValueError(f"任务不存在: {task_id}")

        now = datetime.now().isoformat(timespec="seconds")

        sqlite_manager.execute(
            """
            UPDATE tasks
            SET paper_id = ?, updated_at = ?
            WHERE task_id = ?
            """,
            (paper_id, now, task_id)
        )

        updated_task = self.get_task_by_id(task_id)
        logger.info("Paper attached to task: task_id=%s, paper_id=%s", task_id, paper_id)
        return updated_task


task_service = TaskService()