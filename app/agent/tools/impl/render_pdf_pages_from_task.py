from pathlib import Path
from typing import Any

from app.services.artifact_service import artifact_service
from app.skills.render_pdf_pages import render_pdf_pages


def render_pdf_pages_from_task(task_id: str, dpi: int = 300) -> dict[str, Any]:
    """
    Agent 友好的渲染工具：
    只需要 task_id，就能自动从 artifacts 中找到 blank_pdf 和 solution_pdf，
    然后调用现有的 render_pdf_pages。
    """

    if not task_id:
        raise ValueError("task_id 不能为空")

    blank_pdf_artifacts = artifact_service.list_by_task_and_type(task_id, "blank_pdf")
    solution_pdf_artifacts = artifact_service.list_by_task_and_type(task_id, "solution_pdf")

    if not blank_pdf_artifacts:
        raise ValueError(f"任务 {task_id} 缺少 blank_pdf，无法渲染")
    if not solution_pdf_artifacts:
        raise ValueError(f"任务 {task_id} 缺少 solution_pdf，无法渲染")

    # 当前先取每种类型的第一份
    blank_pdf = blank_pdf_artifacts[0]
    solution_pdf = solution_pdf_artifacts[0]

    blank_pdf_path = blank_pdf.get("local_path")
    solution_pdf_path = solution_pdf.get("local_path")

    if not blank_pdf_path or not Path(blank_pdf_path).exists():
        raise ValueError(f"blank_pdf 文件不存在: {blank_pdf_path}")
    if not solution_pdf_path or not Path(solution_pdf_path).exists():
        raise ValueError(f"solution_pdf 文件不存在: {solution_pdf_path}")

    blank_paper_name = Path(blank_pdf_path).stem
    solution_paper_name = Path(solution_pdf_path).stem

    result = render_pdf_pages(
        task_id=task_id,
        blank_pdf_path=blank_pdf_path,
        solution_pdf_path=solution_pdf_path,
        blank_paper_name=blank_paper_name,
        solution_paper_name=solution_paper_name,
        dpi=dpi,
    )

    return {
        "task_id": task_id,
        "blank_pdf_path": blank_pdf_path,
        "solution_pdf_path": solution_pdf_path,
        "dpi": dpi,
        "status": "success",
        "render_result": result,
    }