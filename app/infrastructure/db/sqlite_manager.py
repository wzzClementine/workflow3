from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator


class SQLiteManager:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.timeout_seconds = 30
        self.max_retries = 5
        self.retry_sleep_seconds = 0.2

    def _create_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self.db_path,
            timeout=self.timeout_seconds,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row

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

    def execute(self, sql: str, params: tuple = ()) -> None:
        def _op():
            with self.get_conn() as conn:
                conn.execute(sql, params)

        self._run_with_retry(_op)

    def executemany(self, sql: str, params_list: list[tuple]) -> None:
        def _op():
            with self.get_conn() as conn:
                conn.executemany(sql, params_list)

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