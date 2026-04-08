from __future__ import annotations

from app.agent.state.task_state import TaskState


class TaskStateMachine:
    _ALLOWED_TRANSITIONS: dict[TaskState, set[TaskState]] = {
        TaskState.CREATED: {
            TaskState.COLLECTING_MATERIALS,
            TaskState.FAILED,
        },
        TaskState.COLLECTING_MATERIALS: {
            TaskState.WAITING_CONFIRMATION,
            TaskState.FAILED,
        },
        TaskState.WAITING_CONFIRMATION: {
            TaskState.PROCESSING,
            TaskState.COLLECTING_MATERIALS,
            TaskState.FAILED,
        },
        TaskState.PROCESSING: {
            TaskState.PACKAGING,
            TaskState.FAILED,
        },
        TaskState.PACKAGING: {
            TaskState.DELIVERING,
            TaskState.FAILED,
        },
        TaskState.DELIVERING: {
            TaskState.COMPLETED,
            TaskState.FAILED,
        },
        TaskState.COMPLETED: set(),
        TaskState.FAILED: set(),
    }

    def can_transition(
        self,
        from_state: TaskState,
        to_state: TaskState,
    ) -> bool:
        return to_state in self._ALLOWED_TRANSITIONS.get(from_state, set())

    def validate_transition(
        self,
        from_state: TaskState,
        to_state: TaskState,
    ) -> None:
        if not self.can_transition(from_state, to_state):
            raise ValueError(
                f"非法状态流转: from={from_state.value}, to={to_state.value}"
            )

    def get_next_allowed_states(
        self,
        current_state: TaskState,
    ) -> list[TaskState]:
        return list(self._ALLOWED_TRANSITIONS.get(current_state, set()))