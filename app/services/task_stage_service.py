from typing import Any

from app.services.artifact_service import artifact_service
from app.services.task_memory_service import task_memory_service


class TaskStageService:
    def get_task_stage(self, task_id: str) -> dict[str, Any]:
        artifacts = artifact_service.list_by_task_id(task_id)
        artifact_types = {item["artifact_type"] for item in artifacts}

        task_memory = task_memory_service.get_by_task_id(task_id)

        existing_artifacts = sorted(list(artifact_types))
        missing_materials: list[str] = []
        current_stage = "empty_task"
        can_auto_advance = False
        next_expected_tools: list[str] = []

        has_excel = "excel" in artifact_types
        has_blank_pdf = "blank_pdf" in artifact_types
        has_solution_pdf = "solution_pdf" in artifact_types
        has_json = "json" in artifact_types

        if not existing_artifacts:
            current_stage = "empty_task"
            missing_materials = ["excel", "blank_pdf", "solution_pdf"]
            can_auto_advance = False

        elif has_excel and not has_blank_pdf and not has_solution_pdf:
            current_stage = "waiting_blank_and_solution_pdf"
            missing_materials = ["blank_pdf", "solution_pdf"]
            can_auto_advance = False

        elif has_excel and has_blank_pdf and not has_solution_pdf:
            current_stage = "waiting_solution_pdf"
            missing_materials = ["solution_pdf"]
            can_auto_advance = False

        elif has_excel and has_solution_pdf and not has_blank_pdf:
            current_stage = "waiting_blank_pdf"
            missing_materials = ["blank_pdf"]
            can_auto_advance = False

        elif not has_excel and has_blank_pdf and has_solution_pdf:
            current_stage = "waiting_excel"
            missing_materials = ["excel"]
            can_auto_advance = False

        elif has_excel and has_blank_pdf and has_solution_pdf and not has_json:
            current_stage = "materials_ready"
            missing_materials = []
            can_auto_advance = True
            next_expected_tools = [
                "render_pdf_pages",
                "generate_questions",
            ]

        elif has_json:
            current_stage = "json_ready"
            missing_materials = []
            can_auto_advance = False

        return {
            "task_id": task_id,
            "current_stage": current_stage,
            "existing_artifacts": existing_artifacts,
            "missing_materials": missing_materials,
            "can_auto_advance": can_auto_advance,
            "next_expected_tools": next_expected_tools,
            "task_memory": task_memory,
        }


task_stage_service = TaskStageService()