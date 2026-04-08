from __future__ import annotations

import json
import traceback
from fastapi import APIRouter, Request, BackgroundTasks

from app.interfaces.feishu.feishu_event_parser import FeishuEventParser


router = APIRouter(prefix="/feishu", tags=["feishu"])
parser = FeishuEventParser()


def _event_exists(sqlite_manager, event_id: str) -> bool:
    row = sqlite_manager.fetch_one(
        """
        SELECT id, status
        FROM webhook_events
        WHERE event_key = ?
        """,
        (event_id,),
    )
    return row is not None


def _insert_event(sqlite_manager, event_id: str, event_type: str, detail_json: str) -> None:
    sqlite_manager.execute(
        """
        INSERT INTO webhook_events (
            event_key,
            event_type,
            status,
            task_id,
            detail_json,
            created_at,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        """,
        (event_id, event_type, "processing", None, detail_json),
    )


def _update_event_status(sqlite_manager, event_id: str, status: str, task_id: str | None = None, detail_json: str | None = None) -> None:
    sqlite_manager.execute(
        """
        UPDATE webhook_events
        SET status = ?, task_id = ?, detail_json = COALESCE(?, detail_json), updated_at = datetime('now')
        WHERE event_key = ?
        """,
        (status, task_id, detail_json, event_id),
    )


def _run_event(orchestrator, sqlite_manager, event_id: str, event):
    try:
        result = orchestrator.handle_event(event)
        _update_event_status(
            sqlite_manager,
            event_id=event_id,
            status="done",
            task_id=result.task_id,
            detail_json=json.dumps(
                {
                    "status": result.status,
                    "message": result.message,
                    "task_id": result.task_id,
                },
                ensure_ascii=False,
            ),
        )
    except Exception as e:
        traceback.print_exc()
        _update_event_status(
            sqlite_manager,
            event_id=event_id,
            status="failed",
            detail_json=json.dumps(
                {"error": str(e)},
                ensure_ascii=False,
            ),
        )


@router.post("/webhook")
async def feishu_webhook(request: Request, background_tasks: BackgroundTasks):
    body = await request.json()

    print("===== FEISHU WEBHOOK BODY START =====")
    print(json.dumps(body, ensure_ascii=False, indent=2))
    print("===== FEISHU WEBHOOK BODY END =====")

    # 飞书 challenge 校验
    if "challenge" in body:
        return {"challenge": body["challenge"]}

    sqlite_manager = request.app.state.sqlite_manager

    header = body.get("header", {})
    event_id = header.get("event_id")
    event_type = header.get("event_type", "")

    if not event_id:
        return {"status": "ignored", "reason": "missing_event_id"}

    # 去重：同一个 event_id 只处理一次
    if _event_exists(sqlite_manager, event_id):
        return {"status": "duplicate_ignored"}

    _insert_event(
        sqlite_manager,
        event_id=event_id,
        event_type=event_type,
        detail_json=json.dumps(body, ensure_ascii=False),
    )

    event = parser.parse(body)
    if not event:
        _update_event_status(
            sqlite_manager,
            event_id=event_id,
            status="ignored",
        )
        return {"status": "ignored"}

    print("Parsed AgentEvent:", event)

    orchestrator = request.app.state.orchestrator

    # 后台执行，先快速返回 200，防止飞书重试
    background_tasks.add_task(
        _run_event,
        orchestrator,
        sqlite_manager,
        event_id,
        event,
    )

    return {"status": "accepted"}