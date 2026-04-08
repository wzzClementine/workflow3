from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from app.repositories.file_repo import TaskFileRepository


class TaskFileService:
    def __init__(self, task_file_repository: TaskFileRepository):
        self.task_file_repository = task_file_repository

    def create_file_record(
        self,
        task_id: str,
        file_role: str,
        file_name: str,
        storage_type: str = "feishu",
        local_path: str | None = None,
        remote_key: str | None = None,
        remote_url: str | None = None,
        page_count: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        file_id = f"file_{uuid.uuid4().hex[:12]}"
        file_ext = Path(file_name).suffix.lower() if file_name else None

        return self.task_file_repository.create_file(
            file_id=file_id,
            task_id=task_id,
            file_role=file_role,
            file_name=file_name,
            file_ext=file_ext,
            storage_type=storage_type,
            local_path=local_path,
            remote_key=remote_key,
            remote_url=remote_url,
            page_count=page_count,
            metadata_json=json.dumps(metadata, ensure_ascii=False) if metadata else None,
        )

    def list_task_files(
        self,
        task_id: str,
    ) -> list[dict[str, Any]]:
        return self.task_file_repository.list_by_task_id(task_id)

    def list_task_files_by_role(
        self,
        task_id: str,
        file_role: str,
    ) -> list[dict[str, Any]]:
        return self.task_file_repository.list_by_task_id_and_role(task_id, file_role)

    def get_materials_summary(
        self,
        task_id: str,
    ) -> dict[str, Any]:
        blank_files = self.task_file_repository.list_by_task_id_and_role(task_id, "blank_pdf")
        solution_files = self.task_file_repository.list_by_task_id_and_role(task_id, "solution_pdf")

        return {
            "has_blank_pdf": len(blank_files) > 0,
            "has_solution_pdf": len(solution_files) > 0,
            "blank_pdf_count": len(blank_files),
            "solution_pdf_count": len(solution_files),
            "is_ready": len(blank_files) > 0 and len(solution_files) > 0,
            "blank_files": blank_files,
            "solution_files": solution_files,
        }