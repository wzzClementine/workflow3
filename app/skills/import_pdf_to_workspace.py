from pathlib import Path
from typing import Any

from app.services.storage_service import storage_service
from app.services.task_service import task_service
from app.services.paper_service import paper_service
from app.skills.task_update_status import task_update_status
from app.utils.logger import setup_logger
from app.config import settings

logger = setup_logger(settings.log_level, settings.logs_dir)


def import_pdf_to_workspace(
    task_id: str,
    pdf_local_path: str,
    paper_name: str,
    source_type: str = "blank",
) -> dict[str, Any]:
    """
    将本地 PDF 导入到 task 工作目录，并在 papers 表中创建记录。
    """
    if not task_id:
        raise ValueError("task_id 不能为空")
    if not pdf_local_path:
        raise ValueError("pdf_local_path 不能为空")
    if not paper_name:
        raise ValueError("paper_name 不能为空")
    if source_type not in {"blank", "solution"}:
        raise ValueError("source_type 必须是 blank 或 solution")

    task = task_service.get_task_by_id(task_id)
    if not task:
        raise ValueError(f"任务不存在: {task_id}")

    try:
        task_update_status(task_id=task_id, status="running")

        source_path = Path(pdf_local_path)
        if not source_path.exists():
            raise FileNotFoundError(f"PDF 文件不存在: {pdf_local_path}")

        if source_path.suffix.lower() != ".pdf":
            raise ValueError("仅支持 PDF 文件")

        target_filename = source_path.name
        saved_path = storage_service.save_local_file(
            task_id=task_id,
            category="raw",
            source_file_path=pdf_local_path,
            target_filename=target_filename,
        )

        paper = paper_service.create_paper(
            paper_name=paper_name,
            source_type=source_type,
            raw_pdf_path=str(saved_path),
        )

        task_service.attach_paper_to_task(task_id=task_id, paper_id=paper["paper_id"])

        task_update_status(
            task_id=task_id,
            status="success",
            output_path=str(saved_path),
        )

        result = {
            "task_id": task_id,
            "paper_id": paper["paper_id"],
            "paper_name": paper["paper_name"],
            "source_type": paper["source_type"],
            "raw_pdf_path": str(saved_path),
            "status": "success",
        }

        logger.info("import_pdf_to_workspace success: %s", result)
        return result

    except Exception as e:
        logger.exception("import_pdf_to_workspace failed: task_id=%s, error=%s", task_id, e)
        task_update_status(
            task_id=task_id,
            status="failed",
            error_message=str(e),
        )
        raise