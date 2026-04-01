
"""
=========================================================
功能：基于腾讯 OCR 的题目切割（整页 → 单题图片）
=========================================================

【核心用途】
将整页试卷图片按“题号”自动切割成单独题目图片。

【处理流程】
1. 使用腾讯 OCR 获取文本及位置（带 bounding box）
2. 自动识别题号（如 1. / 2、 / 13.）
3. 结合投影方法补漏（防止 OCR 漏检）
4. 自动识别并过滤章节标题（如“二、计算题”）
5. 计算有效左右边界（避免只截到一半）
6. 按题号区域裁剪并保存

【输入】
- image_path: str
    输入整页试卷图片路径（PNG/JPG）

【输出】
- output_dir/
    question_1.png
    question_2.png
    ...
    ocr_result.json（调试用）

【适用场景】
- 试卷题目自动拆分
- 题库构建
- OCR结构化前处理

【特点】
- 支持中文题号（1. / 1、）
- 自动处理跨行题目
- 自动跳过“计算题/填空题”等章节标题
- 对复杂页面有较强鲁棒性

=========================================================
"""

import os
import re
import json
import base64
import shutil
import cv2
import numpy as np

from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.ocr.v20181119 import ocr_client, models

# =========================================================
# 1. 腾讯云 OCR 配置
# =========================================================
from app.config import settings

SECRET_ID = settings.tencent_secret_id
SECRET_KEY = settings.tencent_secret_key
REGION = settings.tencent_region

# SECRET_ID = "AKIDXyKWTH3kGcmoh6HKEvNiRaYKuSM4gEk9"
# SECRET_KEY = "KcmjSxDF2bvEJ9l8HBrJWUElPp0wc5LM"
# REGION = "ap-beijing"
# =========================================================
# OCR 客户端
# =========================================================
def build_ocr_client():
    cred = credential.Credential(SECRET_ID, SECRET_KEY)
    http_profile = HttpProfile()
    http_profile.endpoint = "ocr.tencentcloudapi.com"
    client_profile = ClientProfile()
    client_profile.httpProfile = http_profile
    return ocr_client.OcrClient(cred, REGION, client_profile)

def image_to_base64(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def call_general_accurate_ocr(client, image_base64: str) -> dict:
    req = models.GeneralAccurateOCRRequest()
    params = {
        "ImageBase64": image_base64,
        "LanguageType": "zh",
        "IsPdf": False,
        "IsWords": False
    }
    req.from_json_string(json.dumps(params))
    resp = client.GeneralAccurateOCR(req)
    return json.loads(resp.to_json_string())

def get_text_detections(result: dict):
    if "TextDetections" in result:
        return result["TextDetections"]
    if "Response" in result and "TextDetections" in result["Response"]:
        return result["Response"]["TextDetections"]
    return []

def get_request_id(result: dict):
    if "RequestId" in result:
        return result["RequestId"]
    if "Response" in result and "RequestId" in result["Response"]:
        return result["Response"]["RequestId"]
    return ""

# =========================================================
# 基础工具
# =========================================================
def normalize_text(text: str) -> str:
    return text.strip().replace(" ", "")

def extract_box(det: dict):
    poly = det.get("ItemPolygon", {})
    x = int(poly.get("X", 0))
    y = int(poly.get("Y", 0))
    w = int(poly.get("Width", 0))
    h = int(poly.get("Height", 0))
    return x, y, w, h

# =========================================================
# 题号识别
# =========================================================
def extract_question_number(text: str):
    t = normalize_text(text)
    m = re.match(r"^(\d{1,2})[\.、．]", t)
    if m:
        return int(m.group(1))
    return None

def is_question_start(text: str) -> bool:
    t = normalize_text(text)
    return re.match(r"^\d{1,2}[\.、．]", t) is not None

def find_question_starts(text_detections, x_threshold=400, small_box_width=120, min_question_gap=160):
    question_starts = []
    for det in text_detections:
        text = det.get("DetectedText", "").strip()
        x, y, w, h = extract_box(det)
        t = normalize_text(text)

        cond_full_line = re.match(r"^\d{1,2}[\.、．]", t) is not None and x < x_threshold
        cond_small_number = re.match(r"^\d{1,2}[\.、．]$", t) is not None and x < x_threshold and w < small_box_width

        if cond_full_line or cond_small_number:
            question_starts.append({
                "num": extract_question_number(text),
                "text": text,
                "x": x,
                "y": y,
                "w": w,
                "h": h,
                "source": "ocr"
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

# =========================================================
# 投影补漏
# =========================================================
def find_text_bands_in_region(image, y1, y2, x1=0, x2=None,
                              min_band_height=25, merge_gap=120, pixel_threshold=30):
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

def refine_large_gaps_with_projection(image, starts, large_gap_threshold=700):
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
        bands = find_text_bands_in_region(image, y1=cur["y"] + 40, y2=nxt["y"] - 20, x1=0, x2=image.shape[1])
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
                "source": "projection"
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

# =========================================================
# OCR标题过滤
# =========================================================
def is_section_header_text(text: str) -> bool:
    t = normalize_text(text)
    if re.match(r"^[一二三四五六七八九十]+、", t):
        return True
    keywords = ["计算题", "填空题", "选择题", "判断题", "应用题", "解答题"]
    if any(k in t for k in keywords):
        return True
    if "每题" in t and "分" in t:
        return True
    return False

def collect_section_header_boxes(text_detections):
    header_boxes = []
    for det in text_detections:
        text = det.get("DetectedText", "").strip()
        if is_section_header_text(text):
            x, y, w, h = extract_box(det)
            header_boxes.append({"text": text, "x": x, "y": y, "w": w, "h": h})
    return header_boxes

def filter_starts_by_header_boxes(starts, header_boxes, y_tol=100):
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

def find_next_header_y_between(header_boxes, y_start, y_next):
    candidates = []
    for hb in header_boxes:
        if y_start < hb["y"] < y_next:
            candidates.append(hb["y"])
    if not candidates:
        return None
    return min(candidates)

# =========================================================
# 公式页裁剪
# =========================================================
def is_formula_heavy_page(text_detections):
    math_like = 0
    chinese_like = 0
    for det in text_detections:
        t = det.get("DetectedText", "")
        if re.search(r"[+\-×÷=()/]", t) or re.search(r"\d\s*/\s*\d", t):
            math_like += 1
        if re.search(r"[\u4e00-\u9fff]", t):
            chinese_like += 1
    return math_like >= 5 and math_like > chinese_like

def get_crop_left_right(text_detections, min_y, img_w):
    if is_formula_heavy_page(text_detections):
        return 0, img_w

    # 以下相当于 compute_crop_left_right 的逻辑
    xs = []
    xe = []

    for det in text_detections:
        x, y, w, h = extract_box(det)
        if y >= min_y and w > 0 and h > 0:
            xs.append(x)
            xe.append(x + w)

    if not xs:
        left, right = 0, img_w
    else:
        left = max(0, min(xs) - 20)
        right = min(img_w, max(xe) + 20)

    # 宽度太窄兜底全宽
    if right - left < img_w * 0.6:
        left, right = 0, img_w

    return left, right

# =========================================================
# 主流程
# =========================================================
def cut_questions_by_tencent_ocr(image_path: str, output_dir: str = "question_results",
                                 top_pad: int = 20, bottom_pad: int = 20,
                                 left_pad: int = 0, right_pad: int = 0):

    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir)

    image = cv2.imread(image_path)
    if image is None:
        raise FileNotFoundError(f"找不到图片: {image_path}")
    img_h, img_w = image.shape[:2]

    client = build_ocr_client()
    image_base64 = image_to_base64(image_path)
    ocr_result = call_general_accurate_ocr(client, image_base64)

    with open(os.path.join(output_dir, "ocr_result.json"), "w", encoding="utf-8") as f:
        json.dump(ocr_result, f, ensure_ascii=False, indent=2)

    text_detections = get_text_detections(ocr_result)
    request_id = get_request_id(ocr_result)
    print(f"RequestId: {request_id}")
    print(f"TextDetections: {len(text_detections)}")
    if not text_detections:
        raise RuntimeError("OCR没有返回任何文本结果。")

    starts = find_question_starts(text_detections)
    starts = [q for q in starts if not is_section_header_text(q["text"])]

    header_boxes = collect_section_header_boxes(text_detections)
    print("\n识别到的章节标题 OCR 框：")
    for hb in header_boxes:
        print(f"text={hb['text']}, y={hb['y']}")

    starts = refine_large_gaps_with_projection(image, starts, large_gap_threshold=700)
    starts = filter_starts_by_header_boxes(starts, header_boxes, y_tol=100)

    print("\n最终切分起点：")
    for q in starts:
        print(f"source={q['source']}, y={q['y']}, text={q['text']}")

    body_left, body_right = get_crop_left_right(text_detections, min_y=starts[0]["y"], img_w=img_w)

    for i in range(len(starts)):
        y_start = max(0, starts[i]["y"] - top_pad)
        if i < len(starts) - 1:
            next_start_y = starts[i + 1]["y"]
            y_end = max(y_start + 20, next_start_y - bottom_pad)
            next_header_y = find_next_header_y_between(header_boxes, starts[i]["y"], next_start_y)
            if next_header_y is not None:
                y_end = min(y_end, max(y_start + 20, next_header_y - bottom_pad))
        else:
            y_end = img_h - 10
        crop = image[y_start:y_end, body_left:body_right]
        save_path = os.path.join(output_dir, f"question_{i + 1}.png")
        cv2.imwrite(save_path, crop)
        print(f"✅ 已保存第 {i + 1} 题: {save_path}")

# =========================================================
# 主程序入口
# =========================================================
# if __name__ == "__main__":
#     cut_questions_by_tencent_ocr(
#         image_path="../../runtime_data/papers/task_20260401_113134_ba1c/blank_pages/page_004.png",   # 改成你的图片路径
#         output_dir="question_results",
#         top_pad=30,
#         bottom_pad=20,
#         left_pad=0,
#         right_pad=0
#     )