import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator

from app.config import settings
from app.utils.file_utils import ensure_dir


class SQLiteManager:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        ensure_dir(self.db_path.parent)

        # 数据库锁等待时间（秒）
        self.timeout_seconds = 30
        # locked 重试次数
        self.max_retries = 5
        # 每次重试前等待秒数
        self.retry_sleep_seconds = 0.2

    def _create_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self.db_path,
            timeout=self.timeout_seconds,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row

        # 关键：改善 SQLite 并发读写能力
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute(f"PRAGMA busy_timeout={self.timeout_seconds * 1000};")

        return conn

    @contextmanager
    def get_conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = self._create_conn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _run_with_retry(self, func):
        last_error = None

        for attempt in range(self.max_retries):
            try:
                return func()
            except sqlite3.OperationalError as e:
                last_error = e
                error_text = str(e).lower()

                if "database is locked" in error_text or "database table is locked" in error_text:
                    if attempt < self.max_retries - 1:
                        time.sleep(self.retry_sleep_seconds * (attempt + 1))
                        continue

                raise

        if last_error:
            raise last_error

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
            CREATE TABLE IF NOT EXISTS chat_task_binding (
                chat_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
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

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS webhook_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_key TEXT NOT NULL UNIQUE,
                event_type TEXT,
                status TEXT NOT NULL,
                task_id TEXT,
                detail_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT NOT NULL UNIQUE,
                current_task_id TEXT,
                current_step TEXT,
                current_mode TEXT DEFAULT 'idle',
                last_user_message TEXT,
                last_message_type TEXT,
                last_uploaded_file_name TEXT,
                last_uploaded_file_key TEXT,
                waiting_for TEXT,
                summary_memory TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS artifacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                artifact_id TEXT NOT NULL UNIQUE,
                task_id TEXT NOT NULL,
                paper_id TEXT,
                artifact_type TEXT NOT NULL,
                artifact_name TEXT NOT NULL,
                local_path TEXT,
                remote_url TEXT,
                file_hash TEXT,
                status TEXT NOT NULL,
                metadata_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS agent_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL UNIQUE,
                chat_id TEXT NOT NULL,
                task_id TEXT,
                event_type TEXT NOT NULL,
                input_snapshot TEXT,
                retrieved_context TEXT,
                planner_prompt TEXT,
                planner_output_json TEXT,
                tool_calls_json TEXT,
                tool_results_json TEXT,
                final_reply TEXT,
                status TEXT NOT NULL,
                latency_ms INTEGER,
                model_name TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS task_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL UNIQUE,
                summary TEXT,
                state_snapshot_json TEXT,
                missing_materials_json TEXT,
                last_successful_tool TEXT,
                last_failed_tool TEXT,
                last_error_analysis TEXT,
                next_recommended_action TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """)

            # 兼容旧库：如果 agent_runs 之前已创建但没有 tool_results_json，则自动补列
            existing_columns = conn.execute("PRAGMA table_info(agent_runs)").fetchall()
            existing_column_names = {row["name"] for row in existing_columns}

            if "tool_results_json" not in existing_column_names:
                conn.execute("""
                ALTER TABLE agent_runs
                ADD COLUMN tool_results_json TEXT
                """)

    def execute(self, sql: str, params: tuple = ()) -> None:
        def _op():
            with self.get_conn() as conn:
                conn.execute(sql, params)

        self._run_with_retry(_op)

    def fetch_one(self, sql: str, params: tuple = ()) -> dict[str, Any] | None:
        def _op():
            with self.get_conn() as conn:
                row = conn.execute(sql, params).fetchone()
                return dict(row) if row else None

        return self._run_with_retry(_op)

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        def _op():
            with self.get_conn() as conn:
                rows = conn.execute(sql, params).fetchall()
                return [dict(row) for row in rows]

        return self._run_with_retry(_op)


sqlite_manager = SQLiteManager(settings.sqlite_db_path_obj)