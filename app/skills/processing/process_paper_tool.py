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
    AnalysisCleaner,
)
from app.skills.parsing import BlankStructureParser


class ProcessPaperTool(BaseTool):
    name = "process_paper"

    def __init__(
            self,
            task_file_service: TaskFileService,
            task_service: TaskService,
            task_memory_service: TaskMemoryService,
            pdf_renderer: PDFRenderer,
            question_segmenter: QuestionSegmenter,
            analysis_cleaner: AnalysisCleaner,
            page_ocr_client: Any | None = None,
            blank_structure_parser: BlankStructureParser | None = None,
    ):
        self.task_file_service = task_file_service
        self.task_service = task_service
        self.task_memory_service = task_memory_service
        self.pdf_renderer = pdf_renderer
        self.question_segmenter = question_segmenter
        self.analysis_cleaner = analysis_cleaner
        self.page_ocr_client = page_ocr_client
        self.blank_structure_parser = blank_structure_parser

    def _ensure_uploads_dir_with_materials(
        self,
        task_root: Path,
        blank_pdf_path: str,
        solution_pdf_path: str,
    ) -> None:
        uploads_dir = task_root / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)

        for src_path in [blank_pdf_path, solution_pdf_path]:
            if not src_path:
                continue

            src = Path(src_path)
            if not src.exists() or not src.is_file():
                continue

            dst = uploads_dir / src.name
            if dst.exists():
                continue

            try:
                os.link(src, dst)
            except Exception:
                try:
                    import shutil
                    shutil.copy2(src, dst)
                except Exception:
                    pass

    @staticmethod
    def _build_structure_map(structure_records: list[dict]) -> dict[tuple[int, int], dict]:
        result: dict[tuple[int, int], dict] = {}
        for item in structure_records:
            page_index = item.get("page_index")
            question_no = item.get("question_no")
            if isinstance(page_index, int) and isinstance(question_no, int):
                result[(page_index, question_no)] = item
        return result

    @staticmethod
    def _merge_structure_into_segments(
            pages: list[dict],
            segments: list[dict],
            structure_records: list[dict],
    ) -> tuple[list[dict], list[dict]]:
        merged_segments = []

        for seg in segments:
            seg = dict(seg)
            page_no = seg.get("page_no")
            seg_y = (seg.get("outer_bbox") or [0, 0, 0, 0])[1]

            same_page_questions = [
                q for q in structure_records
                if q.get("page_index") == page_no
            ]

            best_match = None
            min_diff = 999999

            for q in same_page_questions:
                q_y = q.get("line_y", 0)
                diff = abs(seg_y - q_y)
                if diff < min_diff:
                    min_diff = diff
                    best_match = q

            if best_match is not None and min_diff < 200:
                seg["question_text"] = best_match.get("question_text", seg.get("question_text", ""))
                seg["question_start_text"] = best_match.get("question_text", seg.get("question_start_text", ""))
                seg["section_raw_title"] = best_match.get("section_title")
                seg["section_type"] = best_match.get("question_type")
                seg["score_per_question"] = best_match.get("score")
                seg["question_type"] = best_match.get("question_type")
                seg["score"] = best_match.get("score")
                seg["line_y"] = best_match.get("line_y")
                seg["question_no"] = best_match.get("question_no")

            merged_segments.append(seg)

        merged_pages = []
        for page in pages:
            page = dict(page)
            page_no = page.get("page_no")
            if isinstance(page_no, int):
                page_questions = [
                    s for s in structure_records
                    if s.get("page_index") == page_no
                ]
                page["blank_structure_questions"] = page_questions
            merged_pages.append(page)

        return merged_pages, merged_segments


    @staticmethod
    def _attach_solution_paths_to_blank_segments(
        blank_segments: list[dict],
        solution_segments: list[dict],
    ) -> list[dict]:
        by_key: dict[tuple[int, int], dict] = {}
        by_page_order: dict[tuple[int, int], dict] = {}

        for seg in solution_segments:
            page_no = seg.get("page_no")
            qno = seg.get("question_no_ocr")
            order = seg.get("question_index_on_page")

            if isinstance(page_no, int) and isinstance(qno, int):
                by_key[(page_no, qno)] = seg
            if isinstance(page_no, int) and isinstance(order, int):
                by_page_order[(page_no, order)] = seg

        merged = []
        for seg in blank_segments:
            seg = dict(seg)
            page_no = seg.get("page_no")
            qno = seg.get("question_no_ocr")
            order = seg.get("question_index_on_page")

            matched = None
            if isinstance(page_no, int) and isinstance(qno, int):
                matched = by_key.get((page_no, qno))
            if matched is None and isinstance(page_no, int) and isinstance(order, int):
                matched = by_page_order.get((page_no, order))

            if matched:
                seg["analysis_image_path"] = matched.get("question_image_path")
                seg["analysis_crop_bbox"] = matched.get("crop_bbox")
                seg["analysis_start_anchor_bbox"] = matched.get("start_anchor_bbox")

            merged.append(seg)

        return merged

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
        question_segments_index_path = task_root / "question_segments_index.json"

        self._ensure_uploads_dir_with_materials(
            task_root=task_root,
            blank_pdf_path=blank_pdf_path,
            solution_pdf_path=solution_pdf_path,
        )

        self.task_memory_service.update_processing_summary(
            task_id=task_id,
            current_stage="processing",
            processing_summary="开始执行 PDF 渲染",
        )

        blank_render_result = self.pdf_renderer.render_pdf_to_images(
            pdf_path=blank_pdf_path,
            output_dir=str(blank_render_dir),
            dpi=400,
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
            dpi=400,
            image_prefix="page",
        )
        if not solution_render_result.success:
            return ToolResult(
                tool_name=self.name,
                success=False,
                message=solution_render_result.message,
                data={"step": "render_solution_pdf"},
            )

        blank_structure_records: list[dict] = []

        if self.blank_structure_parser is not None:
            self.task_memory_service.update_processing_summary(
                task_id=task_id,
                current_stage="processing",
                processing_summary="开始解析空白卷题型与分数",
            )

            blank_structure_records = self.blank_structure_parser.parse_pages(
                str(blank_render_dir)
            )

        self.task_memory_service.update_processing_summary(
            task_id=task_id,
            current_stage="processing",
            processing_summary="开始切割 blank 题目图片",
        )

        question_files_all: list[str] = []
        question_segments_all: list[dict] = []
        question_pages_all: list[dict] = []

        for page_image in blank_render_result.files:
            print(f"\n[ProcessPaperTool] ===== 开始切割 blank 页: {page_image} =====")
            page_stem = Path(page_image).stem
            page_output_dir = question_output_root / page_stem

            result = self.question_segmenter.segment_page(
                image_path=page_image,
                output_dir=str(page_output_dir),
            )
            print(f"[ProcessPaperTool] blank 切割完成: success={result.success}, message={result.message}")

            meta = dict(result.metadata or {})
            if result.success:
                question_files_all.extend(result.files)
                question_pages_all.append(meta)
                question_segments_all.extend(meta.get("segments", []))
            else:
                if meta:
                    meta["segmentation_success"] = False
                    meta["segmentation_message"] = result.message
                    question_pages_all.append(meta)

        self.task_memory_service.update_processing_summary(
            task_id=task_id,
            current_stage="processing",
            processing_summary="开始切割 solution 对应题图",
        )

        analysis_files_all: list[str] = []
        solution_segments_all: list[dict] = []
        solution_pages_all: list[dict] = []

        for page_image in solution_render_result.files:
            print(f"\n[ProcessPaperTool] ===== 开始切割 solution 页: {page_image} =====")
            page_stem = Path(page_image).stem
            page_output_dir = analysis_output_root / page_stem

            result = self.question_segmenter.segment_page(
                image_path=page_image,
                output_dir=str(page_output_dir),
            )
            print(f"[ProcessPaperTool] solution 切割完成: success={result.success}, message={result.message}")

            meta = dict(result.metadata or {})
            if result.success:
                analysis_files_all.extend(result.files)
                solution_pages_all.append(meta)
                solution_segments_all.extend(meta.get("segments", []))
            else:
                if meta:
                    meta["segmentation_success"] = False
                    meta["segmentation_message"] = result.message
                    solution_pages_all.append(meta)

        # 先把结构信息合并进 blank 题目 segments
        question_pages_all, question_segments_all = self._merge_structure_into_segments(
            pages=question_pages_all,
            segments=question_segments_all,
            structure_records=blank_structure_records,
        )

        # 再把 solution 页同逻辑切出的图片路径挂到 blank segments 上
        question_segments_all = self._attach_solution_paths_to_blank_segments(
            blank_segments=question_segments_all,
            solution_segments=solution_segments_all,
        )

        question_segments_index_path.parent.mkdir(parents=True, exist_ok=True)
        full_index_payload = {
            "pages": question_pages_all,
            "segments": question_segments_all,
        }
        with open(question_segments_index_path, "w", encoding="utf-8") as f:
            json.dump(full_index_payload, f, ensure_ascii=False, indent=2)

        summary = {
            "blank_rendered_pages": len(blank_render_result.files),
            "solution_rendered_pages": len(solution_render_result.files),
            "question_image_count": len(question_files_all),
            "analysis_image_count": len(analysis_files_all),
            "task_root": str(task_root),
            "question_output_root": str(question_output_root),
            "analysis_output_root": str(analysis_output_root),
            "question_segments_index_path": str(question_segments_index_path),
            "question_pages_count": len(question_pages_all),
            "question_segments_count": len(question_segments_all),
            "blank_structure_count": len(blank_structure_records),
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
            message="process_paper 执行完成，已生成 blank 题图、solution 对应题图，并更新 question_segments_index.json",
            data=summary,
        )