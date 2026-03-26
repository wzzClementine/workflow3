from pathlib import Path
from typing import Any

from app.services.pdf_render_service import pdf_render_service
from app.services.storage_service import storage_service
from app.services.paper_service import paper_service
from app.services.task_service import task_service
from app.skills.task_update_status import task_update_status
from app.utils.logger import setup_logger
from app.config import settings

logger = setup_logger(settings.log_level, settings.logs_dir)


def render_pdf_pages(
    task_id: str,
    blank_pdf_path: str,
    solution_pdf_path: str,
    blank_paper_name: str,
    solution_paper_name: str,
    dpi: int = 200,
) -> dict[str, Any]:
    """
    将空白试卷 PDF 和解析试卷 PDF 分别渲染为页图。
    """
    if not task_id:
        raise ValueError("task_id 不能为空")
    if not blank_pdf_path:
        raise ValueError("blank_pdf_path 不能为空")
    if not solution_pdf_path:
        raise ValueError("solution_pdf_path 不能为空")

    task = task_service.get_task_by_id(task_id)
    if not task:
        raise ValueError(f"任务不存在: {task_id}")

    try:
        task_update_status(task_id=task_id, status="running")

        dirs = storage_service.init_task_dirs(task_id)

        blank_images = pdf_render_service.render_pdf_to_images(
            pdf_path=blank_pdf_path,
            output_dir=dirs["blank_pages"],
            dpi=dpi,
            prefix="page",
        )

        solution_images = pdf_render_service.render_pdf_to_images(
            pdf_path=solution_pdf_path,
            output_dir=dirs["solution_pages"],
            dpi=dpi,
            prefix="page",
        )

        blank_paper = paper_service.create_paper(
            paper_name=blank_paper_name,
            source_type="blank",
            raw_pdf_path=str(Path(blank_pdf_path).resolve()),
        )
        paper_service.update_page_count(blank_paper["paper_id"], len(blank_images))

        solution_paper = paper_service.create_paper(
            paper_name=solution_paper_name,
            source_type="solution",
            raw_pdf_path=str(Path(solution_pdf_path).resolve()),
        )
        paper_service.update_page_count(solution_paper["paper_id"], len(solution_images))

        # task 先绑定 solution paper，后面你主要处理解析链路
        task_service.attach_paper_to_task(task_id=task_id, paper_id=solution_paper["paper_id"])

        task_update_status(
            task_id=task_id,
            status="success",
            output_path=str(dirs["solution_pages"]),
        )

        result = {
            "task_id": task_id,
            "blank_paper_id": blank_paper["paper_id"],
            "solution_paper_id": solution_paper["paper_id"],
            "blank_page_count": len(blank_images),
            "solution_page_count": len(solution_images),
            "blank_pages_dir": str(dirs["blank_pages"]),
            "solution_pages_dir": str(dirs["solution_pages"]),
            "status": "success",
        }

        logger.info("render_pdf_pages success: %s", result)
        return result

    except Exception as e:
        logger.exception("render_pdf_pages failed: task_id=%s, error=%s", task_id, e)
        task_update_status(task_id=task_id, status="failed", error_message=str(e))
        raise