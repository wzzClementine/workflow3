from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class AgentResult:
    status: str
    message: str
    task_id: str | None
    snapshot: dict[str, Any]