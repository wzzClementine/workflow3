from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SegmentationOutput:
    success: bool
    message: str
    output_dir: str | None = None
    files: list[str] = field(default_factory=list)
    debug_files: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)