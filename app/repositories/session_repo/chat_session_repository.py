from __future__ import annotations

from datetime import datetime
from typing import Any

from app.infrastructure.db.sqlite_manager import SQLiteManager


class ChatSessionRepository:
    def __init__(self, sqlite_manager: SQLiteManager):
        self.sqlite_manager = sqlite_manager

    def get_by_chat_id(self, chat_id: str) -> dict[str, Any] | None:
        return self.sqlite_manager.fetch_one(
            """
            SELECT *
            FROM chat_sessions
            WHERE chat_id = ?
            """,
            (chat_id,),
        )

    def upsert_session(
        self,
        chat_id: str,
        current_task_id: str | None = None,
        current_mode: str = "idle",
        waiting_for: str | None = None,
        last_user_message: str | None = None,
        last_message_type: str | None = None,
        last_uploaded_file_name: str | None = None,
        last_uploaded_file_key: str | None = None,
        summary_memory: str | None = None,
    ) -> dict[str, Any] | None:
        now = datetime.now().isoformat(timespec="seconds")
        existing = self.get_by_chat_id(chat_id)

        if not existing:
            self.sqlite_manager.execute(
                """
                INSERT INTO chat_sessions (
                    chat_id,
                    current_task_id,
                    current_mode,
                    waiting_for,
                    last_user_message,
                    last_message_type,
                    last_uploaded_file_name,
                    last_uploaded_file_key,
                    summary_memory,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chat_id,
                    current_task_id,
                    current_mode,
                    waiting_for,
                    last_user_message,
                    last_message_type,
                    last_uploaded_file_name,
                    last_uploaded_file_key,
                    summary_memory,
                    now,
                    now,
                ),
            )
        else:
            self.sqlite_manager.execute(
                """
                UPDATE chat_sessions
                SET current_task_id = ?,
                    current_mode = ?,
                    waiting_for = ?,
                    last_user_message = ?,
                    last_message_type = ?,
                    last_uploaded_file_name = ?,
                    last_uploaded_file_key = ?,
                    summary_memory = ?,
                    updated_at = ?
                WHERE chat_id = ?
                """,
                (
                    current_task_id if current_task_id is not None else existing["current_task_id"],
                    current_mode if current_mode is not None else existing["current_mode"],
                    waiting_for if waiting_for is not None else existing["waiting_for"],
                    last_user_message if last_user_message is not None else existing["last_user_message"],
                    last_message_type if last_message_type is not None else existing["last_message_type"],
                    last_uploaded_file_name if last_uploaded_file_name is not None else existing["last_uploaded_file_name"],
                    last_uploaded_file_key if last_uploaded_file_key is not None else existing["last_uploaded_file_key"],
                    summary_memory if summary_memory is not None else existing["summary_memory"],
                    now,
                    chat_id,
                ),
            )

        return self.get_by_chat_id(chat_id)

    def update_current_task(
        self,
        chat_id: str,
        current_task_id: str,
    ) -> dict[str, Any] | None:
        now = datetime.now().isoformat(timespec="seconds")

        self.sqlite_manager.execute(
            """
            UPDATE chat_sessions
            SET current_task_id = ?, updated_at = ?
            WHERE chat_id = ?
            """,
            (current_task_id, now, chat_id),
        )

        return self.get_by_chat_id(chat_id)

    def update_waiting_for(
        self,
        chat_id: str,
        waiting_for: str | None,
    ) -> dict[str, Any] | None:
        now = datetime.now().isoformat(timespec="seconds")

        self.sqlite_manager.execute(
            """
            UPDATE chat_sessions
            SET waiting_for = ?, updated_at = ?
            WHERE chat_id = ?
            """,
            (waiting_for, now, chat_id),
        )

        return self.get_by_chat_id(chat_id)

    def update_summary_memory(
        self,
        chat_id: str,
        summary_memory: str,
    ) -> dict[str, Any] | None:
        now = datetime.now().isoformat(timespec="seconds")

        self.sqlite_manager.execute(
            """
            UPDATE chat_sessions
            SET summary_memory = ?, updated_at = ?
            WHERE chat_id = ?
            """,
            (summary_memory, now, chat_id),
        )

        return self.get_by_chat_id(chat_id)