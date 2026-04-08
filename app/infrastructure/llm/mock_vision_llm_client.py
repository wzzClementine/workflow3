from __future__ import annotations

from app.infrastructure.llm.base_vision_llm_client import BaseVisionLLMClient


class MockVisionLLMClient(BaseVisionLLMClient):
    def analyze_question_pair(
            self,
            question_image_path: str,
            analysis_image_path: str | None = None,
    ) -> dict:
        name = question_image_path.lower()

        # 模拟：后面的图是子题
        if "question_2" in name:
            return {
                "question_type": "application",
                "answer": "uncertain",
                "score": 6,
                "knowledge_points": ["应用题模块"],
                "is_subquestion": True,
                "subquestion_index": 2,
                "belongs_to_previous_parent": True,
                "confidence": 0.7,
                "needs_review": True,
                "llm_reason": "mock: 子题"
            }

        return {
            "question_type": "application",
            "answer": "uncertain",
            "score": 6,
            "knowledge_points": ["应用题模块"],
            "is_subquestion": False,
            "subquestion_index": 1,
            "belongs_to_previous_parent": False,
            "confidence": 0.7,
            "needs_review": True,
            "llm_reason": "mock: 主题"
        }