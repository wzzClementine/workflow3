from __future__ import annotations

import base64
import json
from pathlib import Path

import requests

from app.config import settings
from app.shared.utils.retry import retry


class QwenVisionClient:
    def __init__(self):
        self.api_key = settings.qwen_api_key
        self.base_url = settings.qwen_base_url
        self.model = settings.qwen_vision_model

    def _encode_image(self, path: str) -> str:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()

    def _infer_mime_type(self, path: str) -> str:
        ext = Path(path).suffix.lower()
        if ext in {".jpg", ".jpeg"}:
            return "jpeg"
        if ext == ".webp":
            return "webp"
        if ext == ".bmp":
            return "bmp"
        return "png"

    def _build_image_data_url(self, path: str) -> str:
        mime = self._infer_mime_type(path)
        return f"data:image/{mime};base64,{self._encode_image(path)}"

    def analyze_item(self, item: dict) -> dict:
        question_image_path = item.get("question_image_path")
        analysis_image_path = (
            item.get("cleaned_analysis_image_path")
            or item.get("analysis_image_path")
        )

        if not question_image_path:
            return {
                "answer": "uncertain",
                "knowledge_points": [],
                "is_subquestion": False,
                "subquestion_index": None,
                "belongs_to_previous_parent": False,
                "confidence": 0.0,
                "needs_review": True,
                "llm_reason": "missing_question_image_path",
                "_raw_content": "",
                "_raw_response": None,
            }

        return self.analyze_question_pair(
            question_image_path=question_image_path,
            analysis_image_path=analysis_image_path,
        )

    def analyze_question_pair(
        self,
        question_image_path: str,
        analysis_image_path: str | None = None,
    ) -> dict:
        prompt = self._build_prompt()

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": self._build_image_data_url(question_image_path)
                        },
                    },
                ],
            }
        ]

        if analysis_image_path:
            messages[0]["content"].append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": self._build_image_data_url(analysis_image_path)
                    },
                }
            )

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1,
        }

        def _call():
            resp = requests.post(
                self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=(10, 60),
            )
            resp.raise_for_status()

            result = resp.json()
            content = result["choices"][0]["message"]["content"]

            parsed = self._safe_parse(content)
            parsed["_raw_content"] = content
            parsed["_raw_response"] = result
            return parsed

        return retry(_call)

    def _build_prompt(self) -> str:
        return """
你是一个小学/初中数学试卷结构化解析助手。

你的任务是：根据“题目图片”和“解析图片”，提取该题的答案和知识点信息。

注意：
1. 题型和分值由外部系统确定，你不要判断题型，也不要判断分值
2. 你只需要关注答案、知识点、子题关系和置信度
3. 可结合解析图片提取最终答案
4. 如果解析图片信息不足，可以根据题目图片辅助判断
5. 如果无法确认答案，请返回 "uncertain"，不要猜测
6. 如果无法可靠判断知识点，请返回空数组，不要编造
7. 请严格输出一个 JSON 对象，不要输出任何其他文字，不要使用 markdown，不要使用 ```json 包裹

返回格式：
{
  "answer": "最终答案",
  "knowledge_points": [],
  "is_subquestion": false,
  "subquestion_index": null,
  "belongs_to_previous_parent": false,
  "confidence": 0.0,
  "needs_review": true,
  "llm_reason": "简要说明答案提取依据"
}
""".strip()

    def _safe_parse(self, text) -> dict:
        try:
            if not isinstance(text, str):
                text = str(text)

            raw = text.strip()

            if raw.startswith("```"):
                lines = raw.splitlines()
                if lines and lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                raw = "\n".join(lines).strip()

                if raw.lower().startswith("json"):
                    raw = raw[4:].strip()

            start = raw.find("{")
            end = raw.rfind("}")
            if start != -1 and end != -1 and end > start:
                raw = raw[start:end + 1]

            data = json.loads(raw)

            knowledge_points = data.get("knowledge_points", [])
            if isinstance(knowledge_points, str):
                knowledge_points = [knowledge_points] if knowledge_points.strip() else []
            elif not isinstance(knowledge_points, list):
                knowledge_points = []

            confidence = data.get("confidence", 0.0)
            try:
                confidence = float(confidence)
            except Exception:
                confidence = 0.0

            needs_review = data.get("needs_review", True)
            if isinstance(needs_review, str):
                needs_review = needs_review.strip().lower() not in {"false", "0", "no"}
            else:
                needs_review = bool(needs_review)

            is_subquestion = data.get("is_subquestion", False)
            if isinstance(is_subquestion, str):
                is_subquestion = is_subquestion.strip().lower() in {"true", "1", "yes"}
            else:
                is_subquestion = bool(is_subquestion)

            belongs_to_previous_parent = data.get("belongs_to_previous_parent", False)
            if isinstance(belongs_to_previous_parent, str):
                belongs_to_previous_parent = (
                    belongs_to_previous_parent.strip().lower() in {"true", "1", "yes"}
                )
            else:
                belongs_to_previous_parent = bool(belongs_to_previous_parent)

            subquestion_index = data.get("subquestion_index", None)
            if subquestion_index in ("", "null", "None"):
                subquestion_index = None

            answer = data.get("answer", "uncertain")
            if not isinstance(answer, str):
                answer = str(answer)

            llm_reason = data.get("llm_reason", "missing_fields")
            if not isinstance(llm_reason, str):
                llm_reason = str(llm_reason)

            return {
                "answer": answer or "uncertain",
                "knowledge_points": knowledge_points,
                "is_subquestion": is_subquestion,
                "subquestion_index": subquestion_index,
                "belongs_to_previous_parent": belongs_to_previous_parent,
                "confidence": confidence,
                "needs_review": needs_review,
                "llm_reason": llm_reason,
            }

        except Exception as e:
            print(f"[QwenVisionClient] JSON 解析失败: {e}")
            return {
                "answer": "uncertain",
                "knowledge_points": [],
                "is_subquestion": False,
                "subquestion_index": None,
                "belongs_to_previous_parent": False,
                "confidence": 0.0,
                "needs_review": True,
                "llm_reason": "parse_failed",
            }