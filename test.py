import os
import re
import json
import time
import hmac
import base64
import hashlib
import datetime
from typing import Any, Dict, List, Optional

import requests
from PIL import Image, ImageDraw


# =========================
# 配置
# =========================
TENCENT_SECRET_ID = os.getenv("TENCENT_SECRET_ID", "")
TENCENT_SECRET_KEY = os.getenv("TENCENT_SECRET_KEY", "")
TENCENT_REGION = os.getenv("TENCENT_REGION", "ap-beijing")
TENCENT_ENDPOINT = "ocr.tencentcloudapi.com"
TENCENT_SERVICE = "ocr"
TENCENT_VERSION = "2018-11-19"

IMAGE_PATH = r"runtime_data/tasks/task_dbf96301f1d0/rendered_pages/blank/page_9.png"
OUTPUT_DIR = r"output_crops_tencent_only2"


# =========================================================
# 基础工具
# =========================================================
def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def encode_image_to_base64(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def clamp(v: int, low: int, high: int) -> int:
    return max(low, min(v, high))


def crop_and_save(image: Image.Image, bbox: List[int], save_path: str) -> None:
    cropped = image.crop(tuple(bbox))
    cropped.save(save_path)


def draw_boxes_preview(
    image: Image.Image,
    boxes: List[Dict[str, Any]],
    save_path: str,
) -> None:
    preview = image.copy()
    draw = ImageDraw.Draw(preview)

    for item in boxes:
        bbox = item["bbox"]
        label = item["label"]
        color = item["color"]
        draw.rectangle(bbox, outline=color, width=3)
        draw.text((bbox[0] + 4, max(0, bbox[1] - 18)), label, fill=color)

    preview.save(save_path)


def normalize_text_value(text_value: Any) -> str:
    if isinstance(text_value, str):
        return text_value.strip()
    if isinstance(text_value, list):
        return "".join(str(x) for x in text_value).strip()
    return str(text_value).strip() if text_value is not None else ""


def normalize_bbox(
    bbox: Optional[List[int]],
    image_width: int,
    image_height: int,
) -> Optional[List[int]]:
    if bbox is None or len(bbox) != 4:
        return None

    x1, y1, x2, y2 = [int(v) for v in bbox]

    x1 = clamp(x1, 0, image_width - 1)
    y1 = clamp(y1, 0, image_height - 1)
    x2 = clamp(x2, 1, image_width)
    y2 = clamp(y2, 1, image_height)

    if x2 <= x1 or y2 <= y1:
        return None

    return [x1, y1, x2, y2]


def bbox_area(b: Optional[List[int]]) -> int:
    if not b:
        return 0
    return max(0, b[2] - b[0]) * max(0, b[3] - b[1])


def bbox_intersection(a: Optional[List[int]], b: Optional[List[int]]) -> Optional[List[int]]:
    if not a or not b:
        return None

    x1 = max(a[0], b[0])
    y1 = max(a[1], b[1])
    x2 = min(a[2], b[2])
    y2 = min(a[3], b[3])

    if x2 <= x1 or y2 <= y1:
        return None

    return [x1, y1, x2, y2]


def bbox_iou(a: Optional[List[int]], b: Optional[List[int]]) -> float:
    inter = bbox_intersection(a, b)
    if not inter:
        return 0.0

    inter_area = bbox_area(inter)
    union_area = bbox_area(a) + bbox_area(b) - inter_area
    if union_area <= 0:
        return 0.0

    return inter_area / union_area


def parse_question_no_from_text(text: str) -> Optional[int]:
    t = normalize_text_value(text)

    patterns = [
        re.compile(r"^\s*(\d{1,3})\s*[\.．、]\s*"),
        re.compile(r"^\s*(\d{1,3})\s*[\)\]）]\s*"),
    ]

    for p in patterns:
        m = p.match(t)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                return None

    return None


# =========================================================
# 腾讯云 OCR 客户端
# =========================================================
class TencentOCRClient:
    def __init__(self) -> None:
        if not TENCENT_SECRET_ID:
            raise ValueError("缺少环境变量 TENCENT_SECRET_ID")
        if not TENCENT_SECRET_KEY:
            raise ValueError("缺少环境变量 TENCENT_SECRET_KEY")

        self.secret_id = TENCENT_SECRET_ID
        self.secret_key = TENCENT_SECRET_KEY
        self.endpoint = TENCENT_ENDPOINT
        self.service = TENCENT_SERVICE
        self.version = TENCENT_VERSION
        self.region = TENCENT_REGION

    @staticmethod
    def _sign(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

    def _tc3_headers(self, action: str, payload: str) -> Dict[str, str]:
        timestamp = int(time.time())
        date = datetime.datetime.fromtimestamp(timestamp, datetime.UTC).strftime("%Y-%m-%d")

        canonical_headers = (
            f"content-type:application/json; charset=utf-8\n"
            f"host:{self.endpoint}\n"
            f"x-tc-action:{action.lower()}\n"
        )
        signed_headers = "content-type;host;x-tc-action"
        hashed_request_payload = hashlib.sha256(payload.encode("utf-8")).hexdigest()

        canonical_request = (
            "POST\n"
            "/\n"
            "\n"
            f"{canonical_headers}\n"
            f"{signed_headers}\n"
            f"{hashed_request_payload}"
        )

        algorithm = "TC3-HMAC-SHA256"
        credential_scope = f"{date}/{self.service}/tc3_request"
        hashed_canonical_request = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()

        string_to_sign = (
            f"{algorithm}\n"
            f"{timestamp}\n"
            f"{credential_scope}\n"
            f"{hashed_canonical_request}"
        )

        secret_date = self._sign(("TC3" + self.secret_key).encode("utf-8"), date)
        secret_service = self._sign(secret_date, self.service)
        secret_signing = self._sign(secret_service, "tc3_request")
        signature = hmac.new(
            secret_signing,
            string_to_sign.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        authorization = (
            f"{algorithm} "
            f"Credential={self.secret_id}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, "
            f"Signature={signature}"
        )

        return {
            "Authorization": authorization,
            "Content-Type": "application/json; charset=utf-8",
            "Host": self.endpoint,
            "X-TC-Action": action,
            "X-TC-Timestamp": str(timestamp),
            "X-TC-Version": self.version,
            "X-TC-Region": self.region,
        }

    def _post(self, action: str, body: Dict[str, Any]) -> Dict[str, Any]:
        payload = json.dumps(body, ensure_ascii=False)
        headers = self._tc3_headers(action, payload)

        resp = requests.post(
            f"https://{self.endpoint}",
            data=payload.encode("utf-8"),
            headers=headers,
            timeout=120,
        )
        resp.raise_for_status()

        data = resp.json()
        response = data.get("Response", {})
        if "Error" in response:
            raise RuntimeError(f"{action} 调用失败: {response['Error']}")

        return data

    def question_split_layout_ocr(self, image_path: str) -> Dict[str, Any]:
        body = {
            "ImageBase64": encode_image_to_base64(image_path),
            "UseNewModel": True,
        }
        return self._post("QuestionSplitLayoutOCR", body)

    def question_split_ocr(self, image_path: str) -> Dict[str, Any]:
        body = {
            "ImageBase64": encode_image_to_base64(image_path),
            "UseNewModel": True,
        }
        return self._post("QuestionSplitOCR", body)


# =========================================================
# 腾讯返回精确解析
# =========================================================
def coord4_to_bbox(coord: Dict[str, Any]) -> Optional[List[int]]:
    if not isinstance(coord, dict):
        return None

    points = []
    for key in ["LeftTop", "RightTop", "LeftBottom", "RightBottom"]:
        p = coord.get(key)
        if not isinstance(p, dict):
            continue
        if "X" in p and "Y" in p:
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


def extract_first_bbox_from_coord_field(coord_field: Any) -> Optional[List[int]]:
    if isinstance(coord_field, dict):
        return coord4_to_bbox(coord_field)

    if isinstance(coord_field, list):
        for item in coord_field:
            b = coord4_to_bbox(item)
            if b:
                return b

    return None


def extract_best_text_bbox(text_items: Any) -> Optional[List[int]]:
    if not isinstance(text_items, list) or not text_items:
        return None

    best_bbox = None
    best_area = -1

    for item in text_items:
        if not isinstance(item, dict):
            continue

        b = extract_first_bbox_from_coord_field(item.get("Coord"))
        if not b:
            continue

        area = bbox_area(b)
        if area > best_area:
            best_bbox = b
            best_area = area

    return best_bbox


def extract_question_no_from_question_item(question_items: Any) -> Optional[int]:
    if not isinstance(question_items, list):
        return None

    for item in question_items:
        if not isinstance(item, dict):
            continue

        text = normalize_text_value(item.get("Text"))
        qno = parse_question_no_from_text(text)
        if qno is not None:
            return qno

        idx = item.get("Index")
        if isinstance(idx, int):
            return idx

    return None


def normalize_layout_questions(
    resp: Dict[str, Any],
    image_width: int,
    image_height: int,
) -> List[dict]:
    response = resp.get("Response", {})
    question_info = response.get("QuestionInfo", [])
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

            outer_bbox = extract_first_bbox_from_coord_field(result.get("Coord"))
            outer_bbox = normalize_bbox(outer_bbox, image_width, image_height)
            if not outer_bbox:
                continue

            qno = None
            question_items = result.get("Question", [])
            if isinstance(question_items, list) and question_items:
                qno = extract_question_no_from_question_item(question_items)

            if qno is None:
                qno = running_qno

            items.append({
                "question_no": qno,
                "bbox": outer_bbox,
                "raw": result,
            })
            running_qno += 1

    return sorted(items, key=lambda x: x["question_no"])


def normalize_question_split_items(
    resp: Dict[str, Any],
    image_width: int,
    image_height: int,
) -> List[dict]:
    response = resp.get("Response", {})
    question_info = response.get("QuestionInfo", [])
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

            outer_bbox = extract_first_bbox_from_coord_field(result.get("Coord"))
            outer_bbox = normalize_bbox(outer_bbox, image_width, image_height)
            if not outer_bbox:
                continue

            question_items = result.get("Question", [])
            answer_items = result.get("Answer", [])
            parse_items = result.get("Parse", [])

            question_bbox = extract_best_text_bbox(question_items)
            question_bbox = normalize_bbox(question_bbox, image_width, image_height) if question_bbox else None

            answer_bbox = extract_best_text_bbox(answer_items)
            answer_bbox = normalize_bbox(answer_bbox, image_width, image_height) if answer_bbox else None

            parse_bbox = extract_best_text_bbox(parse_items)
            parse_bbox = normalize_bbox(parse_bbox, image_width, image_height) if parse_bbox else None

            qno = extract_question_no_from_question_item(question_items)
            if qno is None:
                qno = running_qno

            items.append({
                "question_no": qno,
                "outer_bbox": outer_bbox,
                "question_bbox": question_bbox,
                "answer_bbox": answer_bbox,
                "parse_bbox": parse_bbox,
                "raw": result,
            })

            running_qno += 1

    return sorted(items, key=lambda x: x["question_no"])


# =========================================================
# 对齐与融合
# =========================================================
def align_split_items_to_layout(layout_items: List[dict], split_items: List[dict]) -> Dict[int, dict]:
    result: Dict[int, dict] = {}
    split_by_qno = {
        item["question_no"]: item
        for item in split_items
        if item.get("question_no") is not None
    }

    for layout in layout_items:
        qno = layout["question_no"]
        matched = split_by_qno.get(qno)

        if matched is None:
            best = None
            best_iou = 0.0
            for s in split_items:
                iou = bbox_iou(layout["bbox"], s["outer_bbox"])
                if iou > best_iou:
                    best_iou = iou
                    best = s
            matched = best

        result[qno] = matched

    return result


def build_question_bbox(
    outer_bbox: List[int],
    split_item: Optional[dict],
) -> Optional[List[int]]:
    if not split_item:
        return None

    qbox = split_item.get("question_bbox")
    if not qbox:
        return None

    inter = bbox_intersection(qbox, outer_bbox)
    if not inter:
        return None

    return [outer_bbox[0], inter[1], outer_bbox[2], inter[3]]


def build_analysis_bbox(
    outer_bbox: List[int],
    split_item: Optional[dict],
    question_bbox: Optional[List[int]],
) -> Optional[List[int]]:
    if split_item:
        abox = split_item.get("answer_bbox")
        if abox:
            inter = bbox_intersection(abox, outer_bbox)
            if inter:
                return [outer_bbox[0], inter[1], outer_bbox[2], inter[3]]

        pbox = split_item.get("parse_bbox")
        if pbox:
            inter = bbox_intersection(pbox, outer_bbox)
            if inter:
                return [outer_bbox[0], inter[1], outer_bbox[2], inter[3]]

    if question_bbox:
        y1 = question_bbox[3]
        y2 = outer_bbox[3]
        if y2 > y1:
            return [outer_bbox[0], y1, outer_bbox[2], y2]

    return None


# =========================================================
# 主流程
# =========================================================
def main() -> None:
    if not os.path.exists(IMAGE_PATH):
        raise FileNotFoundError(f"找不到图片: {IMAGE_PATH}")

    ensure_dir(OUTPUT_DIR)

    image = Image.open(IMAGE_PATH).convert("RGB")
    image_width, image_height = image.size
    print(f"[INFO] 原图尺寸: {image_width} x {image_height}")

    tencent_client = TencentOCRClient()

    # ---------------------------------
    # 1) Layout：整题外框
    # ---------------------------------
    print("[INFO] 调用腾讯 QuestionSplitLayoutOCR ...")
    layout_resp = tencent_client.question_split_layout_ocr(IMAGE_PATH)
    with open(os.path.join(OUTPUT_DIR, "tencent_question_split_layout.json"), "w", encoding="utf-8") as f:
        json.dump(layout_resp, f, ensure_ascii=False, indent=2)

    layout_items = normalize_layout_questions(layout_resp, image_width, image_height)
    print(f"[INFO] LayoutOCR 识别题目数: {len(layout_items)}")

    if not layout_items:
        raise RuntimeError("QuestionSplitLayoutOCR 没有识别出任何题目")

    # ---------------------------------
    # 2) QuestionSplit：题目 / 解析精细结构
    # ---------------------------------
    print("[INFO] 调用腾讯 QuestionSplitOCR ...")
    split_resp = tencent_client.question_split_ocr(IMAGE_PATH)
    with open(os.path.join(OUTPUT_DIR, "tencent_question_split.json"), "w", encoding="utf-8") as f:
        json.dump(split_resp, f, ensure_ascii=False, indent=2)

    split_items = normalize_question_split_items(split_resp, image_width, image_height)
    print(f"[INFO] QuestionSplitOCR 识别题目数: {len(split_items)}")

    # ---------------------------------
    # 3) 对齐
    # ---------------------------------
    split_aligned = align_split_items_to_layout(layout_items, split_items)

    # ---------------------------------
    # 4) 融合与裁剪
    # ---------------------------------
    preview_boxes: List[Dict[str, Any]] = []
    final_records: List[dict] = []

    for layout in layout_items:
        qno = layout["question_no"]
        outer_bbox = layout["bbox"]
        split_item = split_aligned.get(qno)

        question_bbox = build_question_bbox(
            outer_bbox=outer_bbox,
            split_item=split_item,
        )
        question_bbox = normalize_bbox(question_bbox, image_width, image_height) if question_bbox else None

        if question_bbox is None:
            question_bbox = outer_bbox

        analysis_bbox = build_analysis_bbox(
            outer_bbox=outer_bbox,
            split_item=split_item,
            question_bbox=question_bbox,
        )
        analysis_bbox = normalize_bbox(analysis_bbox, image_width, image_height) if analysis_bbox else None

        if analysis_bbox and analysis_bbox[1] < question_bbox[3]:
            analysis_bbox[1] = question_bbox[3]
            analysis_bbox = normalize_bbox(analysis_bbox, image_width, image_height)

        q_save_path = os.path.join(OUTPUT_DIR, f"q{qno}_question.png")
        crop_and_save(image, question_bbox, q_save_path)

        preview_boxes.append({
            "bbox": outer_bbox,
            "label": f"Q{qno}-OUTER",
            "color": "green",
        })
        preview_boxes.append({
            "bbox": question_bbox,
            "label": f"Q{qno}-Q",
            "color": "red",
        })

        if analysis_bbox:
            a_save_path = os.path.join(OUTPUT_DIR, f"q{qno}_analysis.png")
            crop_and_save(image, analysis_bbox, a_save_path)
            preview_boxes.append({
                "bbox": analysis_bbox,
                "label": f"Q{qno}-A",
                "color": "blue",
            })

        record = {
            "question_no": qno,
            "outer_bbox": outer_bbox,
            "question_bbox": question_bbox,
            "analysis_bbox": analysis_bbox,
            "split_question_bbox": split_item.get("question_bbox") if split_item else None,
            "split_answer_bbox": split_item.get("answer_bbox") if split_item else None,
            "split_parse_bbox": split_item.get("parse_bbox") if split_item else None,
        }
        final_records.append(record)

        print(
            f"[Q{qno}] "
            f"OUTER={outer_bbox} ; "
            f"SPLIT_Q={split_item.get('question_bbox') if split_item else None} ; "
            f"SPLIT_A={split_item.get('answer_bbox') if split_item else None} ; "
            f"SPLIT_P={split_item.get('parse_bbox') if split_item else None} ; "
            f"FINAL_Q={question_bbox} ; "
            f"FINAL_A={analysis_bbox}"
        )

    with open(os.path.join(OUTPUT_DIR, "final_bboxes.json"), "w", encoding="utf-8") as f:
        json.dump(final_records, f, ensure_ascii=False, indent=2)

    preview_path = os.path.join(OUTPUT_DIR, "preview_boxes.png")
    draw_boxes_preview(image, preview_boxes, preview_path)

    print(f"\n[OK] 裁剪完成，输出目录: {OUTPUT_DIR}")
    print(f"[OK] 预览图: {preview_path}")


if __name__ == "__main__":
    main()
