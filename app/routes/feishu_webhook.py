import json
import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Form, Query, Request, UploadFile

from app.config import settings
from app.services.agent_service import agent_service
from app.services.chat_session_service import chat_session_service
from app.services.webhook_event_service import webhook_event_service
from app.skills.file_store import (
    file_store_init_task_dirs,
    file_store_save_text,
)
from app.services.chat_task_binding_service import chat_task_binding_service

from app.skills.import_pdf_to_workspace import import_pdf_to_workspace
from app.skills.render_pdf_pages import render_pdf_pages
from app.skills.send_feishu_message import send_feishu_message
from app.skills.task_create import task_create
from app.skills.task_excel_upload import handle_excel_upload
from app.skills.task_update_status import task_update_status
from app.utils.download_file_from_feishu import download_file_from_feishu
from app.utils.logger import setup_logger

logger = setup_logger(settings.log_level, settings.logs_dir)

router = APIRouter(prefix="/feishu", tags=["feishu"])


@router.get("/ping")
def feishu_ping() -> dict:
    return {"message": "feishu route ready"}


def _resolve_task_id(chat_id: str) -> str | None:
    # 1. session
    session = chat_session_service.get_by_chat_id(chat_id)
    if session:
        task_id = session.get("current_task_id")
        if task_id:
            return task_id

    # 2. binding
    task_id = chat_task_binding_service.get_task_id(chat_id)
    if task_id:
        chat_session_service.update_current_task(chat_id, task_id)
        return task_id

    return None


@router.post("/event")
async def feishu_event(request: Request) -> dict[str, Any]:
    body = await request.json()
    logger.info("Feishu event received: %s", body)

    if "challenge" in body:
        return {"challenge": body["challenge"]}

    header = body.get("header", {})
    event_type = header.get("event_type")

    if event_type != "im.message.receive_v1":
        logger.info("Ignored event_type: %s", event_type)
        return {"code": 0, "msg": "ignored"}

    event = body.get("event", {})
    message = event.get("message", {})
    sender = event.get("sender", {})

    chat_id = message.get("chat_id")
    message_id = message.get("message_id")
    message_type = message.get("message_type")
    content_raw = message.get("content", "{}")

    logger.info("Sender: %s", sender)
    logger.info("Chat ID: %s", chat_id)
    logger.info("Message type: %s", message_type)
    logger.info("Message raw content: %s", content_raw)

    if not chat_id:
        logger.warning("chat_id missing in event")
        return {"code": 0, "msg": "ok"}

    try:
        content_obj = json.loads(content_raw)
    except Exception:
        content_obj = {}

    event_key = None

    try:
        # ----------------------------
        # 1) 文件消息：下载后统一交给 Agent
        # ----------------------------
        if message_type == "file":
            file_key = content_obj.get("file_key")
            file_name = content_obj.get("file_name") or "uploaded_file"

            if not file_key:
                send_feishu_message(chat_id, "文件消息缺少 file_key，无法处理。")
                return {"code": 0, "msg": "ok"}

            if not message_id:
                send_feishu_message(chat_id, "文件消息缺少 message_id，无法处理。")
                return {"code": 0, "msg": "ok"}

            event_key = f"feishu_msg:{message_id}"

            logger.info(
                "Start handling file message. event_key=%s, message_id=%s, file_key=%s, file_name=%s",
                event_key,
                message_id,
                file_key,
                file_name,
            )

            existing = webhook_event_service.get_by_event_key(event_key)
            if existing and existing.get("status") == "done":
                logger.info("Duplicate completed file event ignored: %s", event_key)
                return {"code": 0, "msg": "ok"}

            is_new, existing_event = webhook_event_service.begin_event_once(
                event_key=event_key,
                event_type="feishu_file_message",
                detail_json=json.dumps(
                    {
                        "chat_id": chat_id,
                        "message_id": message_id,
                        "file_key": file_key,
                        "file_name": file_name,
                    },
                    ensure_ascii=False,
                ),
            )

            if not is_new:
                logger.info(
                    "Duplicate file event ignored. event_key=%s, existing_status=%s",
                    event_key,
                    existing_event.get("status") if existing_event else None,
                )
                return {"code": 0, "msg": "ok"}

            temp_dir = Path("runtime_data/temp")
            temp_dir.mkdir(parents=True, exist_ok=True)
            download_path = temp_dir / file_name

            download_file_from_feishu(message_id, file_key, download_path)

            chat_session_service.update_last_uploaded_file(
                chat_id=chat_id,
                file_name=file_name,
                file_key=file_key,
            )

            task_id = _resolve_task_id(chat_id)

            agent_result = agent_service.handle_event(
                chat_id=chat_id,
                event_type="file",
                user_message=None,
                task_id=task_id,
                file_name=file_name,
                file_key=file_key,
            )

            webhook_event_service.update_event_status(
                event_key=event_key,
                status="done",
                task_id=task_id,
                detail_json=json.dumps(agent_result, ensure_ascii=False),
            )

            send_feishu_message(
                chat_id,
                agent_result.get("reply", "文件已接收，Agent 已处理。"),
            )
            return {"code": 0, "msg": "ok"}

        # ----------------------------
        # 2) 非文本且非文件
        # ----------------------------
        if message_type != "text":
            send_feishu_message(chat_id, "目前仅支持文本消息和文件消息。")
            return {"code": 0, "msg": "ok"}

        # ----------------------------
        # 3) 文本消息：统一交给 Agent
        # ----------------------------
        text = (content_obj.get("text") or "").strip()
        logger.info("Parsed text: %s", text)

        if not message_id:
            send_feishu_message(chat_id, "文本消息缺少 message_id，无法处理。")
            return {"code": 0, "msg": "ok"}

        event_key = f"feishu_msg:{message_id}"

        existing = webhook_event_service.get_by_event_key(event_key)
        if existing and existing.get("status") == "done":
            logger.info("Duplicate completed text event ignored: %s", event_key)
            return {"code": 0, "msg": "ok"}

        is_new, existing_event = webhook_event_service.begin_event_once(
            event_key=event_key,
            event_type="feishu_text_message",
            detail_json=json.dumps(
                {
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "text": text,
                },
                ensure_ascii=False,
            ),
        )

        if not is_new:
            logger.info(
                "Duplicate text event ignored. event_key=%s, existing_status=%s",
                event_key,
                existing_event.get("status") if existing_event else None,
            )
            return {"code": 0, "msg": "ok"}

        chat_session_service.update_last_message(
            chat_id=chat_id,
            message_type="text",
            message_text=text,
        )

        task_id = _resolve_task_id(chat_id)

        agent_result = agent_service.handle_event(
            chat_id=chat_id,
            event_type="text",
            user_message=text,
            task_id=task_id,
            file_name=None,
            file_key=None,
        )

        webhook_event_service.update_event_status(
            event_key=event_key,
            status="done",
            task_id=task_id,
            detail_json=json.dumps(agent_result, ensure_ascii=False),
        )

        send_feishu_message(
            chat_id,
            agent_result.get("reply", "Agent 已处理当前消息。"),
        )
        return {"code": 0, "msg": "ok"}


    except Exception as e:

        logger.exception("Feishu event handling failed: %s", e)

        error_text = str(e)

        if "无法从 LLM 输出中解析 JSON" in error_text:

            user_message = "抱歉，我刚才理解这条消息时出现了短暂异常。请再发一次“继续处理刚才那套试卷”。"

        else:

            user_message = f"消息处理失败：{e}"

        send_feishu_message(chat_id, user_message)

        return {"code": 0, "msg": "ok"}


# =========================
# 下面这些测试接口先保留
# =========================

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


@router.post("/upload-excel")
async def upload_excel(
    task_id: str = Form(...),
    file: UploadFile = Form(...),
):
    """
    保留旧测试接口，便于单独验证 Step10.4
    """
    try:
        tmp_dir = Path("runtime_data/temp")
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp_file_path = tmp_dir / file.filename

        with tmp_file_path.open("wb") as f:
            shutil.copyfileobj(file.file, f)

        result = handle_excel_upload(
            task_id=task_id,
            excel_local_path=str(tmp_file_path),
        )

        return result

    except Exception as e:
        return {
            "task_id": task_id,
            "status": "failed",
            "message": f"上传 Excel 或触发 Step10.4 失败: {e}",
        }