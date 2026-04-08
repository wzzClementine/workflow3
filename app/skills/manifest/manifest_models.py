from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ManifestItem:
    global_order: int
    question_image_path: str
    analysis_image_path: str | None = None
    cleaned_analysis_image_path: str | None = None

    # LLM 输出
    question_type: str = "unknown"
    answer: str = "uncertain"
    score: int | None = None
    knowledge_points: list[str] = field(default_factory=list)

    # ⭐ 新增：结构信息
    is_subquestion: bool = False
    subquestion_index: int | None = None
    belongs_to_previous_parent: bool = False

    # ⭐ 程序生成
    parent_group_id: int = 0
    parent_display_no: str = ""
    display_no: str = ""

    confidence: float = 0.0
    needs_review: bool = False
    llm_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ManifestBuildResult:
    success: bool
    message: str
    manifest_path: str | None = None
    total_count: int = 0
    items: list[ManifestItem] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "manifest_path": self.manifest_path,
            "total_count": self.total_count,
            "items": [item.to_dict() for item in self.items],
        }