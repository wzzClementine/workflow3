from __future__ import annotations

from pathlib import Path

from app.infrastructure.feishu.feishu_message_file_client import FeishuMessageFileClient
from app.config import settings


class FileFetchService:
    def __init__(self, feishu_message_file_client: FeishuMessageFileClient):
        self.feishu_message_file_client = feishu_message_file_client

    def download_uploaded_file_to_task_dir(
        self,
        task_id: str,
        file_name: str,
        file_key: str,
        message_id: str,
    ) -> str:
        task_upload_dir = settings.tasks_dir / task_id / "uploads"
        task_upload_dir.mkdir(parents=True, exist_ok=True)

        save_path = task_upload_dir / file_name

        return self.feishu_message_file_client.download_message_file(
            message_id=message_id,
            file_key=file_key,
            save_path=str(save_path),
        )