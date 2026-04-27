from __future__ import annotations

import json
import mimetypes
from typing import Any

from app.agent.schema import AgentEvent, UploadedFile


def _safe_json_loads(raw_content: Any) -> dict:
    if isinstance(raw_content, dict):
        return raw_content

    if not raw_content:
        return {}

    try:
        return json.loads(raw_content)
    except Exception:
        return {}


def parse_lark_ws_event(data: Any) -> AgentEvent | None:
    """
    将飞书长连接收到的 im.message.receive_v1 事件转换为项目内部 AgentEvent。

    目标：
    - 保持和 app/interfaces/feishu/feishu_event_parser.py 的输出一致
    - 复用现有 AgentOrchestrator，不改业务流程
    """

    event = getattr(data, "event", None)
    if event is None:
        print("[FeishuWSAdapter] missing event")
        return None

    message = getattr(event, "message", None)
    if message is None:
        print("[FeishuWSAdapter] missing message")
        return None

    message_type = getattr(message, "message_type", None)
    chat_id = getattr(message, "chat_id", None)
    message_id = getattr(message, "message_id", None)
    raw_content = getattr(message, "content", "{}")

    if not chat_id:
        print("[FeishuWSAdapter] missing chat_id")
        return None

    content = _safe_json_loads(raw_content)

    # ===== 文本 =====
    if message_type == "text":
        text = content.get("text", "")

        agent_event = AgentEvent(
            chat_id=chat_id,
            event_type="text",
            user_message=text,
            files=[],
        )

        print("Parsed WS AgentEvent(text):", agent_event)
        return agent_event

    # ===== 文件 =====
    if message_type == "file":
        file_key = content.get("file_key")
        file_name = content.get("file_name") or "unknown_file"

        if not file_key:
            print("[FeishuWSAdapter] file message missing file_key:", content)
            return None

        # 你的 HTTP parser 里固定写 application/pdf；
        # 这里稍微稳一点：优先根据文件名猜，猜不到再按 pdf 处理。
        mime_type = (
            content.get("mime_type")
            or mimetypes.guess_type(file_name)[0]
            or "application/pdf"
        )

        agent_event = AgentEvent(
            chat_id=chat_id,
            event_type="file_upload",
            user_message=None,
            files=[
                UploadedFile(
                    file_name=file_name,
                    file_key=file_key,
                    message_id=message_id,
                    mime_type=mime_type,
                )
            ],
        )

        print("Parsed WS AgentEvent(file):", agent_event)
        return agent_event

    print(f"[FeishuWSAdapter] unsupported message_type={message_type}, content={content}")
    return None