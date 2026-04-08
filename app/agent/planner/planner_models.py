from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PlannerDecision:
    intent: str
    action: str
    reply: str
    should_call_tool: bool = False
    tool_name: str | None = None
    tool_args: dict[str, Any] = field(default_factory=dict)


@dataclass
class PlannerInput:
    system_prompt: str
    user_prompt: str
    snapshot: dict[str, Any]