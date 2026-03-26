from typing import Any

from app.services.task_service import task_service
from app.utils.logger import setup_logger
from app.config import settings

logger = setup_logger(settings.log_level, settings.logs_dir)


def task_create(created_by: str | None = None) -> dict[str, Any]:
    """
    创建 workflow3 任务的统一 skill。
    """
    try:
        task = task_service.create_task(
            task_type="workflow3",
            created_by=created_by,
        )
        logger.info("task_create success: %s", task["task_id"])
        return task
    except Exception as e:
        logger.exception("task_create failed: %s", e)
        raise