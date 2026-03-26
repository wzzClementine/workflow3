import json
from typing import Any

from fastapi import APIRouter, Request
from fastapi import Query

from app.skills.task_update_status import task_update_status
from app.skills.send_feishu_message import send_feishu_message
from app.skills.task_create import task_create
from app.skills.file_store import (
    file_store_init_task_dirs,
    file_store_save_text,
)
from app.skills.import_pdf_to_workspace import import_pdf_to_workspace
from app.skills.render_pdf_pages import render_pdf_pages

from app.utils.logger import setup_logger
from app.config import settings

logger = setup_logger(settings.log_level, settings.logs_dir)

router = APIRouter(prefix="/feishu", tags=["feishu"])


@router.get("/ping")
def feishu_ping() -> dict:
    return {"message": "feishu route ready"}


@router.post("/event")
async def feishu_event(request: Request) -> dict[str, Any]:
    body = await request.json()
    logger.info("Feishu event received: %s", body)

    # 1) challenge 校验
    if "challenge" in body:
        return {"challenge": body["challenge"]}

    # 2) 解析事件
    header = body.get("header", {})
    event_type = header.get("event_type")

    if event_type != "im.message.receive_v1":
        logger.info("Ignored event_type: %s", event_type)
        return {"code": 0, "msg": "ignored"}

    event = body.get("event", {})
    message = event.get("message", {})
    sender = event.get("sender", {})
    chat_id = message.get("chat_id")
    message_type = message.get("message_type")
    content_raw = message.get("content", "{}")

    logger.info("Sender: %s", sender)
    logger.info("Chat ID: %s", chat_id)
    logger.info("Message type: %s", message_type)
    logger.info("Message raw content: %s", content_raw)

    if message_type != "text":
        if chat_id:
            send_feishu_message(chat_id, "目前只支持文本消息测试。")
        return {"code": 0, "msg": "ok"}

    try:
        content_obj = json.loads(content_raw)
        text = (content_obj.get("text") or "").strip()
    except Exception:
        text = ""

    logger.info("Parsed text: %s", text)

    if not chat_id:
        logger.warning("chat_id missing in event")
        return {"code": 0, "msg": "ok"}

    normalized_text = text.strip().lower()

    if normalized_text == "ping":
        send_feishu_message(chat_id, "workflow3 服务正常")

    elif normalized_text == "create task":
        user_id = None
        sender_id = sender.get("sender_id", {})
        if isinstance(sender_id, dict):
            user_id = (
                    sender_id.get("open_id")
                    or sender_id.get("user_id")
                    or sender_id.get("union_id")
            )

        task = task_create(created_by=user_id)

        reply_text = (
            "任务已创建\n"
            f"task_id: {task['task_id']}\n"
            f"status: {task['status']}\n"
            f"task_type: {task['task_type']}"
        )
        send_feishu_message(chat_id, reply_text)

    elif normalized_text.startswith("update task "):
        parts = text.strip().split()

        if len(parts) != 4:
            send_feishu_message(
                chat_id,
                "命令格式错误。\n正确格式：update task <task_id> <status>"
            )
            return {"code": 0, "msg": "ok"}

        _, _, task_id, status = parts
        status = status.strip().lower()

        try:
            task = task_update_status(task_id=task_id, status=status)
            reply_text = (
                "任务状态已更新\n"
                f"task_id: {task['task_id']}\n"
                f"status: {task['status']}"
            )
            send_feishu_message(chat_id, reply_text)
        except Exception as e:
            send_feishu_message(chat_id, f"任务状态更新失败：{e}")

    elif normalized_text.startswith("init file store "):
        parts = text.strip().split()

        if len(parts) != 4:
            send_feishu_message(
                chat_id,
                "命令格式错误。\n正确格式：init file store <task_id>"
            )
            return {"code": 0, "msg": "ok"}

        task_id = parts[3]

        try:
            dirs = file_store_init_task_dirs(task_id)
            reply_text = (
                "文件目录初始化成功\n"
                f"task_id: {task_id}\n"
                f"task_root: {dirs['task_root']}"
            )
            send_feishu_message(chat_id, reply_text)
        except Exception as e:
            send_feishu_message(chat_id, f"文件目录初始化失败：{e}")

    else:
        send_feishu_message(
            chat_id,
            "未识别命令。目前支持：ping / create task / update task <task_id> <status>"
        )

    return {"code": 0, "msg": "ok"}


@router.get("/file-store/init")
def file_store_init(task_id: str = Query(..., description="任务ID")) -> dict:
    dirs = file_store_init_task_dirs(task_id)
    return {
        "message": "file store init ok",
        "task_id": task_id,
        "dirs": {k: str(v) for k, v in dirs.items()},
    }

@router.get("/file-store/save-text")
def file_store_save_text_test(
    task_id: str = Query(..., description="任务ID"),
    category: str = Query(..., description="目录类别"),
    filename: str = Query(..., description="文件名"),
) -> dict:
    path = file_store_save_text(
        task_id=task_id,
        category=category,  # type: ignore
        filename=filename,
        content="这是一个 file_store 测试文本文件。",
    )
    return {
        "message": "file store save text ok",
        "task_id": task_id,
        "category": category,
        "filename": filename,
        "path": str(path),
    }

@router.get("/import-pdf-test")
def import_pdf_test(
    task_id: str = Query(..., description="任务ID"),
    pdf_local_path: str = Query(..., description="本地PDF路径"),
    paper_name: str = Query(..., description="试卷名称"),
    source_type: str = Query("blank", description="blank 或 solution"),
) -> dict[str, Any]:
    result = import_pdf_to_workspace(
        task_id=task_id,
        pdf_local_path=pdf_local_path,
        paper_name=paper_name,
        source_type=source_type,
    )
    return {
        "message": "import pdf ok",
        "result": result,
    }

@router.get("/render-pdf-pages-test")
def render_pdf_pages_test(
    task_id: str = Query(..., description="任务ID"),
    blank_pdf_path: str = Query(..., description="空白试卷PDF路径"),
    solution_pdf_path: str = Query(..., description="解析试卷PDF路径"),
    blank_paper_name: str = Query("空白试卷", description="空白试卷名称"),
    solution_paper_name: str = Query("解析试卷", description="解析试卷名称"),
    dpi: int = Query(200, description="渲染DPI"),
) -> dict[str, Any]:
    result = render_pdf_pages(
        task_id=task_id,
        blank_pdf_path=blank_pdf_path,
        solution_pdf_path=solution_pdf_path,
        blank_paper_name=blank_paper_name,
        solution_paper_name=solution_paper_name,
        dpi=dpi,
    )
    return {
        "message": "render pdf pages ok",
        "result": result,
    }


@router.get("/test-send")
def test_send(chat_id: str = Query(..., description="飞书聊天 chat_id")) -> dict[str, Any]:
    result = send_feishu_message(chat_id, "这是一条来自 /feishu/test-send 的测试消息")
    return {
        "message": "test send ok",
        "result": result,
    }

@router.get("/task-create-test")
def task_create_test(created_by: str = "local_test") -> dict[str, Any]:
    task = task_create(created_by=created_by)
    return {
        "message": "task create ok",
        "task": task,
    }

@router.get("/task-update-test")
def task_update_test(
    task_id: str = Query(..., description="任务ID"),
    status: str = Query(..., description="目标状态"),
) -> dict[str, Any]:
    task = task_update_status(task_id=task_id, status=status)
    return {
        "message": "task update ok",
        "task": task,
    }