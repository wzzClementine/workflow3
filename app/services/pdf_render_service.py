from pathlib import Path
from typing import Any

import fitz  # PyMuPDF

from app.utils.logger import setup_logger
from app.config import settings
from app.utils.file_utils import ensure_dir

logger = setup_logger(settings.log_level, settings.logs_dir)


class PDFRenderService:
    def render_pdf_to_images(
        self,
        pdf_path: str | Path,
        output_dir: str | Path,
        dpi: int = 300,
        prefix: str = "page",
    ) -> list[Path]:
        pdf_path = Path(pdf_path)
        output_dir = ensure_dir(output_dir)

        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF 不存在: {pdf_path}")
        if pdf_path.suffix.lower() != ".pdf":
            raise ValueError(f"文件不是 PDF: {pdf_path}")

        doc = fitz.open(pdf_path)
        image_paths: list[Path] = []

        try:
            scale = dpi / 72.0
            matrix = fitz.Matrix(scale, scale)

            for page_index in range(len(doc)):
                page = doc.load_page(page_index)
                pix = page.get_pixmap(matrix=matrix, alpha=False)

                filename = f"{prefix}_{page_index + 1:03d}.png"
                output_path = output_dir / filename
                pix.save(output_path)

                image_paths.append(output_path)

            logger.info(
                "PDF rendered successfully: pdf=%s, pages=%s, output_dir=%s",
                pdf_path,
                len(image_paths),
                output_dir,
            )
            return image_paths
        finally:
            doc.close()


pdf_render_service = PDFRenderService()