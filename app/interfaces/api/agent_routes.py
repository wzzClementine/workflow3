from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.agent.schema import AgentEvent, UploadedFile


router = APIRouter(prefix="/agent", tags=["agent"])


class UploadedFileDTO(BaseModel):
    file_name: str
    file_key: str | None = None
    mime_type: str | None = None
    message_id: str | None = None


class AgentEventRequest(BaseModel):
    chat_id: str
    event_type: Literal["text", "file_upload", "system"]
    user_message: str | None = None
    files: list[UploadedFileDTO] = Field(default_factory=list)


@router.post("/event")
def handle_agent_event(
    payload: AgentEventRequest,
    request: Request,
) -> dict:
    orchestrator = request.app.state.orchestrator

    event = AgentEvent(
        chat_id=payload.chat_id,
        event_type=payload.event_type,
        user_message=payload.user_message,
        files=[
            UploadedFile(
                file_name=item.file_name,
                file_key=item.file_key,
                mime_type=item.mime_type,
                message_id=item.message_id,
            )
            for item in payload.files
        ],
    )

    result = orchestrator.handle_event(event)

    return {
        "status": result.status,
        "message": result.message,
        "task_id": result.task_id,
        "snapshot": result.snapshot,
    }