from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from app.infrastructure.feishu import FeishuDriveClient
from app.repositories.delivery_repo import DeliveryRecordRepository


class DeliveryService:
    def __init__(
        self,
        drive_client: FeishuDriveClient,
        delivery_record_repository: DeliveryRecordRepository,
    ):
        self.drive_client = drive_client
        self.delivery_record_repository = delivery_record_repository

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