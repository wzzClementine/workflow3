from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any

from app.agent.tools import BaseTool, ToolCall, ToolResult
from app.services.file import TaskFileService
from app.services.task import TaskService
from app.services.memory import TaskMemoryService
from app.skills.rendering import PDFRenderer
from app.skills.segmentation import (
    QuestionSegmenter,
    AnalysisSegmenter,
    AnalysisCleaner,
)


class ProcessPaperTool(BaseTool):
    name = "process_paper"

    def __init__(
        self,
        task_file_service: TaskFileService,
        task_service: TaskService,
        task_memory_service: TaskMemoryService,
        pdf_renderer: PDFRenderer,
        question_segmenter: QuestionSegmenter,
        analysis_segmenter: AnalysisSegmenter,
        analysis_cleaner: AnalysisCleaner,
        page_ocr_client: Any | None = None,
    ):
        self.task_file_service = task_file_service
        self.task_service = task_service
        self.task_memory_service = task_memory_service
        self.pdf_renderer = pdf_renderer
        self.question_segmenter = question_segmenter
        self.analysis_segmenter = analysis_segmenter
        self.analysis_cleaner = analysis_cleaner
        self.page_ocr_client = page_ocr_client

    def execute(self, tool_call: ToolCall) -> ToolResult:
        task_id = tool_call.tool_args.get("task_id")
        work_dir = tool_call.tool_args.get("work_dir")

        if not task_id:
            return ToolResult(
                tool_name=self.name,
                success=False,
                message="缺少 task_id",
                data={},
            )

        if not work_dir:
            return ToolResult(
                tool_name=self.name,
                success=False,
                message="缺少 work_dir",
                data={},
            )

        materials = self.task_file_service.get_materials_summary(task_id)
        if not materials["is_ready"]:
            return ToolResult(
                tool_name=self.name,
                success=False,
                message="材料未齐全，无法开始处理",
                data={"materials_summary": materials},
            )

        blank_pdf_record = materials["blank_files"][-1]
        solution_pdf_record = materials["solution_files"][-1]

        blank_pdf_path = blank_pdf_record.get("local_path")
        solution_pdf_path = solution_pdf_record.get("local_path")

        if not blank_pdf_path or not os.path.exists(blank_pdf_path):
            return ToolResult(
                tool_name=self.name,
                success=False,
                message="blank_pdf 本地路径不存在，当前版本 process_paper 仅支持本地 PDF",
                data={},
            )

        if not solution_pdf_path or not os.path.exists(solution_pdf_path):
            return ToolResult(
                tool_name=self.name,
                success=False,
                message="solution_pdf 本地路径不存在，当前版本 process_paper 仅支持本地 PDF",
                data={},
            )

        task_root = Path(work_dir) / task_id
        blank_render_dir = task_root / "rendered_pages" / "blank"
        solution_render_dir = task_root / "rendered_pages" / "solution"
        question_output_root = task_root / "question_images"
        analysis_output_root = task_root / "analysis_images"
        cleaned_output_root = task_root / "cleaned_analysis_images"
        question_segments_index_path = task_root / "question_segments_index.json"

        self.task_memory_service.update_processing_summary(
            task_id=task_id,
            current_stage="processing",
            processing_summary="开始执行 PDF 渲染",
        )

        blank_render_result = self.pdf_renderer.render_pdf_to_images(
            pdf_path=blank_pdf_path,
            output_dir=str(blank_render_dir),
            dpi=200,
            image_prefix="page",
        )
        if not blank_render_result.success:
            return ToolResult(
                tool_name=self.name,
                success=False,
                message=blank_render_result.message,
                data={"step": "render_blank_pdf"},
            )

        solution_render_result = self.pdf_renderer.render_pdf_to_images(
            pdf_path=solution_pdf_path,
            output_dir=str(solution_render_dir),
            dpi=200,
            image_prefix="page",
        )
        if not solution_render_result.success:
            return ToolResult(
                tool_name=self.name,
                success=False,
                message=solution_render_result.message,
                data={"step": "render_solution_pdf"},
            )

        self.task_memory_service.update_processing_summary(
            task_id=task_id,
            current_stage="processing",
            processing_summary="PDF 渲染完成，开始切割题目与解析",
        )

        question_files_all: list[str] = []
        question_debug_all: list[str] = []
        question_segments_all: list[dict] = []
        question_pages_all: list[dict] = []

        analysis_files_all: list[str] = []
        analysis_debug_all: list[str] = []

        last_nonempty_section: dict | None = None
        last_question_no_ocr: int | None = None

        # ========== 题目切割 + 页级全量 metadata 汇总 ==========
        for page_image in blank_render_result.files:
            print(f"\n[ProcessPaperTool] ===== 开始切题页: {page_image} =====")

            page_stem = Path(page_image).stem
            page_output_dir = question_output_root / page_stem

            result = self.question_segmenter.segment_page(
                image_path=page_image,
                output_dir=str(page_output_dir),
            )
            print(f"[ProcessPaperTool] 切题完成: success={result.success}, message={result.message}")

            meta = dict(result.metadata or {})

            if result.success:
                # ===== 续页继承上一页题型 =====
                meta = self._apply_continuation_section_inheritance(
                    meta=meta,
                    last_nonempty_section=last_nonempty_section,
                    last_question_no_ocr=last_question_no_ocr,
                )

                sections = meta.get("sections", []) or []
                if sections:
                    last_nonempty_section = deepcopy(sections[-1])

                page_segments = meta.get("segments", []) or []
                if page_segments:
                    nums = [
                        seg.get("question_no_ocr")
                        for seg in page_segments
                        if isinstance(seg.get("question_no_ocr"), int)
                    ]
                    if nums:
                        last_question_no_ocr = nums[-1]

                question_files_all.extend(result.files)
                question_debug_all.extend(result.debug_files)
                question_pages_all.append(meta)
                question_segments_all.extend(meta.get("segments", []))
            else:
                if meta:
                    meta["segmentation_success"] = False
                    meta["segmentation_message"] = result.message
                    question_pages_all.append(meta)

        # 统一写一个全量总 JSON
        question_segments_index_path.parent.mkdir(parents=True, exist_ok=True)
        full_index_payload = {
            "pages": question_pages_all,
            "segments": question_segments_all,
        }
        with open(question_segments_index_path, "w", encoding="utf-8") as f:
            json.dump(full_index_payload, f, ensure_ascii=False, indent=2)

        # ========== 解析切割 ==========
        for page_image in solution_render_result.files:
            print(f"\n[ProcessPaperTool] ===== 开始切解析页: {page_image} =====")

            page_stem = Path(page_image).stem
            page_output_dir = analysis_output_root / page_stem

            result = self.analysis_segmenter.segment_page(
                image_path=page_image,
                output_dir=str(page_output_dir),
            )
            if result.success:
                analysis_files_all.extend(result.files)
                analysis_debug_all.extend(result.debug_files)

        self.task_memory_service.update_processing_summary(
            task_id=task_id,
            current_stage="processing",
            processing_summary="题目和解析切割完成，开始清洗解析图片",
        )

        print(f"[ProcessPaperTool] 开始清洗解析图: input_dir={analysis_output_root}, output_dir={cleaned_output_root}")
        clean_result = self.analysis_cleaner.clean_folder(
            input_dir=str(analysis_output_root),
            output_dir=str(cleaned_output_root),
            save_debug_ocr_json=False,
            remove_blue_lines=True,
            crop_outer_whitespace=False,
            overlap_threshold=30,
        )

        if not clean_result.success:
            return ToolResult(
                tool_name=self.name,
                success=False,
                message=clean_result.message,
                data={"step": "clean_analysis"},
            )

        summary = {
            "blank_rendered_pages": len(blank_render_result.files),
            "solution_rendered_pages": len(solution_render_result.files),
            "question_image_count": len(question_files_all),
            "analysis_image_count": len(analysis_files_all),
            "cleaned_analysis_count": len(clean_result.files),
            "task_root": str(task_root),
            "question_output_root": str(question_output_root),
            "analysis_output_root": str(analysis_output_root),
            "cleaned_output_root": str(cleaned_output_root),
            "question_segments_index_path": str(question_segments_index_path),
            "question_pages_count": len(question_pages_all),
            "question_segments_count": len(question_segments_all),
            "blank_pdf_path": blank_pdf_path,
            "solution_pdf_path": solution_pdf_path,
        }

        self.task_memory_service.update_processing_summary(
            task_id=task_id,
            current_stage="processing",
            processing_summary=f"处理链已完成: {json.dumps(summary, ensure_ascii=False)}",
        )
        self.task_memory_service.update_next_action_hint(
            task_id=task_id,
            current_stage="processing",
            next_action_hint="下一步生成 Excel manifest",
        )

        return ToolResult(
            tool_name=self.name,
            success=True,
            message="process_paper 执行完成，已生成页图、题目切图全量索引、解析图片和清洗后的解析图片",
            data=summary,
        )

    def _apply_continuation_section_inheritance(
        self,
        meta: dict,
        last_nonempty_section: dict | None,
        last_question_no_ocr: int | None,
    ) -> dict:
        """
        更严谨的续页继承规则：

        A. 当前页完全没有 section：
           - 若第一页题号不是 1，则整页继承上一页最后一个 section

        B. 当前页存在 section：
           - 找出第一个显式 section 标题之前的未归属题目
           - 只有当这些题号都不是 1，且当前页第一个显式 section 下第一题号是 1 时，
             才把这些前置题目视为上一页题型的续页
           - 若还能与上一页最后题号连续，则置信度更高
        """
        print(f"[ProcessPaperTool] 检查续页继承: page_no={meta.get('page_no')}")

        if not meta:
            return meta

        segments = meta.get("segments", []) or []
        sections = meta.get("sections", []) or []

        if not segments or not last_nonempty_section:
            return meta

        def _get_seg_start_y(seg: dict) -> int | None:
            anchor = seg.get("start_anchor_bbox") or []
            if len(anchor) >= 2:
                return anchor[1]
            return None

        def _get_seg_num(seg: dict) -> int | None:
            num = seg.get("question_no_ocr")
            return num if isinstance(num, int) else None

        img_h = ((meta.get("image_size") or {}).get("height")) or 0
        first_question_no = _get_seg_num(segments[0])

        # =========================================================
        # 情况 A：当前页完全没有 section
        # =========================================================
        if not sections:
            if first_question_no in (None, 1):
                return meta

            inherited_section = deepcopy(last_nonempty_section)
            inherited_section["section_order"] = 1
            inherited_section["y_start"] = 0
            inherited_section["y_end"] = max(0, img_h - 1)
            inherited_section["inherited_from_previous_page"] = True
            inherited_section["inherit_reason"] = "page_without_section_and_first_question_not_1"

            meta["sections"] = [inherited_section]
            meta["inherited_section_from_previous_page"] = True

            for seg in segments:
                if not seg.get("section_raw_title"):
                    seg["section_order"] = inherited_section.get("section_order")
                    seg["section_raw_title"] = inherited_section.get("raw_title")
                    seg["section_y_range"] = [
                        inherited_section.get("y_start"),
                        inherited_section.get("y_end"),
                    ]

            return meta

        # =========================================================
        # 情况 B：当前页有 section，但标题之前可能有上一题型续页
        # =========================================================
        first_section = sections[0]
        first_section_y = first_section.get("y_start", 0)

        # 1) 找出第一个 section 标题之前、且当前还没绑定题型的题
        leading_unassigned_segments = []
        for seg in segments:
            seg_y = _get_seg_start_y(seg)
            if seg_y is None:
                continue
            if seg_y < first_section_y and not seg.get("section_raw_title"):
                leading_unassigned_segments.append(seg)

        if not leading_unassigned_segments:
            return meta

        # 2) 这些前置题的题号必须都不是 1
        leading_nums = [_get_seg_num(seg) for seg in leading_unassigned_segments]
        leading_nums = [n for n in leading_nums if n is not None]

        if not leading_nums:
            return meta

        if any(n == 1 for n in leading_nums):
            return meta

        # 3) 当前页第一个显式 section 下的第一题号，最好是 1
        first_section_segments = []
        for seg in segments:
            seg_y = _get_seg_start_y(seg)
            if seg_y is None:
                continue
            if seg_y >= first_section_y:
                first_section_segments.append(seg)

        if not first_section_segments:
            return meta

        first_section_first_num = _get_seg_num(first_section_segments[0])

        # 这是最关键的“新题型起点”信号
        if first_section_first_num != 1:
            return meta

        # 4) 可选增强：如果与上一页最后题号连续，则更可信
        continuous_with_previous = False
        if last_question_no_ocr is not None and leading_nums:
            # 例如上一页最后一题是10，这一页前置题从11开始
            if min(leading_nums) == last_question_no_ocr + 1:
                continuous_with_previous = True

        inherited_section = deepcopy(last_nonempty_section)
        inherited_section["section_order"] = 0
        inherited_section["y_start"] = 0
        inherited_section["y_end"] = max(0, first_section_y - 1)
        inherited_section["inherited_from_previous_page"] = True
        inherited_section["leading_continuation_section"] = True
        inherited_section["inherit_reason"] = (
            "leading_questions_before_first_section"
            if not continuous_with_previous
            else "leading_questions_before_first_section_and_question_no_continuous"
        )

        # 插到最前面，表示这一页前半段是上一题型续页
        meta["sections"] = [inherited_section] + sections
        meta["inherited_section_from_previous_page"] = True

        for seg in leading_unassigned_segments:
            seg["section_order"] = inherited_section.get("section_order")
            seg["section_raw_title"] = inherited_section.get("raw_title")
            seg["section_y_range"] = [
                inherited_section.get("y_start"),
                inherited_section.get("y_end"),
            ]

        return meta