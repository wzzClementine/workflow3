from __future__ import annotations

import json
import traceback
from concurrent.futures import ThreadPoolExecutor

import lark_oapi as lark
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1

from app.config import settings
from app.interfaces.feishu.feishu_ws_adapter import parse_lark_ws_event
from app.main import build_app_components


def _event_exists(sqlite_manager, event_id: str) -> bool:
    if not event_id:
        return False

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


def _update_event_status(
    sqlite_manager,
    event_id: str,
    status: str,
    task_id: str | None = None,
    detail_json: str | None = None,
) -> None:
    sqlite_manager.execute(
        """
        UPDATE webhook_events
        SET status = ?, task_id = ?, detail_json = COALESCE(?, detail_json), updated_at = datetime('now')
        WHERE event_key = ?
        """,
        (status, task_id, detail_json, event_id),
    )


def _safe_send_text(feishu_message_sender, chat_id: str, text: str) -> None:
    try:
        feishu_message_sender.send_text(chat_id, text)
    except Exception:
        traceback.print_exc()


class FeishuWsRunner:
    def __init__(self):
        self.components = build_app_components()

        self.sqlite_manager = self.components["sqlite_manager"]
        self.orchestrator = self.components["orchestrator"]
        self.feishu_message_sender = self.components["feishu_message_sender"]

        # 关键：长连接回调线程只负责接收事件，业务流程放到后台线程执行。
        # 先用 1 个 worker，避免同一会话/同一 SQLite/同一任务目录发生并发写入。
        self.executor = ThreadPoolExecutor(max_workers=1)

    def _extract_event_meta(self, data: P2ImMessageReceiveV1) -> tuple[str, str, str]:
        event_id = ""
        event_type = "im.message.receive_v1"
        message_id = ""

        header = getattr(data, "header", None)
        if header is not None:
            event_id = getattr(header, "event_id", "") or ""
            event_type = getattr(header, "event_type", "") or event_type

        event_obj = getattr(data, "event", None)
        message = getattr(event_obj, "message", None) if event_obj else None
        if message is not None:
            message_id = getattr(message, "message_id", "") or ""

        if not event_id:
            event_id = message_id

        return event_id, event_type, message_id

    def _run_event(self, event_id: str, agent_event) -> None:
        try:
            result = self.orchestrator.handle_event(agent_event)

            # 和 HTTP webhook 保持一致：入口层发送最终 result.message。
            if getattr(result, "message", None):
                _safe_send_text(
                    self.feishu_message_sender,
                    agent_event.chat_id,
                    result.message,
                )

            _update_event_status(
                self.sqlite_manager,
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

            print(
                f"[FeishuWS] done: event_id={event_id}, "
                f"status={result.status}, task_id={result.task_id}"
            )

        except Exception as e:
            traceback.print_exc()

            try:
                _update_event_status(
                    self.sqlite_manager,
                    event_id=event_id,
                    status="failed",
                    detail_json=json.dumps(
                        {
                            "error": str(e),
                            "exception_type": type(e).__name__,
                        },
                        ensure_ascii=False,
                    ),
                )
            except Exception:
                traceback.print_exc()

            _safe_send_text(
                self.feishu_message_sender,
                agent_event.chat_id,
                "❌ 系统处理过程中发生异常，当前流程已停止。\n"
                "请稍后重试，或回复“当前任务状态”查看情况。",
            )

    def handle_message_receive(self, data: P2ImMessageReceiveV1) -> None:
        event_id = ""

        try:
            event_id, event_type, message_id = self._extract_event_meta(data)

            if not event_id:
                print("[FeishuWS] missing event_id and message_id, ignored")
                return

            if _event_exists(self.sqlite_manager, event_id):
                print(f"[FeishuWS] duplicate ignored: {event_id}")
                return

            try:
                detail_json = json.dumps(data.__dict__, ensure_ascii=False, default=str)
            except Exception:
                detail_json = str(data)

            _insert_event(
                self.sqlite_manager,
                event_id=event_id,
                event_type=event_type,
                detail_json=detail_json,
            )

            agent_event = parse_lark_ws_event(data)
            if not agent_event:
                _update_event_status(
                    self.sqlite_manager,
                    event_id=event_id,
                    status="ignored",
                )
                return

            print("Parsed WS AgentEvent:", agent_event)

            # 关键变化：不要在 WebSocket 回调线程里同步跑完整 Agent。
            self.executor.submit(
                self._run_event,
                event_id,
                agent_event,
            )

            print(
                f"[FeishuWS] accepted: event_id={event_id}, "
                f"type={agent_event.event_type}, message_id={message_id}"
            )

        except Exception:
            traceback.print_exc()

            if event_id:
                try:
                    _update_event_status(
                        self.sqlite_manager,
                        event_id=event_id,
                        status="failed",
                        detail_json=json.dumps(
                            {
                                "error": "failed before submitting background task",
                                "exception_type": "FeishuWsRunnerError",
                            },
                            ensure_ascii=False,
                        ),
                    )
                except Exception:
                    traceback.print_exc()

            try:
                event_obj = getattr(data, "event", None)
                message = getattr(event_obj, "message", None) if event_obj else None
                chat_id = getattr(message, "chat_id", None) if message else None

                if chat_id:
                    _safe_send_text(
                        self.feishu_message_sender,
                        chat_id,
                        "❌ 系统接收飞书事件时发生异常，当前流程未能启动。\n"
                        "请稍后重试。",
                    )
            except Exception:
                traceback.print_exc()

    def run(self) -> None:
        if not settings.feishu_app_id:
            raise RuntimeError("缺少 FEISHU_APP_ID")

        if not settings.feishu_app_secret:
            raise RuntimeError("缺少 FEISHU_APP_SECRET")

        event_handler = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(self.handle_message_receive)
            .build()
        )

        client = lark.ws.Client(
            settings.feishu_app_id,
            settings.feishu_app_secret,
            event_handler=event_handler,
            log_level=lark.LogLevel.INFO,
        )

        print("[FeishuWS] 长连接客户端启动中...")
        client.start()


def run_feishu_ws_client() -> None:
    runner = FeishuWsRunner()
    runner.run()