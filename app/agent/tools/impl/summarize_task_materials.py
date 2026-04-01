from pathlib import Path
from typing import Any

import fitz  # PyMuPDF

from app.services.artifact_service import artifact_service


def _get_pdf_page_count(file_path: str | None) -> int | None:
    if not file_path:
        return None

    path_obj = Path(file_path)
    if not path_obj.exists():
        return None

    try:
        doc = fitz.open(file_path)
        page_count = len(doc)
        doc.close()
        return page_count
    except Exception:
        return None


def summarize_task_materials(task_id: str) -> dict[str, Any]:
    artifacts = artifact_service.list_by_task_id(task_id)

    summary: dict[str, Any] = {
        "task_id": task_id,
        "excel": None,
        "blank_pdf": None,
        "solution_pdf": None,
        "all_artifacts": [],
        "materials_ready": False,
        "missing_materials": [],
        "confirmation_items": [],
    }

    for item in artifacts:
        artifact_type = item.get("artifact_type")
        artifact_name = item.get("artifact_name")
        local_path = item.get("local_path")

        entry = {
            "artifact_id": item.get("artifact_id"),
            "artifact_type": artifact_type,
            "artifact_name": artifact_name,
            "local_path": local_path,
            "status": item.get("status"),
        }

        if artifact_type in ("blank_pdf", "solution_pdf"):
            entry["page_count"] = _get_pdf_page_count(local_path)

        summary["all_artifacts"].append(entry)

        # 当前默认取同类型中“最后一条”（通常也是最新一条）
        if artifact_type == "excel":
            summary["excel"] = entry
        elif artifact_type == "blank_pdf":
            summary["blank_pdf"] = entry
        elif artifact_type == "solution_pdf":
            summary["solution_pdf"] = entry

    if summary["excel"] and summary["blank_pdf"] and summary["solution_pdf"]:
        summary["materials_ready"] = True

    if not summary["excel"]:
        summary["missing_materials"].append("excel")
    if not summary["blank_pdf"]:
        summary["missing_materials"].append("blank_pdf")
    if not summary["solution_pdf"]:
        summary["missing_materials"].append("solution_pdf")

    if summary["excel"]:
        summary["confirmation_items"].append(
            {
                "label": "Excel",
                "artifact_type": "excel",
                "artifact_name": summary["excel"]["artifact_name"],
                "page_count": None,
            }
        )

    if summary["blank_pdf"]:
        summary["confirmation_items"].append(
            {
                "label": "空白试卷 PDF",
                "artifact_type": "blank_pdf",
                "artifact_name": summary["blank_pdf"]["artifact_name"],
                "page_count": summary["blank_pdf"].get("page_count"),
            }
        )

    if summary["solution_pdf"]:
        summary["confirmation_items"].append(
            {
                "label": "解析试卷 PDF",
                "artifact_type": "solution_pdf",
                "artifact_name": summary["solution_pdf"]["artifact_name"],
                "page_count": summary["solution_pdf"].get("page_count"),
            }
        )

    return summary