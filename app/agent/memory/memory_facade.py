from __future__ import annotations

from typing import Any

from app.services.task import TaskService
from app.services.session import ChatSessionService
from app.services.memory import TaskMemoryService


class MemoryFacade:
    def __init__(
        self,
        task_service: TaskService,
        chat_session_service: ChatSessionService,
        task_memory_service: TaskMemoryService,
    ):
        self.task_service = task_service
        self.chat_session_service = chat_session_service
        self.task_memory_service = task_memory_service

    def get_chat_context(
        self,
        chat_id: str,
    ) -> dict[str, Any]:
        session = self.chat_session_service.get_session(chat_id)

        if not session:
            return {
                "session": None,
                "task": None,
                "task_memory": None,
            }

        current_task_id = session.get("current_task_id")
        task = self.task_service.get_task(current_task_id) if current_task_id else None
        task_memory = (
            self.task_memory_service.get_memory(current_task_id)
            if current_task_id
            else None
        )

        return {
            "session": session,
            "task": task,
            "task_memory": task_memory,
        }

    def get_task_context(
        self,
        task_id: str,
    ) -> dict[str, Any]:
        task = self.task_service.get_task(task_id)
        task_memory = self.task_memory_service.get_memory(task_id)

        return {
            "task": task,
            "task_memory": task_memory,
        }

    def build_agent_snapshot(
        self,
        chat_id: str,
    ) -> dict[str, Any]:
        context = self.get_chat_context(chat_id)

        session = context["session"]
        task = context["task"]
        task_memory = context["task_memory"]

        return {
            "chat_id": chat_id,
            "has_session": session is not None,
            "has_task": task is not None,
            "session": session,
            "task": task,
            "task_memory": task_memory,
            "current_task_id": session.get("current_task_id") if session else None,
            "current_stage": task.get("current_stage") if task else None,
            "waiting_for": session.get("waiting_for") if session else None,
            "next_action_hint": task_memory.get("next_action_hint") if task_memory else None,
        }