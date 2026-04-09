from __future__ import annotations

import mimetypes
import os
import tempfile
import zipfile
from pathlib import Path

import requests

from app.config import settings
from app.infrastructure.feishu.feishu_auth_client import FeishuAuthClient
from app.shared.utils.retry import retry


class FeishuDriveClient:
    BASE_URL = "https://open.feishu.cn/open-apis"

    def __init__(self, auth_client: FeishuAuthClient):
        self.auth_client = auth_client
        self.web_base_url = getattr(settings, "feishu_web_base_url", "https://feishu.cn").rstrip("/")

    def _headers(self) -> dict[str, str]:
        token = self.auth_client.get_tenant_access_token()
        return {
            "Authorization": f"Bearer {token}",
        }

    def _build_folder_url(self, folder_token: str | None) -> str:
        if not folder_token:
            return ""
        return f"{self.web_base_url}/drive/folder/{folder_token}"

    def _build_file_url(self, file_token: str | None) -> str:
        if not file_token:
            return ""
        return f"{self.web_base_url}/file/{file_token}"

    def create_folder(
        self,
        name: str,
        parent_folder_token: str,
    ) -> dict:
        url = f"{self.BASE_URL}/drive/v1/files/create_folder"

        def _create():
            print(f"[FeishuDrive] 开始创建文件夹: name={name}, parent={parent_folder_token}")

            headers = self._headers()
            headers["Content-Type"] = "application/json"

            payload = {
                "name": name,
                "folder_token": parent_folder_token,
            }

            resp = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=(10, 30),
            )
            print(f"[FeishuDrive] create_folder status={resp.status_code}")

            resp.raise_for_status()
            data = resp.json()
            print(f"[FeishuDrive] create_folder body={str(data)[:500]}")

            if data.get("code") != 0:
                raise RuntimeError(f"创建飞书文件夹失败: {data}")

            folder_data = data["data"]
            folder_token = (
                folder_data.get("token")
                or folder_data.get("folder_token")
                or folder_data.get("file_token")
            )
            folder_data["url"] = self._build_folder_url(folder_token)

            print(f"[FeishuDrive] 创建文件夹成功: token={folder_token}")
            return folder_data

        return retry(_create, retries=3, delay=1.0, backoff=2.0)

    def upload_file(
        self,
        file_path: str,
        parent_folder_token: str,
    ) -> dict:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")

        url = f"{self.BASE_URL}/drive/v1/files/upload_all"

        file_name = Path(file_path).name
        file_size = os.path.getsize(file_path)
        mime_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"

        print(f"[FeishuDrive] 开始上传文件: {file_name}")
        print(f"[FeishuDrive] 文件大小: {file_size / 1024 / 1024:.2f} MB")
        print(f"[FeishuDrive] 目标文件夹 token: {parent_folder_token}")

        def _upload():
            headers = self._headers()

            with open(file_path, "rb") as f:
                files = {
                    "file": (file_name, f, mime_type),
                }
                data = {
                    "file_name": file_name,
                    "parent_type": "explorer",
                    "parent_node": parent_folder_token,
                    "size": str(file_size),
                }

                resp = requests.post(
                    url,
                    headers=headers,
                    data=data,
                    files=files,
                    timeout=(10, 180),
                )

            print(f"[FeishuDrive] upload_file status={resp.status_code}")
            resp.raise_for_status()

            result = resp.json()
            print(f"[FeishuDrive] upload_file body={str(result)[:500]}")

            if result.get("code") != 0:
                raise RuntimeError(f"上传飞书文件失败: {result}")

            upload_data = result["data"]
            file_token = upload_data.get("file_token") or upload_data.get("token")
            upload_data["url"] = self._build_file_url(file_token)

            print(f"[FeishuDrive] 文件上传成功: {file_name}, file_token={file_token}")
            return upload_data

        return retry(_upload, retries=3, delay=1.0, backoff=2.0)

    def upload_directory_tree(
        self,
        local_dir: str,
        parent_folder_token: str,
        create_root_folder: bool = True,
    ) -> dict:
        root_path = Path(local_dir)
        if not root_path.is_dir():
            raise NotADirectoryError(f"目录不存在: {local_dir}")

        zip_path = None
        upload_success = False

        try:
            temp_dir = Path(tempfile.gettempdir())
            zip_path = temp_dir / f"{root_path.name}.zip"

            if zip_path.exists():
                zip_path.unlink()

            print(f"[FeishuDrive] 开始压缩目录: {root_path}")
            print(f"[FeishuDrive] 临时 zip 路径: {zip_path}")

            with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for current_dir, _, filenames in os.walk(root_path):
                    current_dir_path = Path(current_dir)
                    for filename in sorted(filenames):
                        file_path = current_dir_path / filename
                        arcname = file_path.relative_to(root_path.parent)
                        zf.write(file_path, arcname)

            if not zip_path.exists():
                raise RuntimeError(f"压缩失败，未生成 zip 文件: {zip_path}")

            zip_size_mb = zip_path.stat().st_size / 1024 / 1024
            print(f"[FeishuDrive] 压缩完成: {zip_path.name}")
            print(f"[FeishuDrive] zip 大小: {zip_size_mb:.2f} MB")

            # 当前策略：不创建远端根目录，直接把 zip 上传到父文件夹
            print("[FeishuDrive] step1: 跳过创建文件夹，直接上传 zip")
            upload_parent_token = parent_folder_token
            root_folder_token = parent_folder_token
            root_folder_url = self._build_folder_url(root_folder_token)

            print("[FeishuDrive] step2: 开始上传 zip 文件")
            uploaded = self.upload_file(
                file_path=str(zip_path),
                parent_folder_token=upload_parent_token,
            )
            print("[FeishuDrive] step2 完成: zip 上传成功")

            upload_success = True

            file_token = uploaded.get("file_token") or uploaded.get("token")
            uploaded_file_url = uploaded.get("url") or self._build_file_url(file_token)

            return {
                "success": True,
                "root_folder_token": root_folder_token,
                "root_folder_url": root_folder_url,
                "uploaded_file_count": 1,
                "uploaded_files": [uploaded],
                "zip_file_name": zip_path.name,
                "file_token": file_token,
                "uploaded_file_url": uploaded_file_url,
            }

        except Exception as e:
            print(f"[FeishuDrive] upload_directory_tree 失败: {e}")
            raise

        finally:
            if zip_path and zip_path.exists():
                if upload_success:
                    try:
                        zip_path.unlink()
                        print(f"[FeishuDrive] 已删除临时 zip: {zip_path}")
                    except Exception as e:
                        print(f"[FeishuDrive] 删除临时 zip 失败: {e}")
                else:
                    print(f"[FeishuDrive] 上传未成功，保留临时 zip 便于排查: {zip_path}")