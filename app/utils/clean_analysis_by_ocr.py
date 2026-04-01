
"""
=========================================================
功能：解析图片清洗（删除印刷题目信息）
=========================================================

【核心用途】
对“单题解析图片”进行清洗：
👉 删除其中残留的印刷题目信息（如“二、计算题”）
👉 保留手写解析内容（蓝/红笔迹）

【核心特点】
⚠️ 不假设题目信息位置（顶部/中部/底部都能处理）
⚠️ 基于 OCR + 文本语义判断，而不是固定位置裁剪

【处理流程】
1. 调用腾讯 OCR，获取整图文本 + 坐标
2. 判断哪些是“题目信息”（仅限标题类）：
   - 一、二、三……
   - 计算题 / 填空题 / 选择题 等
   - 每题X分 / 共X分
3. 定位这些文本区域
4. 直接对白化删除（不依赖位置）
5. 删除蓝色章节横线（图像规则）
6. 保留蓝/红解析区域（颜色保护）

【输入】
- image_path: str
    单张解析图片路径

【输出】
- output_path: str
    清洗后的解析图片（默认 *_clean.png）

【可选参数】
- debug: 是否打印删除日志
- remove_blue_lines: 是否删除蓝色标题横线
- crop_outer_whitespace: 是否裁剪外部白边

【提供函数】
- clean_analysis_image()   → 单张处理
- clean_analysis_folder()  → 批量处理

【适用场景】
- 解析图片清洗（核心）
- AI训练数据预处理
- 去除题目干扰信息

【设计原则】
✔ 只删除“标题类信息”，不删除题干
✔ 不依赖位置，只依赖 OCR 语义
✔ 优先保护手写解析

=========================================================
"""

import os
import re
import json
import base64
from typing import Optional, Tuple, List

import cv2
import numpy as np

from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.ocr.v20181119 import ocr_client, models


# =========================================================
# 腾讯云 OCR 配置
# 你需要把下面两个值改成你自己的真实密钥
# =========================================================
from app.config import settings

SECRET_ID = settings.tencent_secret_id
SECRET_KEY = settings.tencent_secret_key
REGION = settings.tencent_region


# =========================================================
# OCR 基础
# =========================================================
def _validate_ascii_config() -> None:
    fields = {
        "SECRET_ID": SECRET_ID,
        "SECRET_KEY": SECRET_KEY,
        "REGION": REGION,
    }
    for name, value in fields.items():
        if not isinstance(value, str):
            raise TypeError(f"{name} 必须是字符串")
        try:
            value.encode("ascii")
        except UnicodeEncodeError:
            raise ValueError(
                f"{name} 包含非 ASCII 字符，请检查是否还保留了中文占位符: {value!r}"
            )


def _build_ocr_client():
    _validate_ascii_config()

    cred = credential.Credential(SECRET_ID, SECRET_KEY)

    http_profile = HttpProfile()
    http_profile.endpoint = "ocr.tencentcloudapi.com"

    client_profile = ClientProfile()
    client_profile.httpProfile = http_profile

    return ocr_client.OcrClient(cred, REGION, client_profile)


def _image_to_base64(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _call_ocr(image_path: str) -> dict:
    client = _build_ocr_client()
    img_base64 = _image_to_base64(image_path)

    req = models.GeneralAccurateOCRRequest()
    params = {
        "ImageBase64": img_base64,
        "LanguageType": "zh",
        "IsPdf": False,
        "IsWords": False
    }
    req.from_json_string(json.dumps(params))

    resp = client.GeneralAccurateOCR(req)
    return json.loads(resp.to_json_string())


def _get_text_detections(result: dict) -> List[dict]:
    if "TextDetections" in result:
        return result["TextDetections"]
    if "Response" in result and "TextDetections" in result["Response"]:
        return result["Response"]["TextDetections"]
    return []


def _extract_box(det: dict) -> Tuple[int, int, int, int]:
    poly = det.get("ItemPolygon", {})
    x = int(poly.get("X", 0))
    y = int(poly.get("Y", 0))
    w = int(poly.get("Width", 0))
    h = int(poly.get("Height", 0))
    return x, y, w, h


def _normalize_text(text: str) -> str:
    return text.strip().replace(" ", "")


# =========================================================
# 题目信息判断
# 目标：找出“应删除的印刷内容”
# 注意：不预设题目信息出现在顶部/底部/中部
# =========================================================
def _is_question_like_text(text: str) -> bool:
    t = _normalize_text(text)

    if not t:
        return False

    # 章节标题：一、二、三……
    if re.match(r"^[一二三四五六七八九十]+、", t):
        return True

    # 题型标题关键词
    if any(k in t for k in ["计算题", "填空题", "选择题", "判断题", "应用题", "解答题"]):
        return True

    # 分值说明
    if "每题" in t or ("共" in t and "分" in t):
        return True

    return False


# =========================================================
# 解析保护区
# 蓝/红笔迹默认视为解析主体，尽量保护
# =========================================================
def _get_analysis_mask(image: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

    # 蓝色
    lower_blue = np.array([100, 43, 46])
    upper_blue = np.array([124, 255, 255])
    blue = cv2.inRange(hsv, lower_blue, upper_blue)

    # 红色
    lower_red1 = np.array([0, 43, 46])
    upper_red1 = np.array([10, 255, 255])
    lower_red2 = np.array([156, 43, 46])
    upper_red2 = np.array([180, 255, 255])

    red = cv2.bitwise_or(
        cv2.inRange(hsv, lower_red1, upper_red1),
        cv2.inRange(hsv, lower_red2, upper_red2)
    )

    mask = cv2.bitwise_or(blue, red)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    mask = cv2.dilate(mask, kernel, iterations=1)
    return mask


def _safe_whiteout(
    image: np.ndarray,
    analysis_mask: np.ndarray,
    box: Tuple[int, int, int, int],
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


def _remove_blue_rule_lines(
    image: np.ndarray,
    min_width_ratio: float = 0.45,
    max_height: int = 14,
    blue_ratio_threshold: float = 0.45,
) -> None:
    """
    删除章节标题下面那种细长蓝线。
    只删“细、长、横向”的蓝色区域，尽量不碰手写图示。
    """
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


def _crop_outer_whitespace(image: np.ndarray, margin: int = 8) -> np.ndarray:
    """
    去掉最外层大块纯白边，但不做激进裁切。
    """
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


# =========================================================
# 主功能：处理单张解析图
# =========================================================
def clean_analysis_image(
    image_path: str,
    output_path: Optional[str] = None,
    debug: bool = False,
    save_debug_ocr_json: bool = False,
    remove_blue_lines: bool = True,
    crop_outer_whitespace: bool = False,
    overlap_threshold: int = 30,
) -> str:
    """
    对单张“解析图片”做处理：
    - OCR 整图
    - 定位印刷题目信息
    - 局部白化删除
    - 保留蓝/红解析

    参数
    ----
    image_path : 输入解析图片路径
    output_path : 输出路径；若为 None，则自动生成 *_clean.png
    debug : 是否打印删除日志
    save_debug_ocr_json : 是否保存 OCR 原始结果 json
    remove_blue_lines : 是否删除细长蓝色标题横线
    crop_outer_whitespace : 是否最后裁掉最外层白边
    overlap_threshold : OCR 框与解析保护区的重叠阈值，越大越保守

    返回
    ----
    output_path : 处理后图片路径
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"找不到图片: {image_path}")

    image = cv2.imread(image_path)
    if image is None:
        raise ValueError(f"无法读取图片: {image_path}")

    if output_path is None:
        root, _ = os.path.splitext(image_path)
        output_path = f"{root}_clean.png"

    ocr_result = _call_ocr(image_path)
    text_detections = _get_text_detections(ocr_result)

    if save_debug_ocr_json:
        json_path = os.path.splitext(output_path)[0] + "_ocr.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(ocr_result, f, ensure_ascii=False, indent=2)

    analysis_mask = _get_analysis_mask(image)
    cleaned = image.copy()

    removed_count = 0

    for det in text_detections:
        text = det.get("DetectedText", "")
        box = _extract_box(det)

        x, y, w, h = box
        if w <= 0 or h <= 0:
            continue

        if not _is_question_like_text(text):
            continue

        t = _normalize_text(text)

        # 章节/题型标题：直接删，不做蓝红保护
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
            removed_count += 1
            if debug:
                print(f"直接删除章节标题: {text}")
            continue

        # 普通题目文字：仍然用保护逻辑
        deleted = _safe_whiteout(
            cleaned,
            analysis_mask,
            box,
            overlap_threshold=overlap_threshold,
            expand_x=6,
            expand_y=6,
        )

        if deleted:
            removed_count += 1
            if debug:
                print(f"删除题目信息: {text}")
        else:
            if debug:
                print(f"保留（与解析重叠）: {text}")

    if remove_blue_lines:
        _remove_blue_rule_lines(cleaned)

    if crop_outer_whitespace:
        cleaned = _crop_outer_whitespace(cleaned)

    cv2.imwrite(output_path, cleaned)

    if debug:
        print(f"OCR 文本框数量: {len(text_detections)}")
        print(f"删除框数量: {removed_count}")
        print(f"输出路径: {output_path}")

    return output_path


# =========================================================
# 批量处理文件夹
# =========================================================
def clean_analysis_folder(
    input_dir: str,
    output_dir: str,
    debug: bool = False,
    save_debug_ocr_json: bool = False,
    remove_blue_lines: bool = True,
    crop_outer_whitespace: bool = False,
    overlap_threshold: int = 30,
) -> List[str]:
    """
    批量处理一个文件夹下的解析图。
    支持 png/jpg/jpeg/webp/bmp
    """
    if not os.path.isdir(input_dir):
        raise NotADirectoryError(f"输入文件夹不存在: {input_dir}")

    os.makedirs(output_dir, exist_ok=True)

    exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
    outputs = []

    for name in sorted(os.listdir(input_dir)):
        ext = os.path.splitext(name)[1].lower()
        if ext not in exts:
            continue

        in_path = os.path.join(input_dir, name)
        out_path = os.path.join(output_dir, os.path.splitext(name)[0] + "_clean.png")

        result_path = clean_analysis_image(
            image_path=in_path,
            output_path=out_path,
            debug=debug,
            save_debug_ocr_json=save_debug_ocr_json,
            remove_blue_lines=remove_blue_lines,
            crop_outer_whitespace=crop_outer_whitespace,
            overlap_threshold=overlap_threshold,
        )
        outputs.append(result_path)

    return outputs


# =========================================================
# 命令行调用示例
# =========================================================
# if __name__ == "__main__":
#     # 单张图片示例
#     clean_analysis_image(
#         image_path="analysis_results/question_4_analysis.png",
#         output_path="analysis_results/analysis_example_clean.png",
#         debug=True,
#         save_debug_ocr_json=False,
#         remove_blue_lines=True,
#         crop_outer_whitespace=False,
#         overlap_threshold=30,
#     )

    # 批量处理示例（需要时取消注释）
    # clean_analysis_folder(
    #     input_dir="analysis_results",
    #     output_dir="analysis_results_clean",
    #     debug=True,
    #     save_debug_ocr_json=False,
    #     remove_blue_lines=True,
    #     crop_outer_whitespace=False,
    #     overlap_threshold=30,
    # )
