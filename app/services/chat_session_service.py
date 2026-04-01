from datetime import datetime
from typing import Any

from app.db.sqlite_manager import sqlite_manager


class ChatSessionService:
    def get_by_chat_id(self, chat_id: str) -> dict[str, Any] | None:
        return sqlite_manager.fetch_one(
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
        current_step: str | None = None,
        current_mode: str = "idle",
        last_user_message: str | None = None,
        last_message_type: str | None = None,
        last_uploaded_file_name: str | None = None,
        last_uploaded_file_key: str | None = None,
        waiting_for: str | None = None,
        summary_memory: str | None = None,
    ) -> dict[str, Any] | None:
        now = datetime.now().isoformat(timespec="seconds")

        existing = self.get_by_chat_id(chat_id)

        if existing:
            sqlite_manager.execute(
                """
                UPDATE chat_sessions
                SET current_task_id = ?,
                    current_step = ?,
                    current_mode = ?,
                    last_user_message = ?,
                    last_message_type = ?,
                    last_uploaded_file_name = ?,
                    last_uploaded_file_key = ?,
                    waiting_for = ?,
                    summary_memory = ?,
                    updated_at = ?
                WHERE chat_id = ?
                """,
                (
                    current_task_id if current_task_id is not None else existing.get("current_task_id"),
                    current_step if current_step is not None else existing.get("current_step"),
                    current_mode if current_mode is not None else existing.get("current_mode"),
                    last_user_message if last_user_message is not None else existing.get("last_user_message"),
                    last_message_type if last_message_type is not None else existing.get("last_message_type"),
                    last_uploaded_file_name if last_uploaded_file_name is not None else existing.get("last_uploaded_file_name"),
                    last_uploaded_file_key if last_uploaded_file_key is not None else existing.get("last_uploaded_file_key"),
                    waiting_for if waiting_for is not None else existing.get("waiting_for"),
                    summary_memory if summary_memory is not None else existing.get("summary_memory"),
                    now,
                    chat_id,
                ),
            )
        else:
            sqlite_manager.execute(
                """
                INSERT INTO chat_sessions (
                    chat_id,
                    current_task_id,
                    current_step,
                    current_mode,
                    last_user_message,
                    last_message_type,
                    last_uploaded_file_name,
                    last_uploaded_file_key,
                    waiting_for,
                    summary_memory,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chat_id,
                    current_task_id,
                    current_step,
                    current_mode,
                    last_user_message,
                    last_message_type,
                    last_uploaded_file_name,
                    last_uploaded_file_key,
                    waiting_for,
                    summary_memory,
                    now,
                    now,
                ),
            )

        return self.get_by_chat_id(chat_id)

    def update_current_task(
        self,
        chat_id: str,
        task_id: str | None,
    ) -> dict[str, Any] | None:
        return self.upsert_session(
            chat_id=chat_id,
            current_task_id=task_id,
        )

    def update_current_step(
        self,
        chat_id: str,
        current_step: str | None,
    ) -> dict[str, Any] | None:
        return self.upsert_session(
            chat_id=chat_id,
            current_step=current_step,
        )

    def update_mode(
        self,
        chat_id: str,
        current_mode: str,
    ) -> dict[str, Any] | None:
        return self.upsert_session(
            chat_id=chat_id,
            current_mode=current_mode,
        )

    def update_last_message(
        self,
        chat_id: str,
        message_type: str,
        message_text: str | None = None,
    ) -> dict[str, Any] | None:
        return self.upsert_session(
            chat_id=chat_id,
            last_message_type=message_type,
            last_user_message=message_text,
        )

    def update_last_uploaded_file(
        self,
        chat_id: str,
        file_name: str | None = None,
        file_key: str | None = None,
    ) -> dict[str, Any] | None:
        return self.upsert_session(
            chat_id=chat_id,
            last_uploaded_file_name=file_name,
            last_uploaded_file_key=file_key,
        )

    def update_waiting_for(
        self,
        chat_id: str,
        waiting_for: str | None,
    ) -> dict[str, Any] | None:
        return self.upsert_session(
            chat_id=chat_id,
            waiting_for=waiting_for,
        )

    def update_summary_memory(
        self,
        chat_id: str,
        summary_memory: str | None,
    ) -> dict[str, Any] | None:
        return self.upsert_session(
            chat_id=chat_id,
            summary_memory=summary_memory,
        )

    def clear_current_task(self, chat_id: str) -> dict[str, Any] | None:
        return self.upsert_session(
            chat_id=chat_id,
            current_task_id="",
        )

    def clear_waiting_for(self, chat_id: str) -> dict[str, Any] | None:
        return self.upsert_session(
            chat_id=chat_id,
            waiting_for="",
        )


chat_session_service = ChatSessionService()