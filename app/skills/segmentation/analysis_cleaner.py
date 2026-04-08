from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from app.infrastructure.ocr import TencentOCRClient
from app.skills.segmentation.segmentation_models import SegmentationOutput


class AnalysisCleaner:
    def __init__(self, ocr_client: TencentOCRClient):
        self.ocr_client = ocr_client

    @staticmethod
    def _normalize_text(text: str) -> str:
        return text.strip().replace(" ", "")

    @staticmethod
    def _extract_box(det: dict):
        poly = det.get("ItemPolygon", {})
        x = int(poly.get("X", 0))
        y = int(poly.get("Y", 0))
        w = int(poly.get("Width", 0))
        h = int(poly.get("Height", 0))
        return x, y, w, h

    def _is_question_like_text(self, text: str) -> bool:
        t = self._normalize_text(text)
        if not t:
            return False

        if re.match(r"^[一二三四五六七八九十]+、", t):
            return True

        if any(k in t for k in ["计算题", "填空题", "选择题", "判断题", "应用题", "解答题"]):
            return True

        if "每题" in t or ("共" in t and "分" in t):
            return True

        return False

    @staticmethod
    def _get_analysis_mask(image: np.ndarray) -> np.ndarray:
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

        lower_blue = np.array([100, 43, 46])
        upper_blue = np.array([124, 255, 255])
        blue = cv2.inRange(hsv, lower_blue, upper_blue)

        lower_red1 = np.array([0, 43, 46])
        upper_red1 = np.array([10, 255, 255])
        lower_red2 = np.array([156, 43, 46])
        upper_red2 = np.array([180, 255, 255])

        red = cv2.bitwise_or(
            cv2.inRange(hsv, lower_red1, upper_red1),
            cv2.inRange(hsv, lower_red2, upper_red2),
        )

        mask = cv2.bitwise_or(blue, red)

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        mask = cv2.dilate(mask, kernel, iterations=1)
        return mask

    @staticmethod
    def _safe_whiteout(
        image: np.ndarray,
        analysis_mask: np.ndarray,
        box,
        overlap_threshold: int = 30,
        expand_x: int = 6,
        expand_y: int = 6,
    ) -> bool:
        h_img, w_img = image.shape[:2]
        x, y, w, h = box

        x1 = max(0, x - expand_x)
        y1 = max(0, y - expand_y)
        x2 = min(w_img, x + w + expand_x)
        y2 = min(h_img, y + h + expand_y)

        if x2 <= x1 or y2 <= y1:
            return False

        roi_mask = analysis_mask[y1:y2, x1:x2]
        if roi_mask.size == 0:
            return False

        overlap = cv2.countNonZero(roi_mask)

        if overlap < overlap_threshold:
            image[y1:y2, x1:x2] = 255
            return True

        return False

    @staticmethod
    def _remove_blue_rule_lines(
        image: np.ndarray,
        min_width_ratio: float = 0.45,
        max_height: int = 14,
        blue_ratio_threshold: float = 0.45,
    ) -> None:
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        lower_blue = np.array([90, 40, 80])
        upper_blue = np.array([140, 255, 255])
        blue_mask = cv2.inRange(hsv, lower_blue, upper_blue)

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 3))
        merged = cv2.morphologyEx(blue_mask, cv2.MORPH_CLOSE, kernel, iterations=1)

        contours, _ = cv2.findContours(merged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        h_img, w_img = image.shape[:2]

        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            if h <= max_height and w >= int(w_img * min_width_ratio):
                roi = blue_mask[y:y+h, x:x+w]
                blue_ratio = float(cv2.countNonZero(roi)) / max(roi.size, 1)
                if blue_ratio >= blue_ratio_threshold:
                    image[y:y+h, x:x+w] = 255

    @staticmethod
    def _crop_outer_whitespace(image: np.ndarray, margin: int = 8) -> np.ndarray:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        mask = gray < 245

        ys, xs = np.where(mask)
        if len(xs) == 0 or len(ys) == 0:
            return image

        x1 = max(0, xs.min() - margin)
        y1 = max(0, ys.min() - margin)
        x2 = min(image.shape[1], xs.max() + margin + 1)
        y2 = min(image.shape[0], ys.max() + margin + 1)

        return image[y1:y2, x1:x2]

    def clean_image(
        self,
        image_path: str,
        output_path: Optional[str] = None,
        save_debug_ocr_json: bool = False,
        remove_blue_lines: bool = True,
        crop_outer_whitespace: bool = False,
        overlap_threshold: int = 30,
    ) -> str:
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"找不到图片: {image_path}")

        image = cv2.imread(image_path)
        if image is None:
            raise ValueError(f"无法读取图片: {image_path}")

        if output_path is None:
            root, _ = os.path.splitext(image_path)
            output_path = f"{root}_clean.png"

        ocr_result = self.ocr_client.general_accurate_ocr(image_path)
        text_detections = self.ocr_client.get_text_detections(ocr_result)

        if save_debug_ocr_json:
            json_path = os.path.splitext(output_path)[0] + "_ocr.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(ocr_result, f, ensure_ascii=False, indent=2)

        analysis_mask = self._get_analysis_mask(image)
        cleaned = image.copy()

        for det in text_detections:
            text = det.get("DetectedText", "")
            box = self._extract_box(det)
            x, y, w, h = box

            if w <= 0 or h <= 0:
                continue
            if not self._is_question_like_text(text):
                continue

            t = self._normalize_text(text)

            is_header = False
            if re.match(r"^[一二三四五六七八九十]+、", t):
                is_header = True
            if any(k in t for k in ["计算题", "填空题", "选择题", "判断题", "应用题", "解答题"]):
                is_header = True
            if "每题" in t or ("共" in t and "分" in t):
                is_header = True

            if is_header:
                x1 = max(0, x - 8)
                y1 = max(0, y - 8)
                x2 = min(cleaned.shape[1], x + w + 8)
                y2 = min(cleaned.shape[0], y + h + 8)
                cleaned[y1:y2, x1:x2] = 255
                continue

            self._safe_whiteout(
                cleaned,
                analysis_mask,
                box,
                overlap_threshold=overlap_threshold,
                expand_x=6,
                expand_y=6,
            )

        if remove_blue_lines:
            self._remove_blue_rule_lines(cleaned)

        if crop_outer_whitespace:
            cleaned = self._crop_outer_whitespace(cleaned)

        cv2.imwrite(output_path, cleaned)
        return output_path

    def clean_folder(
            self,
            input_dir: str,
            output_dir: str,
            save_debug_ocr_json: bool = False,
            remove_blue_lines: bool = True,
            crop_outer_whitespace: bool = False,
            overlap_threshold: int = 30,
    ) -> SegmentationOutput:
        if not os.path.isdir(input_dir):
            return SegmentationOutput(
                success=False,
                message=f"输入文件夹不存在: {input_dir}",
            )

        os.makedirs(output_dir, exist_ok=True)

        exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
        outputs = []
        debug_files = []

        for current_root, _, files in os.walk(input_dir):
            current_root_path = Path(current_root)
            rel_root = current_root_path.relative_to(input_dir)

            target_root = Path(output_dir) / rel_root
            target_root.mkdir(parents=True, exist_ok=True)

            for name in sorted(files):
                ext = os.path.splitext(name)[1].lower()
                if ext not in exts:
                    continue

                in_path = str(current_root_path / name)
                out_path = str(target_root / f"{Path(name).stem}_clean.png")

                result_path = self.clean_image(
                    image_path=in_path,
                    output_path=out_path,
                    save_debug_ocr_json=save_debug_ocr_json,
                    remove_blue_lines=remove_blue_lines,
                    crop_outer_whitespace=crop_outer_whitespace,
                    overlap_threshold=overlap_threshold,
                )
                outputs.append(result_path)

        if not outputs:
            return SegmentationOutput(
                success=False,
                message="未找到任何可清洗的解析图片",
                output_dir=output_dir,
                files=[],
                debug_files=[],
                metadata={"cleaned_count": 0},
            )

        return SegmentationOutput(
            success=True,
            message=f"解析清洗完成，共生成 {len(outputs)} 张图片",
            output_dir=output_dir,
            files=outputs,
            debug_files=debug_files,
            metadata={
                "cleaned_count": len(outputs),
            },
        )