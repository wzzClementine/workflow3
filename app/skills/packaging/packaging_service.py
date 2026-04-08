from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path


class PackagingService:
    def build_delivery_package(
        self,
        task_id: str,
        task_root: str,
        excel_path: str,
        question_dir: str,
        analysis_dir: str | None,
        cleaned_analysis_dir: str | None,
        manifest_path: str | None,
        source_pdf_path: str | None = None,
    ) -> str:
        """
        构建最终交付目录
        """
        package_name = self._derive_package_name(source_pdf_path, task_id)
        delivery_root = Path(task_root) / "delivery" / package_name

        if delivery_root.exists():
            shutil.rmtree(delivery_root)

        delivery_root.mkdir(parents=True, exist_ok=True)

        # ===== 1. Excel -> tags.xlsx（放根目录）=====
        if not os.path.exists(excel_path):
            raise FileNotFoundError(f"Excel 不存在: {excel_path}")
        shutil.copy(excel_path, delivery_root / "tags.xlsx")

        # ===== 2. 把空白试卷 PDF 放进去 =====
        if source_pdf_path and os.path.exists(source_pdf_path):
            shutil.copy(source_pdf_path, delivery_root / Path(source_pdf_path).name)

        # ===== 3. 读取 manifest，按 display_no 重命名图片 =====
        items = self._load_manifest_items(manifest_path)

        # questionPicture
        question_picture_dir = delivery_root / "questionPicture"
        question_picture_dir.mkdir(exist_ok=True)
        self._copy_images_by_manifest_items(
            items=items,
            target_dir=question_picture_dir,
            image_field="question_image_path",
        )

        # analysisPicture（优先 cleaned_analysis_image_path）
        analysis_picture_dir = delivery_root / "analysisPicture"
        analysis_picture_dir.mkdir(exist_ok=True)
        self._copy_images_by_manifest_items(
            items=items,
            target_dir=analysis_picture_dir,
            image_field="analysis_auto",
        )

        # manifest 保留
        if manifest_path and os.path.exists(manifest_path):
            shutil.copy(manifest_path, delivery_root / "manifest.json")

        return str(delivery_root)

    def _derive_package_name(self, source_pdf_path: str | None, fallback_task_id: str) -> str:
        if not source_pdf_path:
            return fallback_task_id

        stem = Path(source_pdf_path).stem
        # 去掉尾部“试卷”或“解析”
        stem = re.sub(r"(试卷|解析)$", "", stem).strip()
        return stem or fallback_task_id

    def _load_manifest_items(self, manifest_path: str | None) -> list[dict]:
        if not manifest_path or not os.path.exists(manifest_path):
            return []

        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        return manifest.get("items", []) or []

    def _safe_filename(self, name: str) -> str:
        name = (name or "").strip()
        if not name:
            name = "unknown"

        # Windows 非法字符替换
        name = re.sub(r'[\\/:*?"<>|]+', "_", name)
        name = re.sub(r"\s+", "", name)
        return name

    def _copy_images_by_manifest_items(
        self,
        items: list[dict],
        target_dir: Path,
        image_field: str,
    ) -> None:
        used_names: dict[str, int] = {}

        for item in items:
            display_no = item.get("display_no") or item.get("parent_display_no") or "unknown"

            if image_field == "analysis_auto":
                src = item.get("cleaned_analysis_image_path") or item.get("analysis_image_path")
            else:
                src = item.get(image_field)

            if not src or not os.path.exists(src):
                continue

            ext = Path(src).suffix or ".png"
            base_name = self._safe_filename(display_no)
            final_name = f"{base_name}{ext}"

            if final_name in used_names:
                used_names[final_name] += 1
                final_name = f"{base_name}_{used_names[final_name]}{ext}"
            else:
                used_names[final_name] = 1

            shutil.copy(src, target_dir / final_name)