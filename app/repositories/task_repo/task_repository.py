from __future__ import annotations

from datetime import datetime
from typing import Any

from app.infrastructure.db.sqlite_manager import SQLiteManager


class TaskRepository:
    def __init__(self, sqlite_manager: SQLiteManager):
        self.sqlite_manager = sqlite_manager

    def create_task(
        self,
        task_id: str,
        chat_id: str | None,
        status: str,
        current_stage: str,
        created_by: str | None = None,
    ) -> dict[str, Any] | None:
        now = datetime.now().isoformat(timespec="seconds")

        self.sqlite_manager.execute(
            """
            INSERT INTO tasks (
                task_id,
                chat_id,
                status,
                current_stage,
                created_by,
                error_message,
                created_at,
                updated_at,
                completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                chat_id,
                status,
                current_stage,
                created_by,
                None,
                now,
                now,
                None,
            ),
        )

        return self.get_by_task_id(task_id)

    def get_by_task_id(self, task_id: str) -> dict[str, Any] | None:
        return self.sqlite_manager.fetch_one(
            """
            SELECT *
            FROM tasks
            WHERE task_id = ?
            """,
            (task_id,),
        )

    def list_by_chat_id(self, chat_id: str) -> list[dict[str, Any]]:
        return self.sqlite_manager.fetch_all(
            """
            SELECT *
            FROM tasks
            WHERE chat_id = ?
            ORDER BY id DESC
            """,
            (chat_id,),
        )

    def update_status(
        self,
        task_id: str,
        status: str,
    ) -> dict[str, Any] | None:
        now = datetime.now().isoformat(timespec="seconds")

        self.sqlite_manager.execute(
            """
            UPDATE tasks
            SET status = ?, updated_at = ?
            WHERE task_id = ?
            """,
            (status, now, task_id),
        )

        return self.get_by_task_id(task_id)

    def update_stage(
        self,
        task_id: str,
        current_stage: str,
    ) -> dict[str, Any] | None:
        now = datetime.now().isoformat(timespec="seconds")

        self.sqlite_manager.execute(
            """
            UPDATE tasks
            SET current_stage = ?, updated_at = ?
            WHERE task_id = ?
            """,
            (current_stage, now, task_id),
        )

        return self.get_by_task_id(task_id)

    def mark_completed(
        self,
        task_id: str,
    ) -> dict[str, Any] | None:
        now = datetime.now().isoformat(timespec="seconds")

        self.sqlite_manager.execute(
            """
            UPDATE tasks
            SET status = ?, current_stage = ?, completed_at = ?, updated_at = ?
            WHERE task_id = ?
            """,
            ("completed", "completed", now, now, task_id),
        )

        return self.get_by_task_id(task_id)

    def mark_failed(
        self,
        task_id: str,
        error_message: str,
    ) -> dict[str, Any] | None:
        now = datetime.now().isoformat(timespec="seconds")

        self.sqlite_manager.execute(
            """
            UPDATE tasks
            SET status = ?, current_stage = ?, error_message = ?, updated_at = ?
            WHERE task_id = ?
            """,
            ("failed", "failed", error_message, now, task_id),
        )

        return self.get_by_task_id(task_id)