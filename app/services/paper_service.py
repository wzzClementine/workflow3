from datetime import datetime
from typing import Any
from uuid import uuid4

from app.db.sqlite_manager import sqlite_manager
from app.utils.logger import setup_logger
from app.config import settings

logger = setup_logger(settings.log_level, settings.logs_dir)


class PaperService:
    def generate_paper_id(self) -> str:
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = uuid4().hex[:4]
        return f"paper_{now}_{suffix}"

    def create_paper(
        self,
        paper_name: str,
        source_type: str,
        raw_pdf_path: str,
    ) -> dict[str, Any]:
        paper_id = self.generate_paper_id()
        now = datetime.now().isoformat(timespec="seconds")

        sqlite_manager.execute(
            """
            INSERT INTO papers (
                paper_id, paper_name, source_type, raw_pdf_path,
                page_count, json_path, publish_status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                paper_id,
                paper_name,
                source_type,
                raw_pdf_path,
                0,
                None,
                "draft",
                now,
                now,
            )
        )

        paper = sqlite_manager.fetch_one(
            "SELECT * FROM papers WHERE paper_id = ?",
            (paper_id,),
        )

        logger.info("Paper created successfully: %s", paper_id)
        return paper

    def get_paper_by_id(self, paper_id: str) -> dict[str, Any] | None:
        return sqlite_manager.fetch_one(
            "SELECT * FROM papers WHERE paper_id = ?",
            (paper_id,),
        )

    def update_page_count(self, paper_id: str, page_count: int) -> dict[str, Any]:
        paper = self.get_paper_by_id(paper_id)
        if not paper:
            raise ValueError(f"试卷不存在: {paper_id}")

        now = datetime.now().isoformat(timespec="seconds")

        sqlite_manager.execute(
            """
            UPDATE papers
            SET page_count = ?, updated_at = ?
            WHERE paper_id = ?
            """,
            (page_count, now, paper_id)
        )

        updated_paper = self.get_paper_by_id(paper_id)
        logger.info("Paper page_count updated: paper_id=%s, page_count=%s", paper_id, page_count)
        return updated_paper


paper_service = PaperService()