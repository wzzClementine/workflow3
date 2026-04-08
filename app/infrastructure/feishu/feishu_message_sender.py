from __future__ import annotations

import json
import requests

from app.infrastructure.feishu.feishu_auth_client import FeishuAuthClient
from app.shared.utils.retry import retry


class FeishuMessageSender:
    BASE_URL = "https://open.feishu.cn/open-apis"

    def __init__(self, auth_client: FeishuAuthClient):
        self.auth_client = auth_client

    def send_text(self, chat_id: str, text: str) -> None:
        def _send():
            token = self.auth_client.get_tenant_access_token()

            url = f"{self.BASE_URL}/im/v1/messages"
            payload = {
                "receive_id": chat_id,
                "msg_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            }
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }

            resp = requests.post(
                url,
                headers=headers,
                params={"receive_id_type": "chat_id"},
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()

            data = resp.json()
            if data.get("code") != 0:
                raise RuntimeError(f"飞书发送消息失败: {data}")

        retry(_send, retries=3, delay=1.0, backoff=2.0)