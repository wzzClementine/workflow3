import json
from typing import Any

from fastapi import APIRouter, Request
from fastapi import Query

from fastapi import APIRouter, UploadFile, Form
from pathlib import Path
import shutil

from app.skills.task_update_status import task_update_status
from app.skills.send_feishu_message import send_feishu_message
from app.skills.task_create import task_create
from app.skills.file_store import (
    file_store_init_task_dirs,
    file_store_save_text,
)
from app.skills.import_pdf_to_workspace import import_pdf_to_workspace
from app.skills.render_pdf_pages import render_pdf_pages
from app.skills.task_excel_upload import handle_excel_upload

from app.utils.logger import setup_logger
from app.utils.download_file_from_feishu import download_file_from_feishu

from app.config import settings

from app.services.task_service import task_service
from app.services.webhook_event_service import webhook_event_service

logger = setup_logger(settings.log_level, settings.logs_dir)

router = APIRouter(prefix="/feishu", tags=["feishu"])


@router.get("/ping")
def feishu_ping() -> dict:
    return {"message": "feishu route ready"}


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

    # ----------------------------
    # 1) 先处理文件消息
    # ----------------------------
    if message_type == "file":
        try:
            file_key = content_obj.get("file_key")
            file_name = content_obj.get("file_name") or "uploaded.xlsx"
            message_id = message.get("message_id")

            if not file_key:
                send_feishu_message(chat_id, "文件消息缺少 file_key，无法处理。")
                return {"code": 0, "msg": "ok"}

            if not message_id:
                send_feishu_message(chat_id, "文件消息缺少 message_id，无法处理。")
                return {"code": 0, "msg": "ok"}

            # 1. 构造唯一事件键
            event_key = f"file:{message_id}:{file_key}"

            # 2. 去重：如果已经存在，直接忽略
            is_new, existing_event = webhook_event_service.begin_event_once(
                event_key=event_key,
                event_type="feishu_file_upload",
                detail_json=json.dumps(
                    {
                        "chat_id": chat_id,
                        "file_name": file_name,
                        "message_id": message_id,
                        "file_key": file_key,
                    },
                    ensure_ascii=False,
                ),
            )

            if not is_new:
                logger.info("Duplicate file event ignored: %s", event_key)

                # 这里不要重复触发 Step10.4
                # 可选：给用户发提示，也可以静默忽略
                send_feishu_message(chat_id, "检测到重复文件事件，已忽略。")
                return {"code": 0, "msg": "ok"}

            # 3. 获取最近 task
            task = task_service.get_latest_task()
            if not task:
                webhook_event_service.update_event_status(
                    event_key=event_key,
                    status="failed",
                    detail_json=json.dumps(
                        {"reason": "没有可用任务，请先 create task"},
                        ensure_ascii=False,
                    ),
                )
                send_feishu_message(chat_id, "还没有可用任务，请先发送 create task。")
                return {"code": 0, "msg": "ok"}

            task_id = task["task_id"]

            # 4. 下载到 temp（推荐）
            temp_dir = Path("runtime_data/temp")
            temp_dir.mkdir(parents=True, exist_ok=True)
            download_path = temp_dir / file_name

            download_file_from_feishu(message_id, file_key, download_path)

            # 5. 调用 Step10.4
            result = handle_excel_upload(
                task_id=task_id,
                excel_local_path=str(download_path),
            )

            # 6. 根据结果更新去重事件状态
            if result.get("step10_4_status") == "success":
                webhook_event_service.update_event_status(
                    event_key=event_key,
                    status="done",
                    task_id=task_id,
                    detail_json=json.dumps(result, ensure_ascii=False),
                )
                send_feishu_message(
                    chat_id,
                    f"Excel 上传成功，Step10.4 已完成。\n"
                    f"status: {result.get('step10_4_status')}\n"
                    f"message: {result.get('message')}"
                )
            else:
                webhook_event_service.update_event_status(
                    event_key=event_key,
                    status="failed",
                    task_id=task_id,
                    detail_json=json.dumps(result, ensure_ascii=False),
                )
                send_feishu_message(
                    chat_id,
                    f"Excel 已接收，但 Step10.4 执行失败。\n"
                    f"status: {result.get('step10_4_status')}\n"
                    f"message: {result.get('message')}"
                )

        except Exception as e:
            logger.exception("File message handling failed: %s", e)

            try:
                event_key = f"file:{message.get('message_id')}:{content_obj.get('file_key')}"
                existing = webhook_event_service.get_by_event_key(event_key)
                if existing:
                    webhook_event_service.update_event_status(
                        event_key=event_key,
                        status="failed",
                        detail_json=json.dumps(
                            {"error": str(e)},
                            ensure_ascii=False,
                        ),
                    )
            except Exception:
                logger.exception("Failed to update webhook event status after file error.")

            send_feishu_message(chat_id, f"Excel 处理失败：{e}")

        return {"code": 0, "msg": "ok"}

    # ----------------------------
    # 2) 再处理非文本消息
    # ----------------------------
    if message_type != "text":
        send_feishu_message(chat_id, "目前仅支持文本消息和 Excel 文件消息。")
        return {"code": 0, "msg": "ok"}

    # ----------------------------
    # 3) 文本消息处理
    # ----------------------------
    text = (content_obj.get("text") or "").strip()
    logger.info("Parsed text: %s", text)

    normalized_text = text.lower()

    if normalized_text == "ping":
        send_feishu_message(chat_id, "workflow3 服务正常")
        return {"code": 0, "msg": "ok"}

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
        return {"code": 0, "msg": "ok"}

    elif normalized_text.startswith("update task "):
        parts = text.split()

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

        return {"code": 0, "msg": "ok"}

    elif normalized_text.startswith("init file store "):
        parts = text.split()

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

        return {"code": 0, "msg": "ok"}

    else:
        send_feishu_message(
            chat_id,
            "未识别命令。目前支持：ping / create task / update task <task_id> <status> / Excel 文件上传"
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

@router.post("/upload-excel")
async def upload_excel(
    task_id: str = Form(...),
    file: UploadFile = Form(...)
):
    """
    飞书上传 Excel 触发 Step10.4
    Args:
        task_id: 当前任务 ID（可由系统创建后传给前端）
        file: 飞书上传的 Excel 文件
    Returns:
        dict: 执行结果
    """
    try:
        # 1. 临时保存 Excel 文件
        tmp_dir = Path("runtime_data/temp")
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp_file_path = tmp_dir / file.filename

        with tmp_file_path.open("wb") as f:
            shutil.copyfileobj(file.file, f)

        # 2. 调用 handle_excel_upload skill
        result = handle_excel_upload(task_id=task_id, excel_local_path=str(tmp_file_path))

        # 3. 返回结果给飞书
        return result

    except Exception as e:
        return {
            "task_id": task_id,
            "status": "failed",
            "message": f"上传 Excel 或触发 Step10.4 失败: {e}"
        }