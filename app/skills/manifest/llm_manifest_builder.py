from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from pathlib import Path

from app.infrastructure.llm.base_vision_llm_client import BaseVisionLLMClient
from app.skills.manifest.manifest_models import ManifestBuildResult, ManifestItem


class LLMManifestBuilder:
    def __init__(self, vision_llm_client: BaseVisionLLMClient):
        self.vision_llm_client = vision_llm_client

    def build_manifest(
        self,
        question_root_dir: str,
        analysis_root_dir: str | None,
        cleaned_analysis_root_dir: str | None,
        output_path: str,
    ) -> ManifestBuildResult:
        task_root = Path(question_root_dir).parent
        index_json_path = task_root / "question_segments_index.json"

        raw_data = self._load_json_file(index_json_path, default=[])

        if isinstance(raw_data, dict):
            question_segments = raw_data.get("segments", [])
            pages_data = raw_data.get("pages", [])
            full_index_payload = raw_data
        else:
            question_segments = raw_data
            pages_data = []
            full_index_payload = {
                "pages": pages_data,
                "segments": question_segments,
            }

        ordered_question_files = self._build_question_files_from_segments(
            question_segments=question_segments,
            fallback_root_dir=question_root_dir,
        )
        if not ordered_question_files:
            return ManifestBuildResult(
                success=False,
                message="未找到题目图片，无法生成 manifest",
            )

        analysis_map = self._build_global_order_map(
            self._collect_images(analysis_root_dir) if analysis_root_dir else []
        )
        cleaned_map = self._build_global_order_map(
            self._collect_images(cleaned_analysis_root_dir) if cleaned_analysis_root_dir else []
        )

        segment_map = self._build_segment_map(question_segments)

        items: list[ManifestItem] = []
        failed_count = 0

        for index, question_path in enumerate(ordered_question_files, start=1):
            print(f"\n[LLMManifestBuilder] ===== 处理第 {index}/{len(ordered_question_files)} 题 =====")

            analysis_path = analysis_map.get(index)
            cleaned_analysis_path = cleaned_map.get(index)

            segment_info = segment_map.get(self._normalize_path(question_path))
            section_info = self._resolve_section_info(segment_info)

            llm_item_payload = {
                "global_order": index,
                "question_image_path": question_path,
                "analysis_image_path": analysis_path,
                "cleaned_analysis_image_path": cleaned_analysis_path,
            }

            try:
                if hasattr(self.vision_llm_client, "analyze_item"):
                    llm_result = self.vision_llm_client.analyze_item(llm_item_payload)
                else:
                    current_analysis = cleaned_analysis_path or analysis_path
                    llm_result = self.vision_llm_client.analyze_question_pair(
                        question_image_path=question_path,
                        analysis_image_path=current_analysis,
                    )
            except Exception as e:
                failed_count += 1
                llm_result = {
                    "answer": "uncertain",
                    "knowledge_points": [],
                    "is_subquestion": False,
                    "subquestion_index": None,
                    "belongs_to_previous_parent": False,
                    "confidence": 0.0,
                    "needs_review": True,
                    "llm_reason": f"llm_call_failed: {e}",
                    "_raw_content": "",
                    "_raw_response": None,
                }

            item = ManifestItem(
                global_order=index,
                question_image_path=question_path,
                analysis_image_path=analysis_path,
                cleaned_analysis_image_path=cleaned_analysis_path,
                question_type=section_info.get("question_type", "unknown"),
                answer=llm_result.get("answer", "uncertain"),
                score=section_info.get("score"),
                knowledge_points=llm_result.get("knowledge_points", []) or [],
                confidence=float(llm_result.get("confidence", 0.0) or 0.0),
                needs_review=bool(llm_result.get("needs_review", True)),
                llm_reason=llm_result.get("llm_reason", ""),
            )

            item.is_subquestion = bool(llm_result.get("is_subquestion", False))
            item.subquestion_index = llm_result.get("subquestion_index")
            item.belongs_to_previous_parent = bool(
                llm_result.get("belongs_to_previous_parent", False)
            )

            items.append(item)

            # =========================
            # 回填到总 JSON 的 segment
            # =========================
            if segment_info is not None:
                segment_info["global_order"] = index
                segment_info["analysis_image_path"] = analysis_path
                segment_info["cleaned_analysis_image_path"] = cleaned_analysis_path

                segment_info["question_type"] = section_info.get("question_type", "unknown")
                segment_info["score"] = section_info.get("score")

                segment_info["answer"] = llm_result.get("answer", "uncertain")
                segment_info["knowledge_points"] = llm_result.get("knowledge_points", []) or []
                print(f"[LLM] KP: {llm_result.get("knowledge_points", [])}")
                print(f"[LLM] REASON: {llm_result.get('llm_reason')}")
                segment_info["is_subquestion"] = bool(llm_result.get("is_subquestion", False))
                segment_info["subquestion_index"] = llm_result.get("subquestion_index")
                segment_info["belongs_to_previous_parent"] = bool(
                    llm_result.get("belongs_to_previous_parent", False)
                )
                segment_info["confidence"] = float(llm_result.get("confidence", 0.0) or 0.0)
                segment_info["needs_review"] = bool(llm_result.get("needs_review", True))
                segment_info["llm_reason"] = llm_result.get("llm_reason", "")

                if "_raw_content" in llm_result:
                    segment_info["llm_raw_content"] = llm_result.get("_raw_content")
                if "_raw_response" in llm_result:
                    segment_info["llm_raw_response"] = llm_result.get("_raw_response")

        self._group_parent_questions(items)
        self._assign_display_numbers_with_sub(items)

        # =========================
        # display_no / parent_display_no 再回填到总 JSON
        # =========================
        item_map = {
            self._normalize_path(item.question_image_path): item
            for item in items
        }

        for seg in question_segments:
            image_path = seg.get("image_path")
            if not image_path:
                continue
            matched_item = item_map.get(self._normalize_path(image_path))
            if not matched_item:
                continue

            seg["display_no"] = matched_item.display_no
            seg["parent_display_no"] = matched_item.parent_display_no
            seg["parent_group_id"] = matched_item.parent_group_id

        self._ensure_output_dir(output_path)
        self._write_manifest(output_path, items)

        # =========================
        # 把 enriched 后的总 JSON 写回去
        # =========================
        full_index_payload["pages"] = pages_data
        full_index_payload["segments"] = question_segments
        with open(index_json_path, "w", encoding="utf-8") as f:
            json.dump(full_index_payload, f, ensure_ascii=False, indent=2)

        return ManifestBuildResult(
            success=True,
            message=f"manifest 生成完成，共 {len(items)} 题，失败 {failed_count} 题",
            manifest_path=output_path,
            total_count=len(items),
            items=items,
        )

    def _collect_images(self, root_dir: str | None) -> list[str]:
        if not root_dir or not os.path.isdir(root_dir):
            return []

        exts = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
        files = []

        for r, _, names in os.walk(root_dir):
            for n in names:
                if Path(n).suffix.lower() in exts:
                    files.append(str(Path(r) / n))

        files.sort(key=self._sort_key_by_page_and_question)
        return files

    def _build_global_order_map(self, files: list[str]) -> dict[int, str]:
        return {i: path for i, path in enumerate(files, start=1)}

    def _sort_key_by_page_and_question(self, path: str):
        return (self._extract_page_no(path), self._extract_question_no(path), path)

    def _extract_page_no(self, path: str) -> int:
        for p in Path(path).parts:
            m = re.match(r"page_(\d+)", p.lower())
            if m:
                return int(m.group(1))
        return 10**9

    def _extract_question_no(self, path: str) -> int:
        m = re.search(r"question_(\d+)", Path(path).stem.lower())
        return int(m.group(1)) if m else 10**9

    def _normalize_path(self, path: str) -> str:
        return str(Path(path).resolve()).lower()

    def _build_segment_map(self, segments):
        return {
            self._normalize_path(s["image_path"]): s
            for s in segments if s.get("image_path")
        }

    def _build_question_files_from_segments(self, question_segments, fallback_root_dir):
        valid = [s for s in question_segments if os.path.exists(s.get("image_path", ""))]
        if not valid:
            return self._collect_images(fallback_root_dir)

        valid.sort(key=lambda s: (s.get("page_no", 10**9), s.get("question_index_on_page", 10**9)))
        return [s["image_path"] for s in valid]

    def _infer_question_type_from_title(self, raw_title: str) -> str:
        t = (raw_title or "").replace(" ", "")
        if "填空题" in t:
            return "fill_blank"
        if "计算题" in t:
            return "calculation"
        if "选择题" in t:
            return "choice"
        if "判断题" in t:
            return "judgement"
        if "应用题" in t or "解决问题" in t or "解答题" in t:
            return "application"
        return "unknown"

    def _resolve_section_info(self, segment_info: dict | None):
        if not segment_info:
            return {"question_type": "unknown", "score": None}

        raw_title = segment_info.get("section_raw_title")
        q_no = segment_info.get("question_no_ocr")

        if raw_title:
            return {
                "question_type": self._infer_question_type_from_title(raw_title),
                "score": self._resolve_score(raw_title, q_no),
            }

        return {"question_type": "unknown", "score": None}

    def _resolve_score(self, raw_title: str, q_no: int | None):
        raw = (raw_title or "").replace(" ", "")

        for s, e, sc in re.findall(r"(\d+)-(\d+)每题(\d+)分", raw):
            if q_no and int(s) <= q_no <= int(e):
                return int(sc)

        m = re.search(r"每题(\d+)分", raw)
        if m:
            return int(m.group(1))

        return None

    def _group_parent_questions(self, items):
        gid = 0
        for i, it in enumerate(items):
            if i == 0 or not it.belongs_to_previous_parent:
                gid += 1
            it.parent_group_id = gid

    def _assign_display_numbers_with_sub(self, items):
        pc = defaultdict(int)
        sc = defaultdict(int)

        for it in items:
            t = it.question_type or "unknown"

            if not it.belongs_to_previous_parent:
                pc[t] += 1
                sc[it.parent_group_id] = 0

            label = self._type_label(t)
            it.parent_display_no = f"{label}{pc[t]}"

            if it.is_subquestion:
                sc[it.parent_group_id] += 1
                it.display_no = f"{it.parent_display_no}-{sc[it.parent_group_id]}"
            else:
                it.display_no = it.parent_display_no

    def _type_label(self, t):
        return {
            "fill_blank": "填空题",
            "calculation": "计算题",
            "application": "解决问题",
            "choice": "选择题",
            "judgement": "判断题",
        }.get(t, "未知题型")

    def _ensure_output_dir(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)

    def _write_manifest(self, path, items):
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "total_count": len(items),
                "items": [i.to_dict() for i in items]
            }, f, ensure_ascii=False, indent=2)

    def _load_json_file(self, path: Path, default):
        if not path.exists():
            return default
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)