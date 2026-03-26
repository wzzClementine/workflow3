import json
from typing import Any

import requests

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(settings.log_level, settings.logs_dir)


class FeishuService:
    def __init__(self) -> None:
        self.app_id = settings.feishu_app_id
        self.app_secret = settings.feishu_app_secret
        self.base_url = "https://open.feishu.cn/open-apis"

    def get_tenant_access_token(self) -> str:
        url = f"{self.base_url}/auth/v3/tenant_access_token/internal"
        payload = {
            "app_id": self.app_id,
            "app_secret": self.app_secret,
        }

        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != 0:
            raise RuntimeError(f"获取 tenant_access_token 失败: {data}")

        token = data.get("tenant_access_token")
        if not token:
            raise RuntimeError("tenant_access_token 为空")

        return token

    def send_text_message(
        self,
        receive_id: str,
        text: str,
        receive_id_type: str = "chat_id",
    ) -> dict[str, Any]:
        token = self.get_tenant_access_token()

        url = f"{self.base_url}/im/v1/messages"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        params = {
            "receive_id_type": receive_id_type,
        }
        payload = {
            "receive_id": receive_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        }

        resp = requests.post(
            url,
            headers=headers,
            params=params,
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != 0:
            raise RuntimeError(f"发送飞书消息失败: {data}")

        logger.info(
            "Feishu text message sent successfully. receive_id_type=%s, receive_id=%s",
            receive_id_type,
            receive_id,
        )
        return data


feishu_service = FeishuService()