from __future__ import annotations

import re
from typing import Any


SECTION_TYPE_MAP = {
    "填空题": "fill_blank",
    "计算题": "calculation",
    "解决问题": "application",
    "应用题": "application",
    "几何题": "geometry",
}


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def parse_section_title_line(text: str) -> dict[str, Any] | None:
    raw = normalize_text(text)

    matched_title = None
    matched_type = None
    for cn_title, en_type in SECTION_TYPE_MAP.items():
        if cn_title in raw:
            matched_title = cn_title
            matched_type = en_type
            break

    if not matched_title:
        return None

    score_per_question = None
    total_score = None

    m1 = re.search(r"每题(\d+)分", raw)
    if m1:
        score_per_question = int(m1.group(1))

    m2 = re.search(r"共(\d+)分", raw)
    if m2:
        total_score = int(m2.group(1))

    return {
        "section_type": matched_type,
        "section_title": matched_title,
        "score_per_question": score_per_question,
        "total_score": total_score,
        "raw_title": text,
    }


def parse_page_structure_from_ocr(ocr_blocks: list[dict], page_no: int) -> dict[str, Any]:
    sections = []

    for block in ocr_blocks:
        text = block.get("text", "")
        parsed = parse_section_title_line(text)
        if not parsed:
            continue

        parsed["page_no"] = page_no
        parsed["title_bbox"] = block.get("bbox")
        sections.append(parsed)

    sections.sort(
        key=lambda x: x["title_bbox"][1]
        if x.get("title_bbox") and len(x["title_bbox"]) >= 2
        else 10**9
    )

    return {
        "page_no": page_no,
        "sections": sections,
    }