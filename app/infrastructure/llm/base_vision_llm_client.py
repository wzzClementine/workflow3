from __future__ import annotations

from abc import ABC, abstractmethod


class BaseVisionLLMClient(ABC):
    @abstractmethod
    def analyze_question_pair(
        self,
        question_image_path: str,
        analysis_image_path: str | None = None,
    ) -> dict:
        raise NotImplementedError