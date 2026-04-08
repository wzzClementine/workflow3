from __future__ import annotations

from datetime import datetime
from typing import Any

from app.infrastructure.db.sqlite_manager import SQLiteManager


class DeliveryRecordRepository:
    def __init__(self, sqlite_manager: SQLiteManager):
        self.sqlite_manager = sqlite_manager

    def create_record(
        self,
        delivery_id: str,
        task_id: str,
        delivery_status: str,
        delivery_folder_name: str | None,
        local_package_path: str | None,
        feishu_folder_token: str | None,
        remote_url: str | None,
        delivered_at: str | None = None,
    ) -> dict[str, Any] | None:
        now = datetime.now().isoformat(timespec="seconds")

        self.sqlite_manager.execute(
            """
            INSERT INTO delivery_records (
                delivery_id,
                task_id,
                delivery_status,
                delivery_folder_name,
                local_package_path,
                feishu_folder_token,
                remote_url,
                delivered_at,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                delivery_id,
                task_id,
                delivery_status,
                delivery_folder_name,
                local_package_path,
                feishu_folder_token,
                remote_url,
                delivered_at,
                now,
                now,
            ),
        )

        return self.get_by_delivery_id(delivery_id)

    def get_by_delivery_id(self, delivery_id: str) -> dict[str, Any] | None:
        return self.sqlite_manager.fetch_one(
            """
            SELECT *
            FROM delivery_records
            WHERE delivery_id = ?
            """,
            (delivery_id,),
        )

    def list_by_task_id(self, task_id: str) -> list[dict[str, Any]]:
        return self.sqlite_manager.fetch_all(
            """
            SELECT *
            FROM delivery_records
            WHERE task_id = ?
            ORDER BY id DESC
            """,
            (task_id,),
        )