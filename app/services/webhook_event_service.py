from datetime import datetime
from typing import Any

from app.db.sqlite_manager import sqlite_manager
from app.utils.logger import setup_logger
from app.config import settings

logger = setup_logger(settings.log_level, settings.logs_dir)


class WebhookEventService:
    def get_by_event_key(self, event_key: str) -> dict[str, Any] | None:
        return sqlite_manager.fetch_one(
            """
            SELECT * FROM webhook_events
            WHERE event_key = ?
            """,
            (event_key,),
        )

    def create_processing_event(
        self,
        event_key: str,
        event_type: str,
        task_id: str | None = None,
        detail_json: str | None = None,
    ) -> dict[str, Any] | None:
        now = datetime.now().isoformat(timespec="seconds")

        sqlite_manager.execute(
            """
            INSERT INTO webhook_events (
                event_key, event_type, status, task_id, detail_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_key,
                event_type,
                "processing",
                task_id,
                detail_json,
                now,
                now,
            ),
        )

        return self.get_by_event_key(event_key)

    def update_event_status(
        self,
        event_key: str,
        status: str,
        task_id: str | None = None,
        detail_json: str | None = None,
    ) -> dict[str, Any] | None:
        now = datetime.now().isoformat(timespec="seconds")

        old = self.get_by_event_key(event_key)
        if not old:
            raise ValueError(f"webhook event 不存在: {event_key}")

        sqlite_manager.execute(
            """
            UPDATE webhook_events
            SET status = ?, task_id = ?, detail_json = ?, updated_at = ?
            WHERE event_key = ?
            """,
            (
                status,
                task_id if task_id is not None else old.get("task_id"),
                detail_json if detail_json is not None else old.get("detail_json"),
                now,
                event_key,
            ),
        )

        return self.get_by_event_key(event_key)

    def delete_event(self, event_key: str) -> None:
        sqlite_manager.execute(
            """
            DELETE FROM webhook_events
            WHERE event_key = ?
            """,
            (event_key,),
        )

    def begin_event_once(
        self,
        event_key: str,
        event_type: str,
        task_id: str | None = None,
        detail_json: str | None = None,
    ) -> tuple[bool, dict[str, Any] | None]:
        """
        返回:
        - (True, row): 本次是首次处理，已经写入 processing
        - (False, row): 已存在，说明重复事件
        """
        existing = self.get_by_event_key(event_key)
        if existing:
            return False, existing

        row = self.create_processing_event(
            event_key=event_key,
            event_type=event_type,
            task_id=task_id,
            detail_json=detail_json,
        )
        return True, row


webhook_event_service = WebhookEventService()