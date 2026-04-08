from __future__ import annotations

import os
import re
import shutil
from typing import Any

import cv2
import numpy as np

from app.skills.segmentation.segmentation_models import SegmentationOutput


class QuestionSegmenter:
    def __init__(self, ocr_client: Any):
        self.ocr_client = ocr_client

    @staticmethod
    def _normalize_text(text: str) -> str:
        return text.strip().replace(" ", "")

    @staticmethod
    def _extract_box(det: dict):
        poly = det.get("ItemPolygon", {}) or {}
        x = int(poly.get("X", 0))
        y = int(poly.get("Y", 0))
        w = int(poly.get("Width", 0))
        h = int(poly.get("Height", 0))
        return x, y, w, h

    def _extract_question_number(self, text: str):
        t = self._normalize_text(text)
        m = re.match(r"^(\d{1,2})[\.、．]", t)
        if m:
            return int(m.group(1))
        return None

    @staticmethod
    def _extract_page_no_from_image_path(image_path: str) -> int | None:
        """
        从 rendered page 路径中提取页码，例如：
        .../page_1.png -> 1
        """
        stem = os.path.splitext(os.path.basename(image_path))[0]
        m = re.search(r"page_(\d+)$", stem)
        if m:
            return int(m.group(1))
        return None

    def _find_question_starts(
        self,
        text_detections,
        x_threshold=400,
        small_box_width=120,
        min_question_gap=160,
    ):
        question_starts = []

        for det in text_detections:
            text = det.get("DetectedText", "").strip()
            x, y, w, h = self._extract_box(det)
            t = self._normalize_text(text)

            cond_full_line = re.match(r"^\d{1,2}[\.、．]", t) is not None and x < x_threshold
            cond_small_number = re.match(r"^\d{1,2}[\.、．]$", t) is not None and x < x_threshold and w < small_box_width

            if cond_full_line or cond_small_number:
                question_starts.append({
                    "num": self._extract_question_number(text),
                    "text": text,
                    "x": x,
                    "y": y,
                    "w": w,
                    "h": h,
                    "source": det.get("RawType", "ocr"),
                    "raw_category": det.get("RawCategory"),
                })

        question_starts.sort(key=lambda d: d["y"])

        merged = []
        for q in question_starts:
            if not merged:
                merged.append(q)
                continue
            dy = q["y"] - merged[-1]["y"]
            if dy < min_question_gap:
                continue
            merged.append(q)
        return merged

    @staticmethod
    def _is_section_header_text(text: str) -> bool:
        t = text.strip().replace(" ", "")
        if re.match(r"^[一二三四五六七八九十]+、", t):
            return True
        keywords = ["计算题", "填空题", "选择题", "判断题", "应用题", "解答题", "解决问题"]
        if any(k in t for k in keywords):
            return True
        if "每题" in t and "分" in t:
            return True
        return False

    def _collect_section_header_boxes(self, text_detections):
        header_boxes = []
        for det in text_detections:
            text = det.get("DetectedText", "").strip()
            if self._is_section_header_text(text):
                x, y, w, h = self._extract_box(det)
                header_boxes.append({
                    "text": text,
                    "x": x,
                    "y": y,
                    "w": w,
                    "h": h,
                })
        header_boxes.sort(key=lambda d: d["y"])
        return header_boxes

    @staticmethod
    def _filter_starts_by_header_boxes(starts, header_boxes, y_tol=100):
        filtered = []
        for s in starts:
            remove = False
            for hb in header_boxes:
                if abs(s["y"] - hb["y"]) <= y_tol:
                    remove = True
                    break
            if not remove:
                filtered.append(s)
        return filtered

    @staticmethod
    def _find_next_header_y_between(header_boxes, y_start, y_next):
        candidates = []
        for hb in header_boxes:
            if y_start < hb["y"] < y_next:
                candidates.append(hb["y"])
        if not candidates:
            return None
        return min(candidates)

    @staticmethod
    def _is_formula_heavy_page(text_detections):
        math_like = 0
        chinese_like = 0
        for det in text_detections:
            t = det.get("DetectedText", "")
            if re.search(r"[+\-×÷=()/]", t) or re.search(r"\d\s*/\s*\d", t):
                math_like += 1
            if re.search(r"[\u4e00-\u9fff]", t):
                chinese_like += 1
        return math_like >= 5 and math_like > chinese_like

    def _get_crop_left_right(self, text_detections, min_y, img_w):
        if self._is_formula_heavy_page(text_detections):
            return 0, img_w

        xs = []
        xe = []

        for det in text_detections:
            x, y, w, h = self._extract_box(det)
            if y >= min_y and w > 0 and h > 0:
                xs.append(x)
                xe.append(x + w)

        if not xs:
            left, right = 0, img_w
        else:
            left = max(0, min(xs) - 20)
            right = min(img_w, max(xe) + 20)

        if right - left < img_w * 0.6:
            left, right = 0, img_w

        return left, right

    @staticmethod
    def _find_text_bands_in_region(
        image,
        y1,
        y2,
        x1=0,
        x2=None,
        min_band_height=25,
        merge_gap=120,
        pixel_threshold=30,
    ):
        h, w = image.shape[:2]
        if x2 is None:
            x2 = w
        roi = image[y1:y2, x1:x2]
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        _, bw = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)
        row_sum = np.sum(bw > 0, axis=1)

        bands = []
        in_band = False
        start = 0
        for i, val in enumerate(row_sum):
            if val > pixel_threshold and not in_band:
                start = i
                in_band = True
            elif val <= pixel_threshold and in_band:
                end = i
                if end - start >= min_band_height:
                    bands.append((start, end))
                in_band = False
        if in_band:
            end = len(row_sum)
            if end - start >= min_band_height:
                bands.append((start, end))

        merged = []
        for b in bands:
            if not merged:
                merged.append(list(b))
            else:
                if b[0] - merged[-1][1] <= merge_gap:
                    merged[-1][1] = b[1]
                else:
                    merged.append(list(b))

        return [(y1 + a, y1 + b) for a, b in merged]

    def _refine_large_gaps_with_projection(self, image, starts, large_gap_threshold=700):
        if len(starts) < 2:
            return starts

        refined = [starts[0]]
        for i in range(len(starts) - 1):
            cur = starts[i]
            nxt = starts[i + 1]
            gap = nxt["y"] - cur["y"]

            if gap < large_gap_threshold:
                refined.append(nxt)
                continue

            bands = self._find_text_bands_in_region(
                image,
                y1=cur["y"] + 40,
                y2=nxt["y"] - 20,
                x1=0,
                x2=image.shape[1],
            )

            extra_candidates = []
            for top, bottom in bands:
                if top - cur["y"] < 260:
                    continue
                extra_candidates.append({
                    "num": None,
                    "text": "[projection_band]",
                    "x": 0,
                    "y": top,
                    "w": image.shape[1],
                    "h": bottom - top,
                    "source": "projection",
                    "raw_category": None,
                })

            cleaned = []
            for c in extra_candidates:
                if nxt["y"] - c["y"] > 80:
                    cleaned.append(c)

            refined.extend(cleaned)
            refined.append(nxt)

        refined.sort(key=lambda d: d["y"])

        dedup = []
        for q in refined:
            if not dedup:
                dedup.append(q)
            else:
                if abs(q["y"] - dedup[-1]["y"]) > 40:
                    dedup.append(q)

        return dedup

    @staticmethod
    def _build_sections_from_header_boxes(header_boxes, img_h):
        """
        根据题型标题框构建 section 区间。
        这里只做轻量规则，不改动你后续更复杂逻辑的空间。
        """
        sections = []
        if not header_boxes:
            return sections

        for i, hb in enumerate(header_boxes):
            y_start = hb["y"]
            if i < len(header_boxes) - 1:
                y_end = max(y_start, header_boxes[i + 1]["y"] - 1)
            else:
                y_end = img_h - 1

            sections.append({
                "section_order": i + 1,
                "raw_title": hb["text"],
                "y_start": y_start,
                "y_end": y_end,
                "bbox": [hb["x"], hb["y"], hb["x"] + hb["w"], hb["y"] + hb["h"]],
            })

        return sections

    @staticmethod
    def _assign_section_for_start(start, sections):
        if not sections:
            return None

        y = start["y"]
        for sec in sections:
            if sec["y_start"] <= y <= sec["y_end"]:
                return sec

        candidates = [sec for sec in sections if sec["y_start"] <= y]
        if candidates:
            return candidates[-1]

        return None

    @staticmethod
    def _serialize_detections(text_detections):
        serialized = []
        for det in text_detections:
            serialized.append({
                "DetectedText": det.get("DetectedText", ""),
                "ItemPolygon": det.get("ItemPolygon", {}),
                "RawCategory": det.get("RawCategory"),
                "RawType": det.get("RawType"),
            })
        return serialized

    def segment_page(
        self,
        image_path: str,
        output_dir: str,
        top_pad: int = 30,
        bottom_pad: int = 20,
    ) -> SegmentationOutput:
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)
        os.makedirs(output_dir, exist_ok=True)

        image = cv2.imread(image_path)
        if image is None:
            return SegmentationOutput(
                success=False,
                message=f"无法读取图片: {image_path}",
            )

        img_h, img_w = image.shape[:2]
        page_no = self._extract_page_no_from_image_path(image_path)

        ocr_result = self.ocr_client.general_ocr(image_path)
        text_detections = self.ocr_client.get_text_detections(ocr_result)

        if not text_detections:
            return SegmentationOutput(
                success=False,
                message="OCR没有返回任何文本结果",
                output_dir=output_dir,
                debug_files=[],
                metadata={
                    "page_no": page_no,
                    "source_image_path": image_path,
                    "ocr_request_id": self.ocr_client.get_request_id(ocr_result),
                    "ocr_provider": self.ocr_client.__class__.__name__,
                    "ocr_raw_response": ocr_result,
                    "text_detections": [],
                },
            )

        starts_before_filter = self._find_question_starts(text_detections)
        starts_before_filter = [
            q for q in starts_before_filter
            if not self._is_section_header_text(q["text"])
        ]

        header_boxes = self._collect_section_header_boxes(text_detections)

        starts_after_projection = self._refine_large_gaps_with_projection(
            image,
            starts_before_filter,
            large_gap_threshold=700,
        )
        starts = self._filter_starts_by_header_boxes(
            starts_after_projection,
            header_boxes,
            y_tol=100,
        )

        if not starts:
            return SegmentationOutput(
                success=False,
                message="未检测到题目起点",
                output_dir=output_dir,
                debug_files=[],
                metadata={
                    "page_no": page_no,
                    "source_image_path": image_path,
                    "ocr_request_id": self.ocr_client.get_request_id(ocr_result),
                    "ocr_provider": self.ocr_client.__class__.__name__,
                    "ocr_raw_response": ocr_result,
                    "text_detections": self._serialize_detections(text_detections),
                    "question_starts_before_filter": starts_before_filter,
                    "question_starts_after_projection": starts_after_projection,
                    "question_starts_after_filter": [],
                    "header_boxes": header_boxes,
                    "sections": self._build_sections_from_header_boxes(header_boxes, img_h),
                    "is_formula_heavy_page": self._is_formula_heavy_page(text_detections),
                },
            )

        body_left, body_right = self._get_crop_left_right(
            text_detections=text_detections,
            min_y=starts[0]["y"],
            img_w=img_w,
        )

        saved_files = []
        segments = []
        sections = self._build_sections_from_header_boxes(header_boxes, img_h)

        for i in range(len(starts)):
            y_start = max(0, starts[i]["y"] - top_pad)

            if i < len(starts) - 1:
                next_start_y = starts[i + 1]["y"]
                y_end = max(y_start + 20, next_start_y - bottom_pad)
                next_header_y = self._find_next_header_y_between(
                    header_boxes,
                    starts[i]["y"],
                    next_start_y,
                )
                if next_header_y is not None:
                    y_end = min(y_end, max(y_start + 20, next_header_y - bottom_pad))
            else:
                y_end = img_h - 10

            crop = image[y_start:y_end, body_left:body_right]
            save_path = os.path.join(output_dir, f"question_{i + 1}.png")
            cv2.imwrite(save_path, crop)
            saved_files.append(save_path)

            matched_section = self._assign_section_for_start(starts[i], sections)

            segment_item = {
                "page_no": page_no,
                "source_image_path": image_path,
                "question_index_on_page": i + 1,
                "question_no_ocr": starts[i].get("num"),
                "question_start_text": starts[i].get("text"),
                "crop_bbox": [body_left, y_start, body_right, y_end],
                "start_anchor_bbox": [
                    starts[i]["x"],
                    starts[i]["y"],
                    starts[i]["x"] + starts[i]["w"],
                    starts[i]["y"] + starts[i]["h"],
                ],
                "image_path": save_path,
            }

            if matched_section:
                segment_item.update({
                    "section_order": matched_section.get("section_order"),
                    "section_raw_title": matched_section.get("raw_title"),
                    "section_y_range": [
                        matched_section.get("y_start"),
                        matched_section.get("y_end"),
                    ],
                })

            segments.append(segment_item)

        return SegmentationOutput(
            success=True,
            message=f"题目切割完成，共生成 {len(saved_files)} 张图片",
            output_dir=output_dir,
            files=saved_files,
            debug_files=[],
            metadata={
                "question_count": len(saved_files),
                "request_id": self.ocr_client.get_request_id(ocr_result),
                "ocr_request_id": self.ocr_client.get_request_id(ocr_result),
                "ocr_provider": self.ocr_client.__class__.__name__,
                "page_no": page_no,
                "source_image_path": image_path,
                "image_size": {
                    "width": img_w,
                    "height": img_h,
                },
                "crop_left_right": [body_left, body_right],
                "is_formula_heavy_page": self._is_formula_heavy_page(text_detections),
                "header_boxes": header_boxes,
                "sections": sections,
                "question_starts_before_filter": starts_before_filter,
                "question_starts_after_projection": starts_after_projection,
                "question_starts_after_filter": starts,
                "text_detections": self._serialize_detections(text_detections),
                "ocr_raw_response": ocr_result,
                "segments": segments,
            },
        )