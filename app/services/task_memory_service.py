from datetime import datetime
from typing import Any

from app.db.sqlite_manager import sqlite_manager


class TaskMemoryService:
    def get_by_task_id(self, task_id: str) -> dict[str, Any] | None:
        return sqlite_manager.fetch_one(
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
        summary: str | None = None,
        state_snapshot_json: str | None = None,
        missing_materials_json: str | None = None,
        last_successful_tool: str | None = None,
        last_failed_tool: str | None = None,
        last_error_analysis: str | None = None,
        next_recommended_action: str | None = None,
    ) -> dict[str, Any] | None:
        now = datetime.now().isoformat(timespec="seconds")

        existing = self.get_by_task_id(task_id)

        if existing:
            sqlite_manager.execute(
                """
                UPDATE task_memory
                SET summary = ?,
                    state_snapshot_json = ?,
                    missing_materials_json = ?,
                    last_successful_tool = ?,
                    last_failed_tool = ?,
                    last_error_analysis = ?,
                    next_recommended_action = ?,
                    updated_at = ?
                WHERE task_id = ?
                """,
                (
                    summary if summary is not None else existing.get("summary"),
                    state_snapshot_json if state_snapshot_json is not None else existing.get("state_snapshot_json"),
                    missing_materials_json if missing_materials_json is not None else existing.get("missing_materials_json"),
                    last_successful_tool if last_successful_tool is not None else existing.get("last_successful_tool"),
                    last_failed_tool if last_failed_tool is not None else existing.get("last_failed_tool"),
                    last_error_analysis if last_error_analysis is not None else existing.get("last_error_analysis"),
                    next_recommended_action if next_recommended_action is not None else existing.get("next_recommended_action"),
                    now,
                    task_id,
                ),
            )
        else:
            sqlite_manager.execute(
                """
                INSERT INTO task_memory (
                    task_id,
                    summary,
                    state_snapshot_json,
                    missing_materials_json,
                    last_successful_tool,
                    last_failed_tool,
                    last_error_analysis,
                    next_recommended_action,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    summary,
                    state_snapshot_json,
                    missing_materials_json,
                    last_successful_tool,
                    last_failed_tool,
                    last_error_analysis,
                    next_recommended_action,
                    now,
                    now,
                ),
            )

        return self.get_by_task_id(task_id)

    def update_summary(
        self,
        task_id: str,
        summary: str | None,
    ) -> dict[str, Any] | None:
        return self.upsert_memory(
            task_id=task_id,
            summary=summary,
        )

    def update_state_snapshot(
        self,
        task_id: str,
        state_snapshot_json: str | None,
    ) -> dict[str, Any] | None:
        return self.upsert_memory(
            task_id=task_id,
            state_snapshot_json=state_snapshot_json,
        )

    def update_missing_materials(
        self,
        task_id: str,
        missing_materials_json: str | None,
    ) -> dict[str, Any] | None:
        return self.upsert_memory(
            task_id=task_id,
            missing_materials_json=missing_materials_json,
        )

    def update_last_successful_tool(
        self,
        task_id: str,
        tool_name: str | None,
    ) -> dict[str, Any] | None:
        return self.upsert_memory(
            task_id=task_id,
            last_successful_tool=tool_name,
        )

    def update_last_failed_tool(
        self,
        task_id: str,
        tool_name: str | None,
        error_analysis: str | None = None,
    ) -> dict[str, Any] | None:
        return self.upsert_memory(
            task_id=task_id,
            last_failed_tool=tool_name,
            last_error_analysis=error_analysis,
        )

    def update_next_recommended_action(
        self,
        task_id: str,
        action: str | None,
    ) -> dict[str, Any] | None:
        return self.upsert_memory(
            task_id=task_id,
            next_recommended_action=action,
        )

    def clear_last_failed_tool(self, task_id: str) -> dict[str, Any] | None:
        return self.upsert_memory(
            task_id=task_id,
            last_failed_tool="",
            last_error_analysis="",
        )


task_memory_service = TaskMemoryService()