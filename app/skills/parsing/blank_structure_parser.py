from __future__ import annotations

import os
import re
from dataclasses import dataclass, asdict
from typing import Any, Optional

from app.infrastructure.ocr.xfyun_llm_ocr import OCRForLLMClient


@dataclass
class TextLine:
    text: str
    x: int
    y: int
    w: int
    h: int

    @property
    def x2(self) -> int:
        return self.x + self.w

    @property
    def y2(self) -> int:
        return self.y + self.h


@dataclass
class SectionContext:
    question_type: Optional[str] = None
    default_score: Optional[int] = None
    section_title: Optional[str] = None


@dataclass
class QuestionInfo:
    page_index: int
    question_no: int
    question_type: Optional[str]
    score: Optional[int]
    section_title: Optional[str]
    question_text: str
    line_y: int


class BlankStructureParser:
    """
    空白卷结构解析器

    作用：
    1. 对空白卷整页图片执行普通印刷体 OCR
    2. 解析大题标题（如：一、计算题（每题4分，共24分））
    3. 解析每道小题题号
    4. 自动继承跨页题型 / 默认分数上下文
    5. 输出题号、题型、分数、题目文本等结构信息

    返回格式：
    [
        {
            "page_index": 1,
            "question_no": 1,
            "question_type": "计算题",
            "score": 4,
            "section_title": "一、计算题（每题4分，共24分）",
            "question_text": "...",
            "line_y": 123
        },
        ...
    ]
    """

    QUESTION_TYPE_KEYWORDS = [
        "计算题",
        "填空题",
        "选择题",
        "判断题",
        "应用题",
        "解答题",
        "解决问题",
        "操作题",
    ]

    SECTION_TITLE_PREFIX_RE = re.compile(r"^\s*[一二三四五六七八九十]+、")
    QUESTION_NO_RE = re.compile(r"^\s*(\d{1,3})\s*[\.．、]")
    PER_QUESTION_SCORE_RE = re.compile(r"每题\s*(\d+)\s*分")
    INLINE_SCORE_RE = re.compile(r"[（(]\s*(\d+)\s*分\s*[）)]")

    def __init__(self, ocr_client: Any | None = None):
        self.ocr_client = ocr_client or OCRForLLMClient()

    def parse_pages(
        self,
        blank_pages_dir: str,
        inherited_context: SectionContext | None = None,
    ) -> list[dict]:
        if not os.path.isdir(blank_pages_dir):
            raise FileNotFoundError(f"找不到目录: {blank_pages_dir}")

        image_paths = self._list_page_images(blank_pages_dir)
        if not image_paths:
            raise RuntimeError(f"目录中没有图片: {blank_pages_dir}")

        all_questions: list[QuestionInfo] = []
        context = inherited_context or SectionContext()

        for idx, image_path in enumerate(image_paths, start=1):
            page_index = self._parse_page_index(image_path, idx)
            print(f"[BlankStructureParser] 处理空白卷 page={page_index}: {image_path}")

            ocr_result = self.ocr_client.general_ocr(image_path)
            detections = self.ocr_client.get_text_detections(ocr_result)
            textlines = self._detections_to_textlines(detections)

            page_questions, context = self._parse_page_questions(
                page_index=page_index,
                textlines=textlines,
                inherited_context=context,
            )

            print(
                f"[BlankStructureParser] page={page_index} "
                f"textlines={len(textlines)} "
                f"questions={len(page_questions)} "
                f"context=({context.question_type}, {context.default_score})"
            )

            all_questions.extend(page_questions)

        return [asdict(q) for q in all_questions]

    @staticmethod
    def _list_page_images(folder: str) -> list[str]:
        files = []
        for name in os.listdir(folder):
            lower = name.lower()
            if lower.endswith((".png", ".jpg", ".jpeg", ".bmp", ".webp")):
                files.append(os.path.join(folder, name))

        def page_sort_key(path: str) -> tuple[int, str]:
            name = os.path.basename(path)
            m = re.search(r"page[_\- ]?(\d+)", name, re.IGNORECASE)
            if m:
                return int(m.group(1)), name
            nums = re.findall(r"\d+", name)
            if nums:
                return int(nums[-1]), name
            return 10**9, name

        files.sort(key=page_sort_key)
        return files

    @staticmethod
    def _parse_page_index(path: str, default_index: int) -> int:
        name = os.path.basename(path)
        m = re.search(r"page[_\- ]?(\d+)", name, re.IGNORECASE)
        if m:
            return int(m.group(1))
        nums = re.findall(r"\d+", name)
        if nums:
            return int(nums[-1])
        return default_index

    @staticmethod
    def _normalize_text(text: str) -> str:
        if not text:
            return ""
        text = text.replace("\u3000", " ")
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _detections_to_textlines(self, detections: list[dict]) -> list[TextLine]:
        lines: list[TextLine] = []

        for det in detections:
            text = self._normalize_text(det.get("DetectedText", ""))
            box = det.get("ItemPolygon", {}) or {}

            if not text:
                continue

            lines.append(
                TextLine(
                    text=text,
                    x=int(box.get("X", 0)),
                    y=int(box.get("Y", 0)),
                    w=int(box.get("Width", 0)),
                    h=int(box.get("Height", 0)),
                )
            )

        lines.sort(key=lambda t: (t.y, t.x))
        return lines

    def _is_section_title(self, line_text: str) -> bool:
        text = self._normalize_text(line_text)
        if not text:
            return False
        if not self.SECTION_TITLE_PREFIX_RE.match(text):
            return False
        return any(keyword in text for keyword in self.QUESTION_TYPE_KEYWORDS)

    def _extract_question_type_from_title(self, title_text: str) -> Optional[str]:
        text = self._normalize_text(title_text)
        for keyword in self.QUESTION_TYPE_KEYWORDS:
            if keyword in text:
                return keyword
        return None

    def _extract_default_score_from_title(self, title_text: str) -> Optional[int]:
        text = self._normalize_text(title_text)
        m = self.PER_QUESTION_SCORE_RE.search(text)
        if not m:
            return None
        try:
            return int(m.group(1))
        except Exception:
            return None

    def _parse_question_no(self, line_text: str) -> Optional[int]:
        text = self._normalize_text(line_text)
        m = self.QUESTION_NO_RE.match(text)
        if not m:
            return None
        try:
            return int(m.group(1))
        except Exception:
            return None

    def _extract_inline_score(self, question_text: str) -> Optional[int]:
        text = self._normalize_text(question_text)
        m = self.INLINE_SCORE_RE.search(text)
        if not m:
            return None
        try:
            return int(m.group(1))
        except Exception:
            return None

    def _collect_question_text(self, lines: list[TextLine], start_idx: int) -> str:
        parts = [lines[start_idx].text]

        for j in range(start_idx + 1, len(lines)):
            text = self._normalize_text(lines[j].text)

            if self._is_section_title(text):
                break

            if self._parse_question_no(text) is not None:
                break

            parts.append(text)

        return "\n".join(parts).strip()

    def _parse_page_questions(
        self,
        page_index: int,
        textlines: list[TextLine],
        inherited_context: SectionContext,
    ) -> tuple[list[QuestionInfo], SectionContext]:
        questions: list[QuestionInfo] = []
        current_context = SectionContext(
            question_type=inherited_context.question_type,
            default_score=inherited_context.default_score,
            section_title=inherited_context.section_title,
        )

        for i, line in enumerate(textlines):
            text = self._normalize_text(line.text)
            if not text:
                continue

            # 1. 新的大题标题
            if self._is_section_title(text):
                current_context = SectionContext(
                    question_type=self._extract_question_type_from_title(text),
                    default_score=self._extract_default_score_from_title(text),
                    section_title=text,
                )
                continue

            # 2. 小题题号
            qno = self._parse_question_no(text)
            if qno is None:
                continue

            question_text = self._collect_question_text(textlines, i)
            inline_score = self._extract_inline_score(question_text)
            final_score = inline_score if inline_score is not None else current_context.default_score

            questions.append(
                QuestionInfo(
                    page_index=page_index,
                    question_no=qno,
                    question_type=current_context.question_type,
                    score=final_score,
                    section_title=current_context.section_title,
                    question_text=question_text,
                    line_y=line.y,
                )
            )

        return questions, current_context