from __future__ import annotations

import base64
import json
import os

from xfyunsdkocr.llm_ocr_client import LlmOcrClient, LlmOcrParam

from app.config import settings
from app.shared.utils.retry import retry


class OCRForLLMClient:
    def __init__(self):
        self._validate_config()
        self.client = self._build_client()

    def _validate_config(self):
        if not settings.iflytek_app_id:
            raise ValueError("缺少 IFLYTEK_APP_ID")
        if not settings.iflytek_api_key:
            raise ValueError("缺少 IFLYTEK_API_KEY")
        if not settings.iflytek_api_secret:
            raise ValueError("缺少 IFLYTEK_API_SECRET")

    def _build_client(self):
        return LlmOcrClient(
            app_id=settings.iflytek_app_id,
            api_key=settings.iflytek_api_key,
            api_secret=settings.iflytek_api_secret,
        )

    def image_to_base64(self, image_path: str) -> str:
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    @staticmethod
    def _infer_format(image_path: str) -> str:
        ext = os.path.splitext(image_path)[1].lower()
        if ext in {".jpg", ".jpeg"}:
            return "jpg"
        if ext == ".png":
            return "png"
        if ext == ".bmp":
            return "bmp"
        if ext == ".webp":
            return "webp"
        return "jpg"

    def general_ocr(self, image_path: str) -> dict:
        @retry(retries=3, delay=1.0)
        def _call():
            image_base64 = self.image_to_base64(image_path)

            param = LlmOcrParam(
                image_base64=image_base64,
                format=self._infer_format(image_path),
            )

            resp = self.client.send(param)
            json_resp = json.loads(resp)

            code = json_resp.get("header", {}).get("code")
            if code != 0:
                raise Exception(f"OCR大模型失败: {json_resp}")

            result_base64 = (
                json_resp.get("payload", {})
                .get("result", {})
                .get("text", "")
            )

            decoded_text = base64.b64decode(result_base64).decode("utf-8")

            decoded_json = None
            try:
                decoded_json = json.loads(decoded_text)
            except Exception:
                decoded_json = None

            return {
                "raw": json_resp,
                "text": decoded_text,
                "decoded_json": decoded_json,
            }

        return _call()

    @staticmethod
    def _get_request_id_from_raw(raw: dict) -> str:
        header = raw.get("header", {})
        if header.get("sid"):
            return header["sid"]
        if header.get("request_id"):
            return header["request_id"]
        if raw.get("sid"):
            return raw["sid"]
        return ""

    @staticmethod
    def get_request_id(result: dict) -> str:
        raw = result.get("raw", {})
        return OCRForLLMClient._get_request_id_from_raw(raw)

    @staticmethod
    def _extract_bbox_from_coord(coord) -> dict:
        if not coord or not isinstance(coord, list):
            return {"X": 0, "Y": 0, "Width": 0, "Height": 0}

        xs = [int(p.get("x", 0)) for p in coord if isinstance(p, dict)]
        ys = [int(p.get("y", 0)) for p in coord if isinstance(p, dict)]

        if not xs or not ys:
            return {"X": 0, "Y": 0, "Width": 0, "Height": 0}

        x_min = min(xs)
        y_min = min(ys)
        x_max = max(xs)
        y_max = max(ys)

        return {
            "X": x_min,
            "Y": y_min,
            "Width": max(0, x_max - x_min),
            "Height": max(0, y_max - y_min),
        }

    @staticmethod
    def _normalize_text_value(text_value) -> str:
        if isinstance(text_value, str):
            return text_value.strip()
        if isinstance(text_value, list):
            return "".join(str(x) for x in text_value).strip()
        return str(text_value).strip() if text_value is not None else ""

    @classmethod
    def _collect_nodes_by_type(cls, node, target_type: str, out: list[dict]):
        if isinstance(node, dict):
            if node.get("type") == target_type:
                out.append(node)
            for value in node.values():
                cls._collect_nodes_by_type(value, target_type, out)
        elif isinstance(node, list):
            for item in node:
                cls._collect_nodes_by_type(item, target_type, out)

    @classmethod
    def _build_detection_from_node(cls, node: dict) -> dict | None:
        text = cls._normalize_text_value(node.get("text"))
        if not text:
            return None

        bbox = cls._extract_bbox_from_coord(node.get("coord", []))

        return {
            "DetectedText": text,
            "ItemPolygon": bbox,
            "RawCategory": node.get("category"),
            "RawType": node.get("type"),
            "RawNode": node,
        }

    @classmethod
    def get_text_detections(cls, result: dict) -> list[dict]:
        """
        统一输出格式，尽量兼容现有 pipeline：
        [
            {
                "DetectedText": "...",
                "ItemPolygon": {"X": ..., "Y": ..., "Width": ..., "Height": ...},
                ...
            }
        ]
        """
        decoded_json = result.get("decoded_json")
        if not decoded_json:
            text = result.get("text", "")
            lines = text.split("\n")
            return [
                {
                    "DetectedText": line.strip(),
                    "ItemPolygon": {"X": 0, "Y": 0, "Width": 0, "Height": 0},
                    "RawCategory": None,
                    "RawType": "plain_text_line",
                }
                for line in lines
                if line.strip()
            ]

        detections: list[dict] = []

        # 优先取 textline，最适合后面做题号锚点检测
        textline_nodes: list[dict] = []
        cls._collect_nodes_by_type(decoded_json, "textline", textline_nodes)

        for node in textline_nodes:
            det = cls._build_detection_from_node(node)
            if det:
                detections.append(det)

        if detections:
            return detections

        # 如果 textline 没取到，再 fallback 到 paragraph
        paragraph_nodes: list[dict] = []
        cls._collect_nodes_by_type(decoded_json, "paragraph", paragraph_nodes)

        for node in paragraph_nodes:
            det = cls._build_detection_from_node(node)
            if det:
                detections.append(det)

        if detections:
            return detections

        # 再 fallback 到 text_block
        text_block_nodes: list[dict] = []
        cls._collect_nodes_by_type(decoded_json, "text_block", text_block_nodes)

        for node in text_block_nodes:
            det = cls._build_detection_from_node(node)
            if det:
                detections.append(det)

        if detections:
            return detections

        # 最后兜底，按纯文本逐行返回
        text = result.get("text", "")
        lines = text.split("\n")
        return [
            {
                "DetectedText": line.strip(),
                "ItemPolygon": {"X": 0, "Y": 0, "Width": 0, "Height": 0},
                "RawCategory": None,
                "RawType": "plain_text_line",
            }
            for line in lines
            if line.strip()
        ]