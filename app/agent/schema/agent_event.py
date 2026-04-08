from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class UploadedFile:
    file_name: str
    file_key: Optional[str] = None
    mime_type: Optional[str] = None
    message_id: Optional[str] = None


@dataclass
class AgentEvent:
    chat_id: str
    event_type: str  # text / file_upload / system
    user_message: Optional[str] = None
    files: List[UploadedFile] = field(default_factory=list)