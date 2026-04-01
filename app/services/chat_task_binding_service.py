# app/services/chat_task_binding_service.py

from datetime import datetime
from app.db.sqlite_manager import sqlite_manager


class ChatTaskBindingService:

    def bind(self, chat_id: str, task_id: str):
        now = datetime.now().isoformat(timespec="seconds")

        sqlite_manager.execute(
            """
            INSERT INTO chat_task_binding (chat_id, task_id, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                task_id = excluded.task_id,
                updated_at = excluded.updated_at
            """,
            (chat_id, task_id, now),
        )

    def get_task_id(self, chat_id: str) -> str | None:
        row = sqlite_manager.fetch_one(
            """
            SELECT task_id FROM chat_task_binding
            WHERE chat_id = ?
            """,
            (chat_id,),
        )
        return row["task_id"] if row else None


chat_task_binding_service = ChatTaskBindingService()