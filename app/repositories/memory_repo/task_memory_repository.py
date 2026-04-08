from __future__ import annotations

from datetime import datetime
from typing import Any

from app.infrastructure.db.sqlite_manager import SQLiteManager


class TaskMemoryRepository:
    def __init__(self, sqlite_manager: SQLiteManager):
        self.sqlite_manager = sqlite_manager

    def get_by_task_id(self, task_id: str) -> dict[str, Any] | None:
        return self.sqlite_manager.fetch_one(
            """
            SELECT *
            FROM task_memory
            WHERE task_id = ?
            """,
            (task_id,),
        )

    def upsert_memory(
        self,
        task_id: str,
        current_stage: str,
        completed_steps_json: str | None = None,
        files_summary_json: str | None = None,
        processing_summary: str | None = None,
        last_error: str | None = None,
        next_action_hint: str | None = None,
    ) -> dict[str, Any] | None:
        now = datetime.now().isoformat(timespec="seconds")
        existing = self.get_by_task_id(task_id)

        if not existing:
            self.sqlite_manager.execute(
                """
                INSERT INTO task_memory (
                    task_id,
                    current_stage,
                    completed_steps_json,
                    files_summary_json,
                    processing_summary,
                    last_error,
                    next_action_hint,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    current_stage,
                    completed_steps_json,
                    files_summary_json,
                    processing_summary,
                    last_error,
                    next_action_hint,
                    now,
                    now,
                ),
            )
        else:
            self.sqlite_manager.execute(
                """
                UPDATE task_memory
                SET current_stage = ?,
                    completed_steps_json = ?,
                    files_summary_json = ?,
                    processing_summary = ?,
                    last_error = ?,
                    next_action_hint = ?,
                    updated_at = ?
                WHERE task_id = ?
                """,
                (
                    current_stage,
                    completed_steps_json if completed_steps_json is not None else existing["completed_steps_json"],
                    files_summary_json if files_summary_json is not None else existing["files_summary_json"],
                    processing_summary if processing_summary is not None else existing["processing_summary"],
                    last_error if last_error is not None else existing["last_error"],
                    next_action_hint if next_action_hint is not None else existing["next_action_hint"],
                    now,
                    task_id,
                ),
            )

        return self.get_by_task_id(task_id)

    def update_last_error(
        self,
        task_id: str,
        last_error: str,
    ) -> dict[str, Any] | None:
        now = datetime.now().isoformat(timespec="seconds")

        self.sqlite_manager.execute(
            """
            UPDATE task_memory
            SET last_error = ?, updated_at = ?
            WHERE task_id = ?
            """,
            (last_error, now, task_id),
        )

        return self.get_by_task_id(task_id)

    def update_next_action_hint(
        self,
        task_id: str,
        next_action_hint: str,
    ) -> dict[str, Any] | None:
        now = datetime.now().isoformat(timespec="seconds")

        self.sqlite_manager.execute(
            """
            UPDATE task_memory
            SET next_action_hint = ?, updated_at = ?
            WHERE task_id = ?
            """,
            (next_action_hint, now, task_id),
        )

        return self.get_by_task_id(task_id)