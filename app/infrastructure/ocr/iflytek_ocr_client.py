from __future__ import annotations

import base64
import json
import time
import hashlib
import requests

from app.config import settings
from app.shared.utils.retry import retry


class IflytekOCRClient:
    def __init__(self):
        self._validate_config()
        # 先使用 HTTP，当前环境下 HTTPS 会触发 SSL 握手错误
        self.url = "http://webapi.xfyun.cn/v1/service/v1/ocr/general"

    def _validate_config(self) -> None:
        if not settings.iflytek_app_id or not settings.iflytek_app_id.strip():
            raise ValueError("缺少 IFLYTEK_APP_ID")
        if not settings.iflytek_api_key or not settings.iflytek_api_key.strip():
            raise ValueError("缺少 IFLYTEK_API_KEY")

    def image_to_base64(self, image_path: str) -> str:
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def _build_headers(self) -> dict:
        app_id = settings.iflytek_app_id.strip()
        api_key = settings.iflytek_api_key.strip()

        cur_time = str(int(time.time()))
        param = {
            "language": "cn|en",
            "location": "false",
        }
        param_json = json.dumps(param, separators=(",", ":"))
        param_base64 = base64.b64encode(param_json.encode("utf-8")).decode("utf-8")

        check_sum = hashlib.md5((api_key + cur_time + param_base64).encode("utf-8")).hexdigest()

        return {
            "X-Appid": app_id,
            "X-CurTime": cur_time,
            "X-Param": param_base64,
            "X-CheckSum": check_sum,
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
        }

    def general_ocr(self, image_path: str) -> dict:
        @retry(retries=3, delay=1.0)
        def _call():
            image_base64 = self.image_to_base64(image_path)
            headers = self._build_headers()
            data = {"image": image_base64}

            response = requests.post(
                self.url,
                headers=headers,
                data=data,
                timeout=30,
            )

            if response.status_code != 200:
                raise Exception(f"讯飞接口请求失败: {response.status_code} {response.text}")

            res_json = response.json()
            code = str(res_json.get("code", ""))

            if code != "0":
                raise Exception(
                    f"讯飞返回错误码: {res_json.get('code')}, "
                    f"消息: {res_json.get('desc') or res_json.get('message') or response.text}"
                )

            return res_json

        return _call()

    @staticmethod
    def get_text_detections(result: dict) -> list[dict]:
        detections = []
        data = result.get("data", {})

        for block in data.get("block", []):
            for line in block.get("line", []):
                for word in line.get("word", []):
                    content = word.get("content", "")
                    if content:
                        detections.append({
                            "DetectedText": content
                        })

        return detections

    @staticmethod
    def get_request_id(result: dict) -> str:
        return result.get("sid", "")