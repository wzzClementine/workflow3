from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from app.infrastructure.feishu import FeishuDriveClient
from app.repositories.delivery_repo import DeliveryRecordRepository
from app.repositories.task_repo import TaskRepository


class DeliveryService:
    def __init__(
        self,
        drive_client: FeishuDriveClient,
        delivery_record_repository: DeliveryRecordRepository,
        task_repository: TaskRepository,
    ):
        self.drive_client = drive_client
        self.delivery_record_repository = delivery_record_repository
        self.task_repository = task_repository

    def deliver_package_to_feishu(
        self,
        task_id: str,
        local_package_path: str,
        parent_folder_token: str,
    ) -> dict[str, Any]:
        if not Path(local_package_path).is_dir():
            raise NotADirectoryError(f"交付目录不存在: {local_package_path}")

        upload_result = self.drive_client.upload_directory_tree(
            local_dir=local_package_path,
            parent_folder_token=parent_folder_token,
            create_root_folder=True,
        )

        delivery_id = f"delivery_{uuid.uuid4().hex[:12]}"
        delivered_at = datetime.now().isoformat(timespec="seconds")

        remote_url = (
            upload_result.get("uploaded_file_url")
            or upload_result.get("root_folder_url")
            or ""
        )

        record = self.delivery_record_repository.create_record(
            delivery_id=delivery_id,
            task_id=task_id,
            delivery_status="success",
            delivery_folder_name=Path(local_package_path).name,
            local_package_path=local_package_path,
            feishu_folder_token=upload_result.get("root_folder_token"),
            remote_url=remote_url,
            delivered_at=delivered_at,
        )

        return {
            "delivery_id": delivery_id,
            "record": record,
            "upload_result": upload_result,
        }

    def get_result_by_task_id(self, task_id: str) -> dict[str, Any] | None:
        record = self.delivery_record_repository.get_latest_success_by_task_id(task_id)
        if not record:
            return None

        return {
            "task_id": task_id,
            "package_name": record.get("delivery_folder_name"),
            "remote_url": record.get("remote_url"),
        }

    def get_latest_result_by_chat_id(self, chat_id: str) -> dict[str, Any] | None:
        tasks = self.task_repository.list_by_chat_id(chat_id)
        if not tasks:
            return None

        task_ids = [t["task_id"] for t in tasks if t.get("task_id")]
        if not task_ids:
            return None

        record = self.delivery_record_repository.get_latest_success_by_task_ids(task_ids)
        if not record:
            return None

        return {
            "task_id": record.get("task_id"),
            "package_name": record.get("delivery_folder_name"),
            "remote_url": record.get("remote_url"),
        }

    def get_results_by_task_ids(self, task_ids: list[str]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []

        for task_id in task_ids:
            record = self.delivery_record_repository.get_latest_success_by_task_id(task_id)
            if not record:
                continue

            results.append(
                {
                    "task_id": task_id,
                    "package_name": record.get("delivery_folder_name"),
                    "remote_url": record.get("remote_url"),
                }
            )

        return results

    def get_completed_task_results_by_chat_id(self, chat_id: str) -> list[dict[str, Any]]:
        tasks = self.task_repository.list_by_chat_id(chat_id)
        if not tasks:
            return []

        completed_task_ids = [
            t["task_id"]
            for t in tasks
            if t.get("task_id") and t.get("status") == "completed"
        ]
        if not completed_task_ids:
            return []

        return self.get_results_by_task_ids(completed_task_ids)

    def get_latest_delivery_record_by_task_id(self, task_id: str) -> dict[str, Any] | None:
        """
        返回某个任务最近一次成功交付的完整记录。
        这里保留 local_package_path，供“重新上传结果”使用。
        """
        return self.delivery_record_repository.get_latest_success_by_task_id(task_id)

    def get_latest_completed_delivery_record_by_chat_id(self, chat_id: str) -> dict[str, Any] | None:
        """
        返回当前 chat 下最近一个已完成任务的最近成功交付记录。
        供“把最近完成的任务重新上传”使用。
        """
        tasks = self.task_repository.list_by_chat_id(chat_id)
        if not tasks:
            return None

        for task in tasks:
            task_id = task.get("task_id")
            if not task_id:
                continue
            if task.get("status") != "completed":
                continue

            record = self.delivery_record_repository.get_latest_success_by_task_id(task_id)
            if record:
                return record

        return None