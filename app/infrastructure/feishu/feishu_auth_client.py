from __future__ import annotations

import requests

from app.config import settings


class FeishuAuthClient:
    BASE_URL = "https://open.feishu.cn/open-apis"

    def get_tenant_access_token(self) -> str:
        if not settings.feishu_app_id:
            raise ValueError("缺少 FEISHU_APP_ID")
        if not settings.feishu_app_secret:
            raise ValueError("缺少 FEISHU_APP_SECRET")

        url = f"{self.BASE_URL}/auth/v3/tenant_access_token/internal"
        payload = {
            "app_id": settings.feishu_app_id,
            "app_secret": settings.feishu_app_secret,
        }

        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()

        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"获取 tenant_access_token 失败: {data}")

        token = data.get("tenant_access_token")
        if not token:
            raise RuntimeError("tenant_access_token 为空")

        return token