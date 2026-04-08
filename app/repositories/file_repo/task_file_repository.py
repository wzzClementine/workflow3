from __future__ import annotations

from datetime import datetime
from typing import Any

from app.infrastructure.db.sqlite_manager import SQLiteManager


class TaskFileRepository:
    def __init__(self, sqlite_manager: SQLiteManager):
        self.sqlite_manager = sqlite_manager

    def create_file(
        self,
        file_id: str,
        task_id: str,
        file_role: str,
        file_name: str,
        file_ext: str | None,
        storage_type: str,
        local_path: str | None = None,
        remote_key: str | None = None,
        remote_url: str | None = None,
        page_count: int | None = None,
        file_hash: str | None = None,
        status: str = "active",
        metadata_json: str | None = None,
    ) -> dict[str, Any] | None:
        now = datetime.now().isoformat(timespec="seconds")

        self.sqlite_manager.execute(
            """
            INSERT INTO task_files (
                file_id,
                task_id,
                file_role,
                file_name,
                file_ext,
                storage_type,
                local_path,
                remote_key,
                remote_url,
                page_count,
                file_hash,
                status,
                metadata_json,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                file_id,
                task_id,
                file_role,
                file_name,
                file_ext,
                storage_type,
                local_path,
                remote_key,
                remote_url,
                page_count,
                file_hash,
                status,
                metadata_json,
                now,
                now,
            ),
        )

        return self.get_by_file_id(file_id)

    def get_by_file_id(self, file_id: str) -> dict[str, Any] | None:
        return self.sqlite_manager.fetch_one(
            """
            SELECT *
            FROM task_files
            WHERE file_id = ?
            """,
            (file_id,),
        )

    def list_by_task_id(self, task_id: str) -> list[dict[str, Any]]:
        return self.sqlite_manager.fetch_all(
            """
            SELECT *
            FROM task_files
            WHERE task_id = ?
            ORDER BY id ASC
            """,
            (task_id,),
        )

    def list_by_task_id_and_role(
        self,
        task_id: str,
        file_role: str,
    ) -> list[dict[str, Any]]:
        return self.sqlite_manager.fetch_all(
            """
            SELECT *
            FROM task_files
            WHERE task_id = ? AND file_role = ?
            ORDER BY id ASC
            """,
            (task_id, file_role),
        )

    def get_latest_by_task_id_and_role(
        self,
        task_id: str,
        file_role: str,
    ) -> dict[str, Any] | None:
        return self.sqlite_manager.fetch_one(
            """
            SELECT *
            FROM task_files
            WHERE task_id = ? AND file_role = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (task_id, file_role),
        )