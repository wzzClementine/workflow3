import json
from app.services.task_memory_service import task_memory_service
from app.services.artifact_service import artifact_service


REQUIRED_MATERIALS = [
    "excel",
    "solution_pdf",
    "blank_pdf"
]


def check_missing_materials(task_id: str):
    artifacts = artifact_service.list_by_task_id(task_id)

    existing_types = set(a["artifact_type"] for a in artifacts)

    # 自动推导缺失材料
    missing = [m for m in REQUIRED_MATERIALS if m not in existing_types]

    # ⭐关键：同步更新 memory（这一步是质变）
    task_memory_service.update_missing_materials(
        task_id=task_id,
        missing_materials_json=json.dumps(missing, ensure_ascii=False),
    )

    return {
        "task_id": task_id,
        "existing": list(existing_types),
        "missing": missing,
        "has_missing": len(missing) > 0,
    }