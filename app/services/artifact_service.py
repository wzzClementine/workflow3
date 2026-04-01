from datetime import datetime
from typing import Any

from app.db.sqlite_manager import sqlite_manager


class ArtifactService:
    def create_artifact(
        self,
        artifact_id: str,
        task_id: str,
        artifact_type: str,
        artifact_name: str,
        paper_id: str | None = None,
        local_path: str | None = None,
        remote_url: str | None = None,
        file_hash: str | None = None,
        status: str = "created",
        metadata_json: str | None = None,
    ) -> dict[str, Any] | None:
        now = datetime.now().isoformat(timespec="seconds")

        sqlite_manager.execute(
            """
            INSERT INTO artifacts (
                artifact_id,
                task_id,
                paper_id,
                artifact_type,
                artifact_name,
                local_path,
                remote_url,
                file_hash,
                status,
                metadata_json,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                artifact_id,
                task_id,
                paper_id,
                artifact_type,
                artifact_name,
                local_path,
                remote_url,
                file_hash,
                status,
                metadata_json,
                now,
                now,
            ),
        )

        return self.get_by_artifact_id(artifact_id)

    def get_by_artifact_id(self, artifact_id: str) -> dict[str, Any] | None:
        return sqlite_manager.fetch_one(
            """
            SELECT *
            FROM artifacts
            WHERE artifact_id = ?
            """,
            (artifact_id,),
        )

    def get_by_local_path(self, local_path: str) -> dict[str, Any] | None:
        return sqlite_manager.fetch_one(
            """
            SELECT *
            FROM artifacts
            WHERE local_path = ?
            """,
            (local_path,),
        )

    def list_by_task_id(self, task_id: str) -> list[dict[str, Any]]:
        return sqlite_manager.fetch_all(
            """
            SELECT *
            FROM artifacts
            WHERE task_id = ?
            ORDER BY id ASC
            """,
            (task_id,),
        )

    def list_by_task_and_type(
        self,
        task_id: str,
        artifact_type: str,
    ) -> list[dict[str, Any]]:
        return sqlite_manager.fetch_all(
            """
            SELECT *
            FROM artifacts
            WHERE task_id = ? AND artifact_type = ?
            ORDER BY id ASC
            """,
            (task_id, artifact_type),
        )

    def update_status(
        self,
        artifact_id: str,
        status: str,
    ) -> dict[str, Any] | None:
        now = datetime.now().isoformat(timespec="seconds")
        artifact = self.get_by_artifact_id(artifact_id)

        if not artifact:
            raise ValueError(f"artifact 不存在: {artifact_id}")

        sqlite_manager.execute(
            """
            UPDATE artifacts
            SET status = ?, updated_at = ?
            WHERE artifact_id = ?
            """,
            (status, now, artifact_id),
        )

        return self.get_by_artifact_id(artifact_id)

    def update_remote_url(
        self,
        artifact_id: str,
        remote_url: str | None,
    ) -> dict[str, Any] | None:
        now = datetime.now().isoformat(timespec="seconds")
        artifact = self.get_by_artifact_id(artifact_id)

        if not artifact:
            raise ValueError(f"artifact 不存在: {artifact_id}")

        sqlite_manager.execute(
            """
            UPDATE artifacts
            SET remote_url = ?, updated_at = ?
            WHERE artifact_id = ?
            """,
            (remote_url, now, artifact_id),
        )

        return self.get_by_artifact_id(artifact_id)

    def update_local_path(
        self,
        artifact_id: str,
        local_path: str | None,
    ) -> dict[str, Any] | None:
        now = datetime.now().isoformat(timespec="seconds")
        artifact = self.get_by_artifact_id(artifact_id)

        if not artifact:
            raise ValueError(f"artifact 不存在: {artifact_id}")

        sqlite_manager.execute(
            """
            UPDATE artifacts
            SET local_path = ?, updated_at = ?
            WHERE artifact_id = ?
            """,
            (local_path, now, artifact_id),
        )

        return self.get_by_artifact_id(artifact_id)

    def update_metadata(
        self,
        artifact_id: str,
        metadata_json: str | None,
    ) -> dict[str, Any] | None:
        now = datetime.now().isoformat(timespec="seconds")
        artifact = self.get_by_artifact_id(artifact_id)

        if not artifact:
            raise ValueError(f"artifact 不存在: {artifact_id}")

        sqlite_manager.execute(
            """
            UPDATE artifacts
            SET metadata_json = ?, updated_at = ?
            WHERE artifact_id = ?
            """,
            (metadata_json, now, artifact_id),
        )

        return self.get_by_artifact_id(artifact_id)

    def update_file_hash(
        self,
        artifact_id: str,
        file_hash: str | None,
    ) -> dict[str, Any] | None:
        now = datetime.now().isoformat(timespec="seconds")
        artifact = self.get_by_artifact_id(artifact_id)

        if not artifact:
            raise ValueError(f"artifact 不存在: {artifact_id}")

        sqlite_manager.execute(
            """
            UPDATE artifacts
            SET file_hash = ?, updated_at = ?
            WHERE artifact_id = ?
            """,
            (file_hash, now, artifact_id),
        )

        return self.get_by_artifact_id(artifact_id)

    def delete_artifact(self, artifact_id: str) -> None:
        artifact = self.get_by_artifact_id(artifact_id)

        if not artifact:
            raise ValueError(f"artifact 不存在: {artifact_id}")

        sqlite_manager.execute(
            """
            DELETE FROM artifacts
            WHERE artifact_id = ?
            """,
            (artifact_id,),
        )


artifact_service = ArtifactService()