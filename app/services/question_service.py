from datetime import datetime
from typing import Any

from app.db.sqlite_manager import sqlite_manager
from app.utils.logger import setup_logger
from app.config import settings

logger = setup_logger(settings.log_level, settings.logs_dir)


class QuestionService:
    def delete_questions_by_paper_id(self, paper_id: str) -> None:
        sqlite_manager.execute(
            "DELETE FROM questions WHERE paper_id = ?",
            (paper_id,),
        )
        logger.info("Questions deleted: paper_id=%s", paper_id)

    def upsert_question(
        self,
        paper_id: str,
        question_no: int,
        blank_image_path: str,
        solution_image_path: str,
        bbox_json: str | None = None,
        match_status: str = "matched",
        json_status: str = "pending",
    ) -> dict[str, Any] | None:
        now = datetime.now().isoformat(timespec="seconds")

        sqlite_manager.execute(
            """
            INSERT INTO questions (
                paper_id, question_no, blank_image_path, solution_image_path,
                bbox_json, match_status, json_status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(paper_id, question_no)
            DO UPDATE SET
                blank_image_path = excluded.blank_image_path,
                solution_image_path = excluded.solution_image_path,
                bbox_json = excluded.bbox_json,
                match_status = excluded.match_status,
                json_status = excluded.json_status,
                updated_at = excluded.updated_at
            """,
            (
                paper_id,
                question_no,
                blank_image_path,
                solution_image_path,
                bbox_json,
                match_status,
                json_status,
                now,
                now,
            ),
        )

        return sqlite_manager.fetch_one(
            """
            SELECT * FROM questions
            WHERE paper_id = ? AND question_no = ?
            """,
            (paper_id, question_no),
        )


question_service = QuestionService()