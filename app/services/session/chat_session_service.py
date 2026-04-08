from __future__ import annotations

from typing import Any

from app.repositories.session_repo import ChatSessionRepository


class ChatSessionService:
    def __init__(self, chat_session_repository: ChatSessionRepository):
        self.chat_session_repository = chat_session_repository

    def get_session(self, chat_id: str) -> dict[str, Any] | None:
        return self.chat_session_repository.get_by_chat_id(chat_id)

    def ensure_session(
        self,
        chat_id: str,
    ) -> dict[str, Any]:
        session = self.chat_session_repository.get_by_chat_id(chat_id)
        if session:
            return session

        created = self.chat_session_repository.upsert_session(
            chat_id=chat_id,
            current_task_id=None,
            current_mode="idle",
            waiting_for=None,
            summary_memory="会话已初始化",
        )

        if not created:
            raise ValueError(f"会话初始化失败: {chat_id}")

        return created

    def bind_task(
        self,
        chat_id: str,
        task_id: str,
    ) -> dict[str, Any]:
        self.ensure_session(chat_id)

        updated = self.chat_session_repository.upsert_session(
            chat_id=chat_id,
            current_task_id=task_id,
        )

        if not updated:
            raise ValueError(f"绑定 task 失败: chat_id={chat_id}, task_id={task_id}")

        return updated

    def set_waiting_for(
        self,
        chat_id: str,
        waiting_for: str | None,
    ) -> dict[str, Any]:
        self.ensure_session(chat_id)

        updated = self.chat_session_repository.update_waiting_for(chat_id, waiting_for)
        if not updated:
            raise ValueError(f"更新 waiting_for 失败: {chat_id}")

        return updated

    def update_last_message(
        self,
        chat_id: str,
        last_user_message: str | None,
        last_message_type: str | None,
    ) -> dict[str, Any]:
        self.ensure_session(chat_id)

        updated = self.chat_session_repository.upsert_session(
            chat_id=chat_id,
            last_user_message=last_user_message,
            last_message_type=last_message_type,
        )

        if not updated:
            raise ValueError(f"更新最近消息失败: {chat_id}")

        return updated

    def update_last_uploaded_file(
        self,
        chat_id: str,
        file_name: str | None,
        file_key: str | None,
    ) -> dict[str, Any]:
        self.ensure_session(chat_id)

        updated = self.chat_session_repository.upsert_session(
            chat_id=chat_id,
            last_uploaded_file_name=file_name,
            last_uploaded_file_key=file_key,
        )

        if not updated:
            raise ValueError(f"更新最近上传文件失败: {chat_id}")

        return updated

    def update_summary_memory(
        self,
        chat_id: str,
        summary_memory: str,
    ) -> dict[str, Any]:
        self.ensure_session(chat_id)

        updated = self.chat_session_repository.update_summary_memory(
            chat_id,
            summary_memory,
        )

        if not updated:
            raise ValueError(f"更新会话摘要失败: {chat_id}")

        return updated

    def clear_waiting_for(
        self,
        chat_id: str,
    ) -> dict[str, Any]:
        return self.set_waiting_for(chat_id, None)