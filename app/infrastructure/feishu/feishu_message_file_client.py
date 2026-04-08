from __future__ import annotations

from pathlib import Path
import requests

from app.infrastructure.feishu.feishu_auth_client import FeishuAuthClient
from app.shared.utils.retry import retry


class FeishuMessageFileClient:
    BASE_URL = "https://open.feishu.cn/open-apis"

    def __init__(self, auth_client: FeishuAuthClient):
        self.auth_client = auth_client

    def _headers(self) -> dict[str, str]:
        token = self.auth_client.get_tenant_access_token()
        return {
            "Authorization": f"Bearer {token}",
        }

    def download_message_file(
        self,
        message_id: str,
        file_key: str,
        save_path: str,
    ) -> str:
        if not message_id:
            raise ValueError("缺少 message_id")
        if not file_key:
            raise ValueError("缺少 file_key")

        save_path_obj = Path(save_path)
        save_path_obj.parent.mkdir(parents=True, exist_ok=True)

        url = f"{self.BASE_URL}/im/v1/messages/{message_id}/resources/{file_key}"
        headers = self._headers()

        def _download():
            resp = requests.get(
                url,
                headers=headers,
                params={"type": "file"},   # 关键修复
                timeout=120,
                stream=True,
            )

            if resp.status_code != 200:
                try:
                    print("FEISHU DOWNLOAD ERROR:", resp.status_code, resp.text)
                except Exception:
                    print("FEISHU DOWNLOAD ERROR:", resp.status_code)

            resp.raise_for_status()

            with open(save_path_obj, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)

            return str(save_path_obj)

        return retry(_download, retries=3, delay=1.0, backoff=2.0)