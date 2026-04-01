from typing import Any

from app.services.task_stage_service import task_stage_service


class AutoAdvanceService:
    def build_auto_tool_calls(self, task_id: str) -> list[dict[str, Any]]:
        """
        第一版自动推进策略：
        materials_ready -> summarize_task_materials
        先让用户确认，不直接渲染
        """
        stage = task_stage_service.get_task_stage(task_id)

        current_stage = stage.get("current_stage")
        can_auto_advance = stage.get("can_auto_advance", False)

        auto_tool_calls: list[dict[str, Any]] = []

        if current_stage == "materials_ready" and can_auto_advance:
            auto_tool_calls.append(
                {
                    "tool": "summarize_task_materials",
                    "args": {
                        "task_id": task_id,
                    },
                }
            )

        return auto_tool_calls


auto_advance_service = AutoAdvanceService()