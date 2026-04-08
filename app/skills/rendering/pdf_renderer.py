from __future__ import annotations

import os
import shutil
from pathlib import Path

import fitz  # PyMuPDF

from app.skills.segmentation.segmentation_models import SegmentationOutput


class PDFRenderer:
    def render_pdf_to_images(
        self,
        pdf_path: str,
        output_dir: str,
        dpi: int = 400,
        image_prefix: str = "page",
    ) -> SegmentationOutput:
        if not os.path.exists(pdf_path):
            return SegmentationOutput(
                success=False,
                message=f"PDF 不存在: {pdf_path}",
            )

        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)
        os.makedirs(output_dir, exist_ok=True)

        doc = fitz.open(pdf_path)
        saved_files: list[str] = []

        try:
            zoom = dpi / 72.0
            matrix = fitz.Matrix(zoom, zoom)

            for page_index in range(len(doc)):
                page = doc.load_page(page_index)
                pix = page.get_pixmap(matrix=matrix, alpha=False)

                save_path = os.path.join(
                    output_dir,
                    f"{image_prefix}_{page_index + 1}.png",
                )
                pix.save(save_path)
                saved_files.append(save_path)

        finally:
            doc.close()

        return SegmentationOutput(
            success=True,
            message=f"PDF 渲染完成，共生成 {len(saved_files)} 张页图",
            output_dir=output_dir,
            files=saved_files,
            metadata={
                "page_count": len(saved_files),
                "dpi": dpi,
            },
        )