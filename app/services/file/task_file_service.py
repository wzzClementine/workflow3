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

    def get_latest_materials_summary(
        self,
        task_id: str,
    ) -> dict[str, Any]:
        latest_blank = self.task_file_repository.get_latest_by_task_id_and_role(task_id, "blank_pdf")
        latest_solution = self.task_file_repository.get_latest_by_task_id_and_role(task_id, "solution_pdf")

        return {
            "has_blank_pdf": latest_blank is not None,
            "has_solution_pdf": latest_solution is not None,
            "is_ready": latest_blank is not None and latest_solution is not None,
            "blank_pdf_name": latest_blank.get("file_name") if latest_blank else None,
            "solution_pdf_name": latest_solution.get("file_name") if latest_solution else None,
            "blank_pdf_pages": latest_blank.get("page_count") if latest_blank else None,
            "solution_pdf_pages": latest_solution.get("page_count") if latest_solution else None,
            "blank_pdf_record": latest_blank,
            "solution_pdf_record": latest_solution,
        }

    def build_user_friendly_materials_text(
        self,
        task_id: str,
    ) -> str:
        summary = self.get_latest_materials_summary(task_id)

        has_blank = summary["has_blank_pdf"]
        has_solution = summary["has_solution_pdf"]

        blank_name = summary["blank_pdf_name"]
        solution_name = summary["solution_pdf_name"]
        blank_pages = summary["blank_pdf_pages"]
        solution_pages = summary["solution_pdf_pages"]

        def _fmt(name: str | None, pages: int | None) -> str:
            if not name:
                return "未知文件"
            if isinstance(pages, int) and pages > 0:
                return f"{name}（{pages}页）"
            return name

        if has_blank and has_solution:
            return (
                f"已收到试卷材料：{_fmt(blank_name, blank_pages)}；"
                f"已收到解析材料：{_fmt(solution_name, solution_pages)}。"
            )

        if has_blank and not has_solution:
            return f"已收到试卷材料：{_fmt(blank_name, blank_pages)}，还缺答案解析 PDF。"

        if not has_blank and has_solution:
            return f"已收到解析材料：{_fmt(solution_name, solution_pages)}，还缺空白试卷 PDF。"

        return "当前还没有识别到有效的空白试卷 PDF 和答案解析 PDF，请继续上传。"

    def get_latest_material_records(
        self,
        task_id: str,
    ) -> dict[str, dict[str, Any] | None]:
        return {
            "blank_pdf": self.task_file_repository.get_latest_by_task_id_and_role(task_id, "blank_pdf"),
            "solution_pdf": self.task_file_repository.get_latest_by_task_id_and_role(task_id, "solution_pdf"),
        }

    def clone_latest_materials_to_task(
        self,
        source_task_id: str,
        target_task_id: str,
    ) -> dict[str, Any]:
        latest = self.get_latest_material_records(source_task_id)
        blank_record = latest.get("blank_pdf")
        solution_record = latest.get("solution_pdf")

        created_records: list[dict[str, Any]] = []

        for record in [blank_record, solution_record]:
            if not record:
                continue

            metadata = None
            raw_metadata = record.get("metadata_json")
            if raw_metadata:
                try:
                    metadata = json.loads(raw_metadata)
                except Exception:
                    metadata = {"raw_metadata_json": raw_metadata}

            created = self.create_file_record(
                task_id=target_task_id,
                file_role=record.get("file_role"),
                file_name=record.get("file_name"),
                storage_type=record.get("storage_type") or "feishu",
                local_path=record.get("local_path"),
                remote_key=record.get("remote_key"),
                remote_url=record.get("remote_url"),
                page_count=record.get("page_count"),
                metadata=metadata,
            )
            if created:
                created_records.append(created)

        materials_summary = self.get_materials_summary(target_task_id)
        latest_materials_summary = self.get_latest_materials_summary(target_task_id)

        return {
            "created_records": created_records,
            "materials_summary": materials_summary,
            "latest_materials_summary": latest_materials_summary,
        }