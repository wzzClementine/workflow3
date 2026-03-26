from pathlib import Path
from typing import BinaryIO

from app.config import settings
from app.utils.file_utils import ensure_dir
from app.utils.logger import setup_logger

import shutil

logger = setup_logger(settings.log_level, settings.logs_dir)


class StorageService:
    VALID_CATEGORIES = {
        "raw",
        "pages",
        "blank_pages",
        "solution_pages",
        "blank_questions",
        "solution_questions",
        "json",
        "logs",
    }

    def get_task_root(self, task_id: str) -> Path:
        if not task_id:
            raise ValueError("task_id 不能为空")
        return settings.papers_dir / task_id

    def init_task_dirs(self, task_id: str) -> dict[str, Path]:
        task_root = ensure_dir(self.get_task_root(task_id))

        dirs = {
            "task_root": task_root,
            "raw": ensure_dir(task_root / "raw"),
            "pages": ensure_dir(task_root / "pages"),
            "blank_pages": ensure_dir(task_root / "blank_pages"),
            "solution_pages": ensure_dir(task_root / "solution_pages"),
            "blank_questions": ensure_dir(task_root / "blank_questions"),
            "solution_questions": ensure_dir(task_root / "solution_questions"),
            "json": ensure_dir(task_root / "json"),
            "logs": ensure_dir(task_root / "logs"),
        }

        logger.info("Task directories initialized: task_id=%s, dirs=%s", task_id, dirs)
        return dirs

    def get_category_dir(self, task_id: str, category: str) -> Path:
        if category not in self.VALID_CATEGORIES:
            raise ValueError(f"不支持的 category: {category}")

        dirs = self.init_task_dirs(task_id)
        return dirs[category]

    def save_bytes(
        self,
        task_id: str,
        category: str,
        filename: str,
        content: bytes,
    ) -> Path:
        if not filename:
            raise ValueError("filename 不能为空")

        target_dir = self.get_category_dir(task_id, category)
        file_path = target_dir / filename
        file_path.write_bytes(content)

        logger.info(
            "File saved by bytes: task_id=%s, category=%s, path=%s",
            task_id,
            category,
            file_path,
        )
        return file_path

    def save_text(
        self,
        task_id: str,
        category: str,
        filename: str,
        content: str,
        encoding: str = "utf-8",
    ) -> Path:
        if not filename:
            raise ValueError("filename 不能为空")

        target_dir = self.get_category_dir(task_id, category)
        file_path = target_dir / filename
        file_path.write_text(content, encoding=encoding)

        logger.info(
            "File saved by text: task_id=%s, category=%s, path=%s",
            task_id,
            category,
            file_path,
        )
        return file_path

    def exists(self, task_id: str, category: str, filename: str) -> bool:
        target_dir = self.get_category_dir(task_id, category)
        return (target_dir / filename).exists()

    def get_file_path(self, task_id: str, category: str, filename: str) -> Path:
        target_dir = self.get_category_dir(task_id, category)
        return target_dir / filename

    def save_local_file(
        self,
        task_id: str,
        category: str,
        source_file_path: str,
        target_filename: str | None = None,
    ) -> Path:
        source_path = Path(source_file_path)

        if not source_path.exists():
            raise FileNotFoundError(f"源文件不存在: {source_file_path}")

        if not source_path.is_file():
            raise ValueError(f"源路径不是文件: {source_file_path}")

        filename = target_filename or source_path.name
        target_dir = self.get_category_dir(task_id, category)
        target_path = target_dir / filename

        shutil.copy2(source_path, target_path)

        logger.info(
            "Local file copied: task_id=%s, category=%s, source=%s, target=%s",
            task_id,
            category,
            source_path,
            target_path,
        )
        return target_path


storage_service = StorageService()