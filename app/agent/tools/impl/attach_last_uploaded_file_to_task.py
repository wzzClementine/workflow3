import json
import uuid
from pathlib import Path

from app.config import settings
from app.services.artifact_service import artifact_service
from app.services.chat_session_service import chat_session_service


def _infer_artifact_type(file_name: str) -> str:
    lower_name = file_name.lower()

    if lower_name.endswith(".xlsx") or lower_name.endswith(".xls"):
        return "excel"

    if lower_name.endswith(".pdf"):
        if any(k in lower_name for k in ["solution", "解析", "答案", "详解"]):
            return "solution_pdf"
        return "blank_pdf"

    return "uploaded_file"


def attach_last_uploaded_file_to_task(chat_id: str, task_id: str):
    session = chat_session_service.get_by_chat_id(chat_id)
    if not session:
        raise ValueError(f"未找到 chat session: {chat_id}")

    file_name = session.get("last_uploaded_file_name")
    file_key = session.get("last_uploaded_file_key")

    if not file_name:
        raise ValueError("session 中没有 last_uploaded_file_name，无法关联文件到任务")

    local_path = settings.temp_dir / file_name
    if not local_path.exists():
        raise ValueError(f"最近上传文件不存在: {local_path}")

    artifact_type = _infer_artifact_type(file_name)

    # ===== 避免重复挂载 =====
    existing = artifact_service.get_by_local_path(str(local_path))
    if existing and existing.get("task_id") == task_id:
        return {
            "task_id": task_id,
            "artifact_id": existing.get("artifact_id"),
            "artifact_type": existing.get("artifact_type"),
            "artifact_name": existing.get("artifact_name"),
            "local_path": existing.get("local_path"),
            "status": "already_attached",
        }

    artifact_id = f"artifact_{uuid.uuid4().hex[:12]}"

    artifact = artifact_service.create_artifact(
        artifact_id=artifact_id,
        task_id=task_id,
        artifact_type=artifact_type,
        artifact_name=file_name,
        local_path=str(local_path),
        status="attached",
        metadata_json=json.dumps(
            {
                "source": "chat_session.last_uploaded_file",
                "chat_id": chat_id,
                "file_key": file_key,
            },
            ensure_ascii=False,
        ),
    )

    from app.services.task_memory_service import task_memory_service

    memory = task_memory_service.get_by_task_id(task_id)

    if memory:
        missing_json = memory.get("missing_materials_json") or "[]"
        missing = json.loads(missing_json)

        if artifact_type in missing:
            missing.remove(artifact_type)

        task_memory_service.update_missing_materials(
            task_id=task_id,
            missing_materials=missing,
        )

    return {
        "task_id": task_id,
        "artifact_id": artifact["artifact_id"],
        "artifact_type": artifact["artifact_type"],
        "artifact_name": artifact["artifact_name"],
        "local_path": artifact["local_path"],
        "status": "attached",
    }