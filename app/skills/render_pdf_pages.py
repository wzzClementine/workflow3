import uuid
from pathlib import Path
from typing import Any

from app.services.artifact_service import artifact_service
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
    dpi: int = 300,
) -> dict[str, Any]:
    """
    将空白试卷 PDF 和解析试卷 PDF 分别渲染为页图，
    并把生成的页图登记到 artifacts 表中。
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

    blank_pdf_path_obj = Path(blank_pdf_path).resolve()
    solution_pdf_path_obj = Path(solution_pdf_path).resolve()

    if not blank_pdf_path_obj.exists():
        raise ValueError(f"blank_pdf_path 不存在: {blank_pdf_path_obj}")
    if not solution_pdf_path_obj.exists():
        raise ValueError(f"solution_pdf_path 不存在: {solution_pdf_path_obj}")

    try:
        task_update_status(task_id=task_id, status="running")

        # 1. 初始化任务目录
        dirs = storage_service.init_task_dirs(task_id)

        # 2. 渲染 PDF 到任务目录
        blank_images = pdf_render_service.render_pdf_to_images(
            pdf_path=str(blank_pdf_path_obj),
            output_dir=dirs["blank_pages"],
            dpi=dpi,
            prefix="page",
        )

        solution_images = pdf_render_service.render_pdf_to_images(
            pdf_path=str(solution_pdf_path_obj),
            output_dir=dirs["solution_pages"],
            dpi=dpi,
            prefix="page",
        )

        # 3. 建立 / 更新 paper 记录
        blank_paper = paper_service.create_paper(
            paper_name=blank_paper_name,
            source_type="blank",
            raw_pdf_path=str(blank_pdf_path_obj),
        )
        paper_service.update_page_count(
            blank_paper["paper_id"],
            len(blank_images),
        )

        solution_paper = paper_service.create_paper(
            paper_name=solution_paper_name,
            source_type="solution",
            raw_pdf_path=str(solution_pdf_path_obj),
        )
        paper_service.update_page_count(
            solution_paper["paper_id"],
            len(solution_images),
        )

        # 4. 绑定 paper 到 task
        # 你原来只绑定 solution_paper，这里保留原逻辑的同时不破坏现有链路
        task_service.attach_paper_to_task(
            task_id=task_id,
            paper_id=solution_paper["paper_id"],
        )

        # 5. 记录 blank 页图 artifact
        blank_artifact_count = 0
        for img_path in blank_images:
            img_path_obj = Path(img_path).resolve()

            artifact_service.create_artifact(
                artifact_id=f"artifact_{uuid.uuid4().hex[:12]}",
                task_id=task_id,
                paper_id=blank_paper["paper_id"],
                artifact_type="blank_page_image",
                artifact_name=img_path_obj.name,
                local_path=str(img_path_obj),
                status="created",
            )
            blank_artifact_count += 1

        # 6. 记录 solution 页图 artifact
        solution_artifact_count = 0
        for img_path in solution_images:
            img_path_obj = Path(img_path).resolve()

            artifact_service.create_artifact(
                artifact_id=f"artifact_{uuid.uuid4().hex[:12]}",
                task_id=task_id,
                paper_id=solution_paper["paper_id"],
                artifact_type="solution_page_image",
                artifact_name=img_path_obj.name,
                local_path=str(img_path_obj),
                status="created",
            )
            solution_artifact_count += 1

        # 7. 更新任务状态
        task_update_status(
            task_id=task_id,
            status="success",
            output_path=str(Path(dirs["solution_pages"]).resolve()),
        )

        result = {
            "task_id": task_id,
            "blank_paper_id": blank_paper["paper_id"],
            "solution_paper_id": solution_paper["paper_id"],
            "blank_page_count": len(blank_images),
            "solution_page_count": len(solution_images),
            "blank_pages_dir": str(Path(dirs["blank_pages"]).resolve()),
            "solution_pages_dir": str(Path(dirs["solution_pages"]).resolve()),
            "artifacts_created": {
                "blank_page_image": blank_artifact_count,
                "solution_page_image": solution_artifact_count,
            },
            "status": "success",
        }

        logger.info("render_pdf_pages success: %s", result)
        return result

    except Exception as e:
        logger.exception("render_pdf_pages failed: task_id=%s, error=%s", task_id, e)
        task_update_status(
            task_id=task_id,
            status="failed",
            error_message=str(e),
        )
        raise