from typing import Any

from app.services.task_service import task_service
from app.utils.logger import setup_logger
from app.config import settings

logger = setup_logger(settings.log_level, settings.logs_dir)


def task_update_status(
    task_id: str,
    status: str,
    error_message: str | None = None,
    output_path: str | None = None,
) -> dict[str, Any]:
    """
    更新任务状态的统一 skill。
    """
    if not task_id:
        raise ValueError("task_id 不能为空")
    if not status:
        raise ValueError("status 不能为空")

    try:
        task = task_service.update_task_status(
            task_id=task_id,
            status=status,
            error_message=error_message,
            output_path=output_path,
        )
        logger.info("task_update_status success: %s -> %s", task_id, status)
        return task
    except Exception as e:
        logger.exception("task_update_status failed: task_id=%s, status=%s, error=%s", task_id, status, e)
        raise