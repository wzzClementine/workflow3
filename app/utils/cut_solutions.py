
"""
=========================================================
功能：解析区域提取（整页解析 → 单题解析图片）
=========================================================

【核心用途】
从“带手写解析的整页图片”中，提取每道题对应的解析区域。

【处理流程】
1. 提取黑色印刷文本（题干）
2. 按行检测文本区域（题目行）
3. 合并为“题块”（解决多行题目问题）
4. 根据题块中心线划分区域
5. 提取蓝色 + 红色笔迹（解析）
6. 生成每题对应解析图

【输入】
- image_path: str
    输入整页解析图片

【输出】
- output_dir/
    question_1_analysis.png
    question_2_analysis.png
    ...
    debug_lines.png（调试用）

【适用场景】
- 教辅解析提取
- 手写解题过程提取
- AI训练数据生成

【特点】
- 自动识别题目结构
- 支持多行题干
- 只保留蓝/红手写解析
- 自动过滤印刷背景

=========================================================
"""

import shutil
import cv2
import numpy as np
import os


def merge_text_lines_to_question_blocks(rects, y_gap_threshold=120):
    """
    将相邻的黑色文本行矩形，按纵向距离合并成“题块”。
    rects: [(x, y, w, h), ...]，已经按 y 排序
    返回: merged_blocks = [(x, y, w, h), ...]
    """
    if not rects:
        return []

    rects = sorted(rects, key=lambda r: r[1])

    merged = []
    cur_x, cur_y, cur_w, cur_h = rects[0]

    for x, y, w, h in rects[1:]:
        cur_bottom = cur_y + cur_h

        # 如果下一行和当前块足够近，就合并
        if y - cur_bottom <= y_gap_threshold:
            new_x1 = min(cur_x, x)
            new_y1 = min(cur_y, y)
            new_x2 = max(cur_x + cur_w, x + w)
            new_y2 = max(cur_y + cur_h, y + h)

            cur_x = new_x1
            cur_y = new_y1
            cur_w = new_x2 - new_x1
            cur_h = new_y2 - new_y1
        else:
            merged.append((cur_x, cur_y, cur_w, cur_h))
            cur_x, cur_y, cur_w, cur_h = x, y, w, h

    merged.append((cur_x, cur_y, cur_w, cur_h))
    return merged


def extract_analysis_by_question_blocks(
    image_path,
    output_dir="analysis_results",
    debug_output_name="debug_lines.png"
):
    # 如果文件夹存在，先删除
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)

    # 再重新创建
    os.makedirs(output_dir)

    src_img = cv2.imread(image_path)
    if src_img is None:
        print(f"❌ 找不到图片: {image_path}")
        return

    h, w, _ = src_img.shape
    hsv = cv2.cvtColor(src_img, cv2.COLOR_BGR2HSV)

    # =========================================================
    # 1. 提取黑色印刷内容
    # =========================================================
    lower_black = np.array([0, 0, 0])
    upper_black = np.array([180, 255, 110])
    black_mask = cv2.inRange(hsv, lower_black, upper_black)

    # 横向膨胀，把每一行题干尽量连起来
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (50, 5))
    black_dilated = cv2.dilate(black_mask, kernel, iterations=1)

    contours, _ = cv2.findContours(
        black_dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    # =========================================================
    # 2. 先找“黑色长文本行”
    # =========================================================
    line_rects = []
    for cnt in contours:
        x, y, bw, bh = cv2.boundingRect(cnt)

        # 只保留更像“题目行”的黑色文本行
        left_margin_ratio = x / w
        width_ratio = bw / w

        # 题目行：通常从左边开始，并且宽度足够长
        # 标题：通常更居中，左边距较大
        if width_ratio > 0.1 and left_margin_ratio < 0.20:
            line_rects.append((x, y, bw, bh))

    line_rects = sorted(line_rects, key=lambda r: r[1])

    if not line_rects:
        print("❌ 没有检测到题干文本行")
        return

    # =========================================================
    # 3. 把同一道题的多行文本合并成一个题块
    #    这是解决 7 条线问题的关键
    # =========================================================
    question_blocks = merge_text_lines_to_question_blocks(
        line_rects,
        y_gap_threshold=120
    )

    # =========================================================
    # 4. 每个题块取一个横向中心线
    # =========================================================
    final_centers = []
    for x, y, bw, bh in question_blocks:
        yc = y + bh // 2
        final_centers.append(yc)

    print("检测到的题块中心线：", final_centers)

    # =========================================================
    # 5. 输出调试画线图
    # =========================================================
    debug_img = src_img.copy()

    for idx, yc in enumerate(final_centers, start=1):
        cv2.line(debug_img, (0, yc), (w - 1, yc), (0, 0, 255), 2)
        cv2.putText(
            debug_img,
            str(idx),
            (10, max(30, yc - 10)),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (0, 0, 255),
            2
        )

    debug_path = os.path.join(output_dir, debug_output_name)
    cv2.imwrite(debug_path, debug_img)
    print(f"🖼️ 调试画线图已保存: {debug_path}")

    # =========================================================
    # 6. 提取蓝色解析 + 红色解析
    # =========================================================
    lower_blue = np.array([100, 43, 46])
    upper_blue = np.array([124, 255, 255])
    blue_only_mask = cv2.inRange(hsv, lower_blue, upper_blue)

    lower_red1 = np.array([0, 43, 46])
    upper_red1 = np.array([10, 255, 255])
    lower_red2 = np.array([156, 43, 46])
    upper_red2 = np.array([180, 255, 255])

    red_mask1 = cv2.inRange(hsv, lower_red1, upper_red1)
    red_mask2 = cv2.inRange(hsv, lower_red2, upper_red2)
    red_mask = cv2.bitwise_or(red_mask1, red_mask2)

    # 保持后续代码不变，直接复用 blue_mask 变量名
    blue_mask = cv2.bitwise_or(blue_only_mask, red_mask)

    white_bg = np.full(src_img.shape, 255, dtype=np.uint8)

    # =========================================================
    # 7. 按“当前中心线 -> 下一中心线 -> 最后一题到页底”切割
    # =========================================================
    question_num = 1

    for i in range(len(final_centers)):
        y_start = final_centers[i]

        if i < len(final_centers) - 1:
            y_end = final_centers[i + 1]
        else:
            y_end = h  # 最后一题切到页底

        roi_blue = blue_mask[y_start:y_end, :]
        roi_src = src_img[y_start:y_end, :]
        roi_white = white_bg[y_start:y_end, :]

        # 只保留蓝色和红色
        blue_part = cv2.bitwise_and(roi_src, roi_src, mask=roi_blue)
        white_part = cv2.bitwise_and(
            roi_white, roi_white, mask=cv2.bitwise_not(roi_blue)
        )
        result_roi = cv2.bitwise_or(blue_part, white_part)

        # 有蓝色或红色就保存
        if cv2.countNonZero(roi_blue) > 100:
            save_name = os.path.join(
                output_dir, f"question_{question_num}_analysis.png"
            )
            cv2.imwrite(save_name, result_roi)
            print(f"✅ 成功生成第 {question_num} 题解析: {save_name}")

        question_num += 1


# if __name__ == "__main__":
#     extract_analysis_by_question_blocks(
#         image_path="output_images/solutions_raw/page_3.png",
#         output_dir="analysis_results",
#         debug_output_name="debug_lines.png"
#     )