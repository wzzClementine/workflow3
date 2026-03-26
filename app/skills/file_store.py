from pathlib import Path
from typing import Literal

from app.services.storage_service import storage_service
from app.utils.logger import setup_logger
from app.config import settings

logger = setup_logger(settings.log_level, settings.logs_dir)

FileCategory = Literal[
    "raw",
    "pages",
    "blank_questions",
    "solution_questions",
    "json",
    "logs",
]


def file_store_init_task_dirs(task_id: str) -> dict[str, Path]:
    """
    为指定 task 初始化完整目录结构。
    """
    try:
        dirs = storage_service.init_task_dirs(task_id)
        logger.info("file_store_init_task_dirs success: task_id=%s", task_id)
        return dirs
    except Exception as e:
        logger.exception("file_store_init_task_dirs failed: task_id=%s, error=%s", task_id, e)
        raise


def file_store_save_text(
    task_id: str,
    category: FileCategory,
    filename: str,
    content: str,
) -> Path:
    """
    保存文本文件。
    """
    try:
        path = storage_service.save_text(task_id, category, filename, content)
        logger.info(
            "file_store_save_text success: task_id=%s, category=%s, filename=%s",
            task_id,
            category,
            filename,
        )
        return path
    except Exception as e:
        logger.exception(
            "file_store_save_text failed: task_id=%s, category=%s, filename=%s, error=%s",
            task_id,
            category,
            filename,
            e,
        )
        raise


def file_store_save_bytes(
    task_id: str,
    category: FileCategory,
    filename: str,
    content: bytes,
) -> Path:
    """
    保存二进制文件。
    """
    try:
        path = storage_service.save_bytes(task_id, category, filename, content)
        logger.info(
            "file_store_save_bytes success: task_id=%s, category=%s, filename=%s",
            task_id,
            category,
            filename,
        )
        return path
    except Exception as e:
        logger.exception(
            "file_store_save_bytes failed: task_id=%s, category=%s, filename=%s, error=%s",
            task_id,
            category,
            filename,
            e,
        )
        raise