from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCall:
    tool_name: str
    tool_args: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    tool_name: str
    success: bool
    message: str
    data: dict[str, Any] = field(default_factory=dict)