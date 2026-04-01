from app.services.task_memory_service import task_memory_service
from app.services.artifact_service import artifact_service
from app.agent.tools.impl.check_missing_materials import check_missing_materials


def get_task_state(task_id: str):
    memory = task_memory_service.get_by_task_id(task_id)
    artifacts = artifact_service.list_by_task_id(task_id)

    missing_result = check_missing_materials(task_id)

    return {
        "task_id": task_id,
        "memory": task_memory_service.get_by_task_id(task_id),  # 重新取一次，拿更新后的
        "artifact_count": len(artifacts),
        "artifact_types": [a["artifact_type"] for a in artifacts],
        "missing_materials": missing_result.get("missing", []),
        "has_missing": missing_result.get("has_missing", False),
    }