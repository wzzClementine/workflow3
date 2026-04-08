from __future__ import annotations

from app.infrastructure.db.sqlite_manager import SQLiteManager


def init_db_schema(sqlite_manager: SQLiteManager) -> None:
    with sqlite_manager.get_conn() as conn:
        cursor = conn.cursor()

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL UNIQUE,
            chat_id TEXT,
            status TEXT NOT NULL,
            current_stage TEXT NOT NULL,
            created_by TEXT,
            error_message TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT NOT NULL UNIQUE,
            current_task_id TEXT,
            current_mode TEXT DEFAULT 'idle',
            waiting_for TEXT,
            last_user_message TEXT,
            last_message_type TEXT,
            last_uploaded_file_name TEXT,
            last_uploaded_file_key TEXT,
            summary_memory TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS task_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id TEXT NOT NULL UNIQUE,
            task_id TEXT NOT NULL,
            file_role TEXT NOT NULL,
            file_name TEXT NOT NULL,
            file_ext TEXT,
            storage_type TEXT NOT NULL,
            local_path TEXT,
            remote_key TEXT,
            remote_url TEXT,
            page_count INTEGER,
            file_hash TEXT,
            status TEXT NOT NULL,
            metadata_json TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS task_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL UNIQUE,
            current_stage TEXT NOT NULL,
            completed_steps_json TEXT,
            files_summary_json TEXT,
            processing_summary TEXT,
            last_error TEXT,
            next_action_hint TEXT,
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
            final_prompt TEXT,
            final_output_json TEXT,
            final_reply TEXT,
            status TEXT NOT NULL,
            latency_ms INTEGER,
            model_name TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS delivery_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            delivery_id TEXT NOT NULL UNIQUE,
            task_id TEXT NOT NULL,
            delivery_status TEXT NOT NULL,
            delivery_folder_name TEXT,
            local_package_path TEXT,
            feishu_folder_token TEXT,
            remote_url TEXT,
            delivered_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
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