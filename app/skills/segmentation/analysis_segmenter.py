from __future__ import annotations

import os
import shutil

import cv2
import numpy as np

from app.skills.segmentation.segmentation_models import SegmentationOutput


class AnalysisSegmenter:
    @staticmethod
    def _merge_text_lines_to_question_blocks(rects, y_gap_threshold=120):
        if not rects:
            return []

        rects = sorted(rects, key=lambda r: r[1])

        merged = []
        cur_x, cur_y, cur_w, cur_h = rects[0]

        for x, y, w, h in rects[1:]:
            cur_bottom = cur_y + cur_h

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

    def segment_page(
        self,
        image_path: str,
        output_dir: str,
        debug_output_name: str = "debug_lines.png",
    ) -> SegmentationOutput:
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)
        os.makedirs(output_dir, exist_ok=True)

        src_img = cv2.imread(image_path)
        if src_img is None:
            return SegmentationOutput(
                success=False,
                message=f"找不到图片: {image_path}",
            )

        h, w, _ = src_img.shape
        hsv = cv2.cvtColor(src_img, cv2.COLOR_BGR2HSV)

        lower_black = np.array([0, 0, 0])
        upper_black = np.array([180, 255, 110])
        black_mask = cv2.inRange(hsv, lower_black, upper_black)

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (50, 5))
        black_dilated = cv2.dilate(black_mask, kernel, iterations=1)

        contours, _ = cv2.findContours(
            black_dilated,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE,
        )

        line_rects = []
        for cnt in contours:
            x, y, bw, bh = cv2.boundingRect(cnt)

            left_margin_ratio = x / w
            width_ratio = bw / w

            if width_ratio > 0.1 and left_margin_ratio < 0.20:
                line_rects.append((x, y, bw, bh))

        line_rects = sorted(line_rects, key=lambda r: r[1])

        if not line_rects:
            return SegmentationOutput(
                success=False,
                message="没有检测到题干文本行",
                output_dir=output_dir,
            )

        question_blocks = self._merge_text_lines_to_question_blocks(
            line_rects,
            y_gap_threshold=120,
        )

        final_centers = []
        for x, y, bw, bh in question_blocks:
            yc = y + bh // 2
            final_centers.append(yc)

        # debug_img = src_img.copy()
        # for idx, yc in enumerate(final_centers, start=1):
        #     cv2.line(debug_img, (0, yc), (w - 1, yc), (0, 0, 255), 2)
        #     cv2.putText(
        #         debug_img,
        #         str(idx),
        #         (10, max(30, yc - 10)),
        #         cv2.FONT_HERSHEY_SIMPLEX,
        #         1.0,
        #         (0, 0, 255),
        #         2,
        #     )

        # debug_path = os.path.join(output_dir, debug_output_name)
        # cv2.imwrite(debug_path, debug_img)

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

        blue_mask = cv2.bitwise_or(blue_only_mask, red_mask)
        white_bg = np.full(src_img.shape, 255, dtype=np.uint8)

        saved_files = []
        question_num = 1

        for i in range(len(final_centers)):
            y_start = final_centers[i]

            if i < len(final_centers) - 1:
                y_end = final_centers[i + 1]
            else:
                y_end = h

            roi_blue = blue_mask[y_start:y_end, :]
            roi_src = src_img[y_start:y_end, :]
            roi_white = white_bg[y_start:y_end, :]

            blue_part = cv2.bitwise_and(roi_src, roi_src, mask=roi_blue)
            white_part = cv2.bitwise_and(
                roi_white,
                roi_white,
                mask=cv2.bitwise_not(roi_blue),
            )
            result_roi = cv2.bitwise_or(blue_part, white_part)

            if cv2.countNonZero(roi_blue) > 100:
                save_name = os.path.join(
                    output_dir,
                    f"question_{question_num}_analysis.png",
                )
                cv2.imwrite(save_name, result_roi)
                saved_files.append(save_name)

            question_num += 1

        return SegmentationOutput(
            success=True,
            message=f"解析切割完成，共生成 {len(saved_files)} 张解析图片",
            output_dir=output_dir,
            files=saved_files,
            debug_files=[],
            metadata={
                "analysis_count": len(saved_files),
                "centers": final_centers,
            },
        )