from datetime import datetime
from typing import Any

from app.db.sqlite_manager import sqlite_manager


class AgentRunService:
    def create_run(
        self,
        run_id: str,
        chat_id: str,
        event_type: str,
        task_id: str | None = None,
        input_snapshot: str | None = None,
        retrieved_context: str | None = None,
        planner_prompt: str | None = None,
        planner_output_json: str | None = None,
        tool_calls_json: str | None = None,
        final_reply: str | None = None,
        status: str = "created",
        latency_ms: int | None = None,
        model_name: str | None = None,
    ) -> dict[str, Any] | None:
        now = datetime.now().isoformat(timespec="seconds")

        sqlite_manager.execute(
            """
            INSERT INTO agent_runs (
                run_id,
                chat_id,
                task_id,
                event_type,
                input_snapshot,
                retrieved_context,
                planner_prompt,
                planner_output_json,
                tool_calls_json,
                final_reply,
                status,
                latency_ms,
                model_name,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                chat_id,
                task_id,
                event_type,
                input_snapshot,
                retrieved_context,
                planner_prompt,
                planner_output_json,
                tool_calls_json,
                final_reply,
                status,
                latency_ms,
                model_name,
                now,
                now,
            ),
        )

        return self.get_by_run_id(run_id)

    def get_by_run_id(self, run_id: str) -> dict[str, Any] | None:
        return sqlite_manager.fetch_one(
            """
            SELECT *
            FROM agent_runs
            WHERE run_id = ?
            """,
            (run_id,),
        )

    def list_by_task_id(self, task_id: str) -> list[dict[str, Any]]:
        return sqlite_manager.fetch_all(
            """
            SELECT *
            FROM agent_runs
            WHERE task_id = ?
            ORDER BY id DESC
            """,
            (task_id,),
        )

    def list_by_chat_id(self, chat_id: str) -> list[dict[str, Any]]:
        return sqlite_manager.fetch_all(
            """
            SELECT *
            FROM agent_runs
            WHERE chat_id = ?
            ORDER BY id DESC
            """,
            (chat_id,),
        )

    def update_status(
        self,
        run_id: str,
        status: str,
    ) -> dict[str, Any] | None:
        now = datetime.now().isoformat(timespec="seconds")
        run = self.get_by_run_id(run_id)

        if not run:
            raise ValueError(f"agent run 不存在: {run_id}")

        sqlite_manager.execute(
            """
            UPDATE agent_runs
            SET status = ?, updated_at = ?
            WHERE run_id = ?
            """,
            (status, now, run_id),
        )

        return self.get_by_run_id(run_id)

    def update_retrieved_context(
        self,
        run_id: str,
        retrieved_context: str | None,
    ) -> dict[str, Any] | None:
        now = datetime.now().isoformat(timespec="seconds")
        run = self.get_by_run_id(run_id)

        if not run:
            raise ValueError(f"agent run 不存在: {run_id}")

        sqlite_manager.execute(
            """
            UPDATE agent_runs
            SET retrieved_context = ?, updated_at = ?
            WHERE run_id = ?
            """,
            (retrieved_context, now, run_id),
        )

        return self.get_by_run_id(run_id)

    def update_planner_prompt(
        self,
        run_id: str,
        planner_prompt: str | None,
    ) -> dict[str, Any] | None:
        now = datetime.now().isoformat(timespec="seconds")
        run = self.get_by_run_id(run_id)

        if not run:
            raise ValueError(f"agent run 不存在: {run_id}")

        sqlite_manager.execute(
            """
            UPDATE agent_runs
            SET planner_prompt = ?, updated_at = ?
            WHERE run_id = ?
            """,
            (planner_prompt, now, run_id),
        )

        return self.get_by_run_id(run_id)

    def update_planner_output(
        self,
        run_id: str,
        planner_output_json: str | None,
    ) -> dict[str, Any] | None:
        now = datetime.now().isoformat(timespec="seconds")
        run = self.get_by_run_id(run_id)

        if not run:
            raise ValueError(f"agent run 不存在: {run_id}")

        sqlite_manager.execute(
            """
            UPDATE agent_runs
            SET planner_output_json = ?, updated_at = ?
            WHERE run_id = ?
            """,
            (planner_output_json, now, run_id),
        )

        return self.get_by_run_id(run_id)

    def update_tool_calls(
        self,
        run_id: str,
        tool_calls_json: str | None,
    ) -> dict[str, Any] | None:
        now = datetime.now().isoformat(timespec="seconds")
        run = self.get_by_run_id(run_id)

        if not run:
            raise ValueError(f"agent run 不存在: {run_id}")

        sqlite_manager.execute(
            """
            UPDATE agent_runs
            SET tool_calls_json = ?, updated_at = ?
            WHERE run_id = ?
            """,
            (tool_calls_json, now, run_id),
        )

        return self.get_by_run_id(run_id)

    def update_final_reply(
        self,
        run_id: str,
        final_reply: str | None,
    ) -> dict[str, Any] | None:
        now = datetime.now().isoformat(timespec="seconds")
        run = self.get_by_run_id(run_id)

        if not run:
            raise ValueError(f"agent run 不存在: {run_id}")

        sqlite_manager.execute(
            """
            UPDATE agent_runs
            SET final_reply = ?, updated_at = ?
            WHERE run_id = ?
            """,
            (final_reply, now, run_id),
        )

        return self.get_by_run_id(run_id)

    def finish_run(
        self,
        run_id: str,
        status: str,
        latency_ms: int | None = None,
        final_reply: str | None = None,
    ) -> dict[str, Any] | None:
        now = datetime.now().isoformat(timespec="seconds")
        run = self.get_by_run_id(run_id)

        if not run:
            raise ValueError(f"agent run 不存在: {run_id}")

        sqlite_manager.execute(
            """
            UPDATE agent_runs
            SET status = ?,
                latency_ms = ?,
                final_reply = ?,
                updated_at = ?
            WHERE run_id = ?
            """,
            (status, latency_ms, final_reply, now, run_id),
        )

        return self.get_by_run_id(run_id)

    def update_tool_results(
        self,
        run_id: str,
        tool_results_json: str | None,
    ) -> dict[str, Any] | None:
        now = datetime.now().isoformat(timespec="seconds")
        run = self.get_by_run_id(run_id)

        if not run:
            raise ValueError(f"agent run 不存在: {run_id}")

        sqlite_manager.execute(
            """
            UPDATE agent_runs
            SET tool_results_json = ?, updated_at = ?
            WHERE run_id = ?
            """,
            (tool_results_json, now, run_id),
        )

        return self.get_by_run_id(run_id)

    def update_final_prompt(
        self,
        run_id: str,
        final_prompt: str | None,
    ) -> dict[str, Any] | None:
        now = datetime.now().isoformat(timespec="seconds")
        run = self.get_by_run_id(run_id)

        if not run:
            raise ValueError(f"agent run 不存在: {run_id}")

        sqlite_manager.execute(
            """
            UPDATE agent_runs
            SET final_prompt = ?, updated_at = ?
            WHERE run_id = ?
            """,
            (final_prompt, now, run_id),
        )

        return self.get_by_run_id(run_id)

    def update_final_output(
        self,
        run_id: str,
        final_output_json: str | None,
    ) -> dict[str, Any] | None:
        now = datetime.now().isoformat(timespec="seconds")
        run = self.get_by_run_id(run_id)

        if not run:
            raise ValueError(f"agent run 不存在: {run_id}")

        sqlite_manager.execute(
            """
            UPDATE agent_runs
            SET final_output_json = ?, updated_at = ?
            WHERE run_id = ?
            """,
            (final_output_json, now, run_id),
        )

        return self.get_by_run_id(run_id)


agent_run_service = AgentRunService()