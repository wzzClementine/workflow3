import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator

from app.config import settings
from app.utils.file_utils import ensure_dir


class SQLiteManager:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        ensure_dir(self.db_path.parent)

    @contextmanager
    def get_conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_db(self) -> None:
        with self.get_conn() as conn:
            cursor = conn.cursor()

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL UNIQUE,
                task_type TEXT NOT NULL,
                paper_id TEXT,
                status TEXT NOT NULL,
                input_path TEXT,
                output_path TEXT,
                error_message TEXT,
                created_by TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS papers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                paper_id TEXT NOT NULL UNIQUE,
                paper_name TEXT NOT NULL,
                source_type TEXT,
                raw_pdf_path TEXT,
                page_count INTEGER DEFAULT 0,
                json_path TEXT,
                publish_status TEXT DEFAULT 'draft',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                paper_id TEXT NOT NULL,
                question_no INTEGER NOT NULL,
                blank_image_path TEXT,
                solution_image_path TEXT,
                bbox_json TEXT,
                match_status TEXT DEFAULT 'pending',
                json_status TEXT DEFAULT 'pending',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(paper_id, question_no)
            )
            """)

    def execute(self, sql: str, params: tuple = ()) -> None:
        with self.get_conn() as conn:
            conn.execute(sql, params)

    def fetch_one(self, sql: str, params: tuple = ()) -> dict[str, Any] | None:
        with self.get_conn() as conn:
            row = conn.execute(sql, params).fetchone()
            return dict(row) if row else None

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        with self.get_conn() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [dict(row) for row in rows]


sqlite_manager = SQLiteManager(settings.sqlite_db_path_obj)