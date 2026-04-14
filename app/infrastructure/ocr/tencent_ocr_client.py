from __future__ import annotations

import base64
import json

from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.ocr.v20181119 import ocr_client, models

from app.config import settings

from app.shared.utils.retry import retry


class TencentOCRClient:
    def __init__(self):
        self._validate_config()
        self.client = self._build_client()

    def _validate_config(self) -> None:
        if not settings.tencent_secret_id:
            raise ValueError("缺少 TENCENT_SECRET_ID")
        if not settings.tencent_secret_key:
            raise ValueError("缺少 TENCENT_SECRET_KEY")
        if not settings.tencent_region:
            raise ValueError("缺少 TENCENT_REGION")

    def _build_client(self):
        cred = credential.Credential(
            settings.tencent_secret_id,
            settings.tencent_secret_key,
        )

        http_profile = HttpProfile()
        http_profile.endpoint = "ocr.tencentcloudapi.com"

        client_profile = ClientProfile()
        client_profile.httpProfile = http_profile

        return ocr_client.OcrClient(
            cred,
            settings.tencent_region,
            client_profile,
        )

    def image_to_base64(self, image_path: str) -> str:
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def general_accurate_ocr(self, image_path: str) -> dict:
        def _call():
            image_base64 = self.image_to_base64(image_path)

            req = models.GeneralBasicOCRRequest()
            params = {
                "ImageBase64": image_base64,
                "LanguageType": "zh",
                "IsPdf": False,
                "IsWords": False,
            }
            req.from_json_string(json.dumps(params))

            resp = self.client.GeneralBasicOCR(req)
            return json.loads(resp.to_json_string())

        return retry(_call, retries=3, delay=1.0, backoff=2.0)

    def question_split_layout_ocr(self, image_path: str) -> dict:
        def _call():
            image_base64 = self.image_to_base64(image_path)

            req = models.QuestionSplitLayoutOCRRequest()
            params = {
                "ImageBase64": image_base64
            }
            req.from_json_string(json.dumps(params))

            resp = self.client.QuestionSplitLayoutOCR(req)
            return json.loads(resp.to_json_string())

        return retry(_call, retries=3, delay=1.0, backoff=2.0)

    def question_split_ocr(self, image_path: str) -> dict:
        def _call():
            image_base64 = self.image_to_base64(image_path)

            req = models.QuestionSplitOCRRequest()
            params = {
                "ImageBase64": image_base64
            }
            req.from_json_string(json.dumps(params))

            resp = self.client.QuestionSplitOCR(req)
            return json.loads(resp.to_json_string())

        return retry(_call, retries=3, delay=1.0, backoff=2.0)

    @staticmethod
    def get_text_detections(result: dict) -> list[dict]:
        if "TextDetections" in result:
            return result["TextDetections"]
        if "Response" in result and "TextDetections" in result["Response"]:
            return result["Response"]["TextDetections"]
        return []

    @staticmethod
    def get_request_id(result: dict) -> str:
        if "RequestId" in result:
            return result["RequestId"]
        if "Response" in result and "RequestId" in result["Response"]:
            return result["Response"]["RequestId"]
        return ""