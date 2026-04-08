from __future__ import annotations

import json

from app.agent.schema import AgentEvent, UploadedFile


class FeishuEventParser:

    def parse(self, payload: dict) -> AgentEvent | None:
        header = payload.get("header", {})
        event_type = header.get("event_type")

        if event_type != "im.message.receive_v1":
            return None

        event = payload.get("event", {})
        message = event.get("message", {})

        message_type = message.get("message_type")
        chat_id = message.get("chat_id")
        message_id = message.get("message_id")

        raw_content = message.get("content", "{}")

        try:
            content = json.loads(raw_content)
        except Exception:
            content = {}

        # ===== 文本 =====
        if message_type == "text":
            text = content.get("text", "")
            agent_event = AgentEvent(
                chat_id=chat_id,
                event_type="text",
                user_message=text,
                files=[],
            )
            print("Parsed AgentEvent(text):", agent_event)
            return agent_event

        # ===== 文件 =====
        if message_type == "file":
            file_key = content.get("file_key")
            file_name = content.get("file_name")

            agent_event = AgentEvent(
                chat_id=chat_id,
                event_type="file_upload",
                user_message=None,
                files=[
                    UploadedFile(
                        file_name=file_name,
                        file_key=file_key,
                        message_id=message_id,
                        mime_type="application/pdf",
                    )
                ],
            )
            print("Parsed AgentEvent(file):", agent_event)
            return agent_event

        return None