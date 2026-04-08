from __future__ import annotations

import requests
import json

from app.config import settings
from app.shared.utils.retry import retry


class QwenTextClient:

    def __init__(self):
        self.api_key = settings.qwen_api_key
        self.base_url = settings.qwen_base_url
        self.model = settings.qwen_text_model


    def structured_chat(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> dict:

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
        }

        def _call():
            resp = requests.post(
                self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=60,
            )

            resp.raise_for_status()
            result = resp.json()

            content = result["choices"][0]["message"]["content"]

            return self._safe_parse(content)

        return retry(_call)

    def _safe_parse(self, text: str) -> dict:
        try:
            return json.loads(text)
        except:
            return {"action": "reply", "reply": text}