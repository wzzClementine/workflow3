from __future__ import annotations

import base64
import requests

from app.shared.utils.retry import retry


class VisionLLMClient:

    def __init__(self, api_key: str, base_url: str):
        self.api_key = api_key
        self.base_url = base_url

    def _encode_image(self, path: str) -> str:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()

    def analyze_question_pair(
            self,
            question_image_path: str,
            analysis_image_path: str | None = None,
    ) -> dict:

        prompt = self._build_prompt()

        images = [
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{self._encode_image(question_image_path)}"
                }
            }
        ]

        if analysis_image_path:
            images.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{self._encode_image(analysis_image_path)}"
                }
            })

        payload = {
            "model": "gpt-4o",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        *images
                    ]
                }
            ],
            "temperature": 0.2,
        }

        def _call():
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
                timeout=60,
            )
            resp.raise_for_status()
            result = resp.json()
            content = result["choices"][0]["message"]["content"]
            return self._safe_parse(content)

        return retry(_call, retries=3, delay=1.0, backoff=2.0)

    def _build_prompt(self) -> str:
        return """
你是一个试题解析专家。

请从图片中提取信息，并严格返回JSON：

{
  "question_type": "fill_blank | calculation | application | geometry",
  "answer": "最终答案（不要写过程）",
  "score": 数字,
  "knowledge_points": ["知识点1","知识点2"],
  "is_subquestion": true/false,
  "subquestion_index": 数字或null,
  "belongs_to_previous_parent": true/false,
  "confidence": 0~1,
  "needs_review": true/false,
  "llm_reason": "简短解释"
}

规则：
1. 只输出JSON
2. 如果看不清答案 → answer=uncertain
3. 不要编造
"""

    def _safe_parse(self, text: str) -> dict:
        import json
        try:
            return json.loads(text)
        except:
            return {
                "question_type": "unknown",
                "answer": "uncertain",
                "confidence": 0.0,
                "needs_review": True,
                "llm_reason": "parse_failed"
            }