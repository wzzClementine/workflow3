from typing import Any

from app.services.feishu_service import feishu_service
from app.utils.logger import setup_logger
from app.config import settings

logger = setup_logger(settings.log_level, settings.logs_dir)


def send_feishu_message(
    receive_id: str,
    text: str,
    receive_id_type: str = "chat_id",
) -> dict[str, Any]:
    """
    统一的飞书消息发送 skill。
    后续所有业务 skill 都通过它发消息，而不是直接调用 feishu_service。
    """
    if not receive_id:
        raise ValueError("receive_id 不能为空")

    if not text or not text.strip():
        raise ValueError("发送文本不能为空")

    try:
        result = feishu_service.send_text_message(
            receive_id=receive_id,
            text=text,
            receive_id_type=receive_id_type,
        )
        logger.info(
            "send_feishu_message success. receive_id=%s, text=%s",
            receive_id,
            text,
        )
        return result
    except Exception as e:
        logger.exception(
            "send_feishu_message failed. receive_id=%s, text=%s, error=%s",
            receive_id,
            text,
            e,
        )
        raise