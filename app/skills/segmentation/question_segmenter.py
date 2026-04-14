from __future__ import annotations

import os
import re
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import Image

from app.skills.segmentation.segmentation_models import SegmentationOutput


@dataclass
class SegmentItem:
    page_no: int | None
    question_index_on_page: int
    question_no_ocr: int | None
    question_start_text: str
    crop_bbox: list[int]
    start_anchor_bbox: list[int]
    question_image_path: str
    analysis_image_path: str | None = None
    section_order: int | None = None
    section_raw_title: str | None = None
    section_y_range: list[int] | None = None


class QuestionSegmenter:
    """
    纯腾讯切题器：
    - 输入一页图片
    - 输出该页所有题目切图
    - 不负责题型 / 分数 / section 语义
    """

    def __init__(self, ocr_client: Any):
        self.ocr_client = ocr_client

    @staticmethod
    def _extract_page_no_from_image_path(image_path: str) -> int | None:
        stem = os.path.splitext(os.path.basename(image_path))[0]
        m = re.search(r"page[_\- ]?(\d+)$", stem, re.IGNORECASE)
        if m:
            return int(m.group(1))
        return None

    @staticmethod
    def _normalize_text_value(text_value: Any) -> str:
        if isinstance(text_value, str):
            return text_value.strip()
        if isinstance(text_value, list):
            return "".join(str(x) for x in text_value).strip()
        return str(text_value).strip() if text_value is not None else ""

    @staticmethod
    def _clamp(v: int, low: int, high: int) -> int:
        return max(low, min(v, high))

    @classmethod
    def _normalize_bbox(
        cls,
        bbox: Optional[List[int]],
        image_width: int,
        image_height: int,
    ) -> Optional[List[int]]:
        if bbox is None or len(bbox) != 4:
            return None

        x1, y1, x2, y2 = [int(v) for v in bbox]
        x1 = cls._clamp(x1, 0, image_width - 1)
        y1 = cls._clamp(y1, 0, image_height - 1)
        x2 = cls._clamp(x2, 1, image_width)
        y2 = cls._clamp(y2, 1, image_height)

        if x2 <= x1 or y2 <= y1:
            return None
        return [x1, y1, x2, y2]

    @staticmethod
    def _bbox_area(b: Optional[List[int]]) -> int:
        if not b:
            return 0
        return max(0, b[2] - b[0]) * max(0, b[3] - b[1])

    @classmethod
    def _bbox_intersection(
        cls,
        a: Optional[List[int]],
        b: Optional[List[int]],
    ) -> Optional[List[int]]:
        if not a or not b:
            return None

        x1 = max(a[0], b[0])
        y1 = max(a[1], b[1])
        x2 = min(a[2], b[2])
        y2 = min(a[3], b[3])

        if x2 <= x1 or y2 <= y1:
            return None
        return [x1, y1, x2, y2]

    @classmethod
    def _bbox_iou(cls, a: Optional[List[int]], b: Optional[List[int]]) -> float:
        inter = cls._bbox_intersection(a, b)
        if not inter:
            return 0.0
        inter_area = cls._bbox_area(inter)
        union_area = cls._bbox_area(a) + cls._bbox_area(b) - inter_area
        if union_area <= 0:
            return 0.0
        return inter_area / union_area

    @staticmethod
    def _crop_and_save(image: Image.Image, bbox: List[int], save_path: str) -> None:
        cropped = image.crop(tuple(bbox))
        cropped.save(save_path)

    @staticmethod
    def _coord4_to_bbox(coord: Dict[str, Any]) -> Optional[List[int]]:
        if not isinstance(coord, dict):
            return None

        points = []
        for key in ["LeftTop", "RightTop", "LeftBottom", "RightBottom"]:
            p = coord.get(key)
            if isinstance(p, dict) and "X" in p and "Y" in p:
                points.append((int(p["X"]), int(p["Y"])))

        if len(points) < 2:
            return None

        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        x1 = min(xs)
        y1 = min(ys)
        x2 = max(xs)
        y2 = max(ys)

        if x2 <= x1 or y2 <= y1:
            return None
        return [x1, y1, x2, y2]

    @classmethod
    def _extract_first_bbox_from_coord_field(cls, coord_field: Any) -> Optional[List[int]]:
        if isinstance(coord_field, dict):
            return cls._coord4_to_bbox(coord_field)

        if isinstance(coord_field, list):
            for item in coord_field:
                b = cls._coord4_to_bbox(item)
                if b:
                    return b
        return None

    @classmethod
    def _extract_best_text_item(cls, text_items: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(text_items, list) or not text_items:
            return None

        best_item = None
        best_area = -1
        for item in text_items:
            if not isinstance(item, dict):
                continue
            bbox = cls._extract_first_bbox_from_coord_field(item.get("Coord"))
            if not bbox:
                continue
            area = cls._bbox_area(bbox)
            if area > best_area:
                best_item = item
                best_area = area
        return best_item

    @classmethod
    def _extract_best_text_bbox(cls, text_items: Any) -> Optional[List[int]]:
        item = cls._extract_best_text_item(text_items)
        if not item:
            return None
        return cls._extract_first_bbox_from_coord_field(item.get("Coord"))

    @classmethod
    def _extract_question_no_from_question_item(cls, question_items: Any) -> Optional[int]:
        if not isinstance(question_items, list):
            return None

        patterns = [
            re.compile(r"^\s*(\d{1,3})\s*[\.．、]\s*"),
            re.compile(r"^\s*(\d{1,3})\s*[\)\]）]\s*"),
        ]

        for item in question_items:
            if not isinstance(item, dict):
                continue

            text = cls._normalize_text_value(item.get("Text"))
            for p in patterns:
                m = p.match(text)
                if m:
                    try:
                        return int(m.group(1))
                    except Exception:
                        pass

            idx = item.get("Index")
            if isinstance(idx, int):
                return idx

        return None

    @classmethod
    def _normalize_layout_questions(
            cls,
            resp: Dict[str, Any],
            image_width: int,
            image_height: int,
    ) -> List[dict]:
        question_info = resp.get("QuestionInfo")
        if question_info is None:
            question_info = resp.get("Response", {}).get("QuestionInfo", [])

        items: List[dict] = []

        if not isinstance(question_info, list):
            return items

        running_qno = 1

        for page in question_info:
            if not isinstance(page, dict):
                continue

            result_list = page.get("ResultList", [])
            if not isinstance(result_list, list):
                continue

            for result in result_list:
                if not isinstance(result, dict):
                    continue

                outer_bbox = cls._extract_first_bbox_from_coord_field(result.get("Coord"))
                outer_bbox = cls._normalize_bbox(outer_bbox, image_width, image_height)
                if not outer_bbox:
                    continue

                qno = None
                question_items = result.get("Question", [])
                if isinstance(question_items, list) and question_items:
                    qno = cls._extract_question_no_from_question_item(question_items)

                if qno is None:
                    qno = running_qno

                items.append({
                    "question_no": qno,
                    "bbox": outer_bbox,
                    "raw": result,
                })
                running_qno += 1

        return sorted(items, key=lambda x: x["question_no"])

    @classmethod
    def _normalize_question_split_items(
            cls,
            resp: Dict[str, Any],
            image_width: int,
            image_height: int,
    ) -> List[dict]:
        question_info = resp.get("QuestionInfo")
        if question_info is None:
            question_info = resp.get("Response", {}).get("QuestionInfo", [])

        items: List[dict] = []

        if not isinstance(question_info, list):
            return items

        running_qno = 1

        for page in question_info:
            if not isinstance(page, dict):
                continue

            result_list = page.get("ResultList", [])
            if not isinstance(result_list, list):
                continue

            for result in result_list:
                if not isinstance(result, dict):
                    continue

                outer_bbox = cls._extract_first_bbox_from_coord_field(result.get("Coord"))
                outer_bbox = cls._normalize_bbox(outer_bbox, image_width, image_height)
                if not outer_bbox:
                    continue

                question_items = result.get("Question", [])
                question_bbox = cls._extract_best_text_bbox(question_items)
                question_bbox = cls._normalize_bbox(question_bbox, image_width, image_height) if question_bbox else None

                question_item = cls._extract_best_text_item(question_items)
                question_text = cls._normalize_text_value(question_item.get("Text")) if question_item else ""

                qno = cls._extract_question_no_from_question_item(question_items)
                if qno is None:
                    qno = running_qno

                items.append({
                    "question_no": qno,
                    "outer_bbox": outer_bbox,
                    "question_bbox": question_bbox,
                    "question_text": question_text,
                    "raw": result,
                })
                running_qno += 1

        return sorted(items, key=lambda x: x["question_no"])

    @classmethod
    def _align_split_items_to_layout(cls, layout_items: List[dict], split_items: List[dict]) -> Dict[int, dict]:
        result: Dict[int, dict] = {}
        split_by_qno = {item["question_no"]: item for item in split_items}

        for layout in layout_items:
            qno = layout["question_no"]
            matched = split_by_qno.get(qno)

            if matched is None:
                best = None
                best_iou = 0.0
                for s in split_items:
                    iou = cls._bbox_iou(layout["bbox"], s["outer_bbox"])
                    if iou > best_iou:
                        best_iou = iou
                        best = s
                matched = best

            result[qno] = matched

        return result

    def segment_page(
        self,
        image_path: str,
        output_dir: str,
        solution_image_path: str | None = None,
        analysis_output_dir: str | None = None,
        top_pad: int = 20,
        bottom_pad: int = 20,
        save_aligned_solution_preview: bool = False,
        analysis_extra_bottom_pad: int = 10,
    ) -> SegmentationOutput:
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)
        os.makedirs(output_dir, exist_ok=True)

        image = Image.open(image_path).convert("RGB")
        image_width, image_height = image.size
        page_no = self._extract_page_no_from_image_path(image_path)

        layout_resp = self.ocr_client.question_split_layout_ocr(image_path)
        # print("layout_resp:", layout_resp)
        split_resp = self.ocr_client.question_split_ocr(image_path)

        layout_items = self._normalize_layout_questions(layout_resp, image_width, image_height)
        split_items = self._normalize_question_split_items(split_resp, image_width, image_height)
        split_aligned = self._align_split_items_to_layout(layout_items, split_items)

        if not layout_items:
            return SegmentationOutput(
                success=False,
                message="未识别出任何题目",
                output_dir=output_dir,
                files=[],
                debug_files=[],
                metadata={
                    "page_no": page_no,
                    "source_image_path": image_path,
                    "question_count": 0,
                    "segments": [],
                },
            )

        question_files: list[str] = []
        segments: list[dict] = []

        for i, layout in enumerate(layout_items, start=1):
            qno = layout["question_no"]
            outer_bbox = layout["bbox"]
            split_item = split_aligned.get(qno)

            question_bbox = None
            question_text = ""

            if split_item:
                qbox = split_item.get("question_bbox")
                if qbox:
                    inter = self._bbox_intersection(qbox, outer_bbox)
                    if inter:
                        question_bbox = [outer_bbox[0], inter[1], outer_bbox[2], inter[3]]
                question_text = split_item.get("question_text", "")

            if question_bbox is None:
                question_bbox = outer_bbox

            q_path = str(Path(output_dir) / f"question_{i}.png")
            self._crop_and_save(image, question_bbox, q_path)
            question_files.append(q_path)

            item = SegmentItem(
                page_no=page_no,
                question_index_on_page=i,
                question_no_ocr=qno,
                question_start_text=question_text[:80] if question_text else str(qno),
                crop_bbox=question_bbox,
                start_anchor_bbox=outer_bbox,
                question_image_path=q_path,
                analysis_image_path=None,
            )

            item_dict = asdict(item)
            item_dict["source_image_path"] = image_path
            item_dict["image_path"] = q_path
            item_dict["outer_bbox"] = outer_bbox
            item_dict["question_text"] = question_text
            segments.append(item_dict)

        return SegmentationOutput(
            success=True,
            message=f"题目切割完成，共生成 {len(question_files)} 张题目图",
            output_dir=output_dir,
            files=question_files,
            debug_files=[],
            metadata={
                "question_count": len(question_files),
                "analysis_count": 0,
                "analysis_files": [],
                "analysis_output_dir": None,
                "request_id": "",
                "ocr_request_id": "",
                "ocr_provider": self.ocr_client.__class__.__name__,
                "page_no": page_no,
                "source_image_path": image_path,
                "solution_image_path": None,
                "image_size": {
                    "width": image_width,
                    "height": image_height,
                },
                "crop_left_right": [0, image_width],
                "header_boxes": [],
                "sections": [],
                "question_starts_before_filter": [],
                "question_starts_after_filter": [],
                "text_detections": [],
                "ocr_raw_response": {
                    "layout_raw_response": layout_resp,
                    "split_raw_response": split_resp,
                },
                "segments": segments,
                "alignment": None,
            },
        )