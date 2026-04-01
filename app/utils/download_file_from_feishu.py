from pathlib import Path
import requests

from app.services.feishu_service import feishu_service


def download_file_from_feishu(message_id: str, file_key: str, save_path: Path) -> None:
    if not message_id:
        raise ValueError("message_id 不能为空")
    if not file_key:
        raise ValueError("file_key 不能为空")

    token = feishu_service.get_tenant_access_token()

    url = f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/resources/{file_key}"
    headers = {
        "Authorization": f"Bearer {token}",
    }
    params = {
        "type": "file",
    }

    resp = requests.get(
        url,
        headers=headers,
        params=params,
        stream=True,
        timeout=60,
    )

    if resp.status_code != 200:
        raise Exception(
            f"下载文件失败: status={resp.status_code}, body={resp.text}"
        )

    save_path.parent.mkdir(parents=True, exist_ok=True)

    with open(save_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)