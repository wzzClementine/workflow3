from __future__ import annotations

from pathlib import Path

from app.config import settings
from app.agent.memory import MemoryFacade
from app.agent.planner import LLMPlanner
from app.agent.policies import ConfirmationPolicy
from app.agent.schema import AgentEvent, AgentResult
from app.agent.state import TaskState
from app.agent.tools import ToolCall, ToolExecutor
from app.services.task import TaskService
from app.services.session import ChatSessionService
from app.infrastructure.feishu import FeishuMessageSender


class AgentOrchestrator:
    def __init__(
        self,
        task_service: TaskService,
        chat_session_service: ChatSessionService,
        memory_facade: MemoryFacade,
        llm_planner: LLMPlanner,
        tool_executor: ToolExecutor,
        confirmation_policy: ConfirmationPolicy,
        feishu_message_sender: FeishuMessageSender,
    ):
        self.task_service = task_service
        self.chat_session_service = chat_session_service
        self.memory_facade = memory_facade
        self.llm_planner = llm_planner
        self.tool_executor = tool_executor
        self.confirmation_policy = confirmation_policy
        self.feishu_message_sender = feishu_message_sender

    def _run_planner_flow(
        self,
        event: AgentEvent,
        snapshot: dict,
        task_id: str | None,
    ) -> AgentResult:
        decision = self.llm_planner.plan(
            event=event,
            snapshot=snapshot,
        )

        tool_result = None

        if decision.should_call_tool and decision.tool_name:
            tool_call = ToolCall(
                tool_name=decision.tool_name,
                tool_args=decision.tool_args,
            )
            tool_result = self.tool_executor.execute(tool_call)
            snapshot = self.memory_facade.build_agent_snapshot(event.chat_id)

            if not tool_result.success:
                return AgentResult(
                    status="failed",
                    message=tool_result.message,
                    task_id=task_id,
                    snapshot=snapshot,
                )

        message = decision.reply
        if tool_result and tool_result.message:
            message = f"{decision.reply}\n\n{tool_result.message}"

        return AgentResult(
            status="ok",
            message=message,
            task_id=task_id,
            snapshot=snapshot,
        )

    def handle_event(
        self,
        event: AgentEvent,
    ) -> AgentResult:
        session = self.chat_session_service.ensure_session(event.chat_id)

        if event.event_type == "text":
            self.chat_session_service.update_last_message(
                chat_id=event.chat_id,
                last_user_message=event.user_message,
                last_message_type="text",
            )

        if event.event_type == "file_upload" and event.files:
            self.feishu_message_sender.send_text(
                event.chat_id,
                "📥 已接收文件，正在登记材料并下载到本地，请稍候。",
            )

            latest_file = event.files[-1]
            self.chat_session_service.update_last_uploaded_file(
                chat_id=event.chat_id,
                file_name=latest_file.file_name,
                file_key=latest_file.file_key,
            )

        current_task_id = session.get("current_task_id")

        # ===== 新增：如果 session 绑定的是旧任务终态，则先解绑 =====
        if current_task_id:
            bound_task = self.task_service.get_task(current_task_id)

            if bound_task and bound_task.get("status") in ["completed", "failed"]:
                # 旧任务保留为历史任务，但不再作为当前活跃任务使用
                self.chat_session_service.bind_task(
                    chat_id=event.chat_id,
                    task_id=None,  # 运行时允许 None，用于解绑当前 task
                )
                self.chat_session_service.update_summary_memory(
                    chat_id=event.chat_id,
                    summary_memory=f"已将终态任务 {current_task_id} 归档为历史任务，准备进入新任务会话",
                )

                current_task_id = None
                session = self.chat_session_service.get_session(event.chat_id) or session
        # ===== 新增结束 =====

        if not current_task_id:
            task = self.task_service.create_task(
                chat_id=event.chat_id,
                created_by="agent",
            )
            current_task_id = task["task_id"]

            self.chat_session_service.bind_task(
                chat_id=event.chat_id,
                task_id=current_task_id,
            )

            self.chat_session_service.update_summary_memory(
                chat_id=event.chat_id,
                summary_memory=f"已自动创建任务 {current_task_id}",
            )

        snapshot = self.memory_facade.build_agent_snapshot(event.chat_id)
        current_stage = snapshot.get("current_stage")

        # 1. 文件上传事件优先直走 ingest_materials
        if event.event_type == "file_upload" and event.files:
            tool_call = ToolCall(
                tool_name="ingest_materials",
                tool_args={
                    "task_id": current_task_id,
                    "files": [
                        {
                            "file_name": item.file_name,
                            "file_key": item.file_key,
                            "mime_type": item.mime_type,
                            "message_id": item.message_id,
                        }
                        for item in event.files
                    ],
                },
            )

            tool_result = self.tool_executor.execute(tool_call)
            snapshot = self.memory_facade.build_agent_snapshot(event.chat_id)

            return AgentResult(
                status="ok" if tool_result.success else "failed",
                message=tool_result.message,
                task_id=current_task_id,
                snapshot=snapshot,
            )

        # 2. waiting_confirmation 阶段优先处理“确认 / 驳回”
        if (
            current_stage == TaskState.WAITING_CONFIRMATION.value
            and event.event_type == "text"
        ):
            if self.confirmation_policy.is_confirm_message(event.user_message):
                self.feishu_message_sender.send_text(
                    event.chat_id,
                    "✅ 已收到确认，开始处理试卷。",
                )

                # 2.1 先推进到 processing
                stage_tool_call = ToolCall(
                    tool_name="manage_task",
                    tool_args={
                        "action": "advance_stage",
                        "task_id": current_task_id,
                        "target_stage": "processing",
                        "next_action_hint": "开始执行完整处理链",
                    },
                )

                stage_result = self.tool_executor.execute(stage_tool_call)
                if not stage_result.success:
                    snapshot = self.memory_facade.build_agent_snapshot(event.chat_id)
                    return AgentResult(
                        status="failed",
                        message=stage_result.message,
                        task_id=current_task_id,
                        snapshot=snapshot,
                    )

                self.chat_session_service.clear_waiting_for(event.chat_id)
                self.chat_session_service.update_summary_memory(
                    chat_id=event.chat_id,
                    summary_memory=f"用户已确认材料，任务 {current_task_id} 已进入 processing",
                )

                # ========= Step A: process_paper =========
                self.feishu_message_sender.send_text(
                    event.chat_id,
                    "🛠️ 正在执行 PDF 转图片、切题、切解析和清洗流程，请稍候。",
                )

                work_dir = str(settings.tasks_dir)

                process_tool_call = ToolCall(
                    tool_name="process_paper",
                    tool_args={
                        "task_id": current_task_id,
                        "work_dir": work_dir,
                    },
                )

                process_result = self.tool_executor.execute(process_tool_call)
                if not process_result.success:
                    snapshot = self.memory_facade.build_agent_snapshot(event.chat_id)
                    return AgentResult(
                        status="failed",
                        message=f"process_paper 执行失败：{process_result.message}",
                        task_id=current_task_id,
                        snapshot=snapshot,
                    )

                task_root = process_result.data.get("task_root")
                question_output_root = process_result.data.get("question_output_root")
                analysis_output_root = process_result.data.get("analysis_output_root")
                cleaned_output_root = process_result.data.get("cleaned_output_root")
                blank_pdf_path = process_result.data.get("blank_pdf_path")

                # ========= Step B: build_manifest =========
                self.feishu_message_sender.send_text(
                    event.chat_id,
                    "🧠 正在分析答案与知识点。",
                )

                manifest_path = str(Path(task_root) / "manifest" / "manifest.json")

                manifest_tool_call = ToolCall(
                    tool_name="build_manifest",
                    tool_args={
                        "task_id": current_task_id,
                        "question_root_dir": question_output_root,
                        "analysis_root_dir": analysis_output_root,
                        "cleaned_analysis_root_dir": cleaned_output_root,
                        "output_path": manifest_path,
                    },
                )

                manifest_result = self.tool_executor.execute(manifest_tool_call)
                if not manifest_result.success:
                    snapshot = self.memory_facade.build_agent_snapshot(event.chat_id)
                    return AgentResult(
                        status="failed",
                        message=f"build_manifest 执行失败：{manifest_result.message}",
                        task_id=current_task_id,
                        snapshot=snapshot,
                    )

                manifest_path = manifest_result.data.get("manifest_path", manifest_path)

                # ========= Step C: write_excel =========
                self.feishu_message_sender.send_text(
                    event.chat_id,
                    "📊 正在生成 Excel。",
                )

                excel_path = str(Path(task_root) / "excel" / f"{current_task_id}.xlsx")

                excel_tool_call = ToolCall(
                    tool_name="write_excel",
                    tool_args={
                        "task_id": current_task_id,
                        "manifest_path": manifest_path,
                        "output_path": excel_path,
                        "school": "",
                        "year": "",
                        "paper_note": "",
                    },
                )

                excel_result = self.tool_executor.execute(excel_tool_call)
                if not excel_result.success:
                    snapshot = self.memory_facade.build_agent_snapshot(event.chat_id)
                    return AgentResult(
                        status="failed",
                        message=f"write_excel 执行失败：{excel_result.message}",
                        task_id=current_task_id,
                        snapshot=snapshot,
                    )

                excel_path = excel_result.data.get("excel_path", excel_path)

                # ========= Step D: package_results =========
                self.feishu_message_sender.send_text(
                    event.chat_id,
                    "📦 正在整理交付文件夹。",
                )

                package_tool_call = ToolCall(
                    tool_name="package_results",
                    tool_args={
                        "task_id": current_task_id,
                        "task_root": str(settings.tasks_dir),
                        "excel_path": excel_path,
                        "question_dir": question_output_root,
                        "analysis_dir": analysis_output_root,
                        "cleaned_analysis_dir": cleaned_output_root,
                        "manifest_path": manifest_path,
                        "source_pdf_path": blank_pdf_path,
                    },
                )

                package_result = self.tool_executor.execute(package_tool_call)
                if not package_result.success:
                    snapshot = self.memory_facade.build_agent_snapshot(event.chat_id)
                    return AgentResult(
                        status="failed",
                        message=f"package_results 执行失败：{package_result.message}",
                        task_id=current_task_id,
                        snapshot=snapshot,
                    )

                local_package_path = package_result.data.get("local_package_path")
                if not local_package_path:
                    snapshot = self.memory_facade.build_agent_snapshot(event.chat_id)
                    return AgentResult(
                        status="failed",
                        message="package_results 成功但没有返回 local_package_path",
                        task_id=current_task_id,
                        snapshot=snapshot,
                    )

                # ========= Step E: deliver_results =========
                self.feishu_message_sender.send_text(
                    event.chat_id,
                    "☁️ 正在上传到飞书云文件夹。",
                )

                deliver_tool_call = ToolCall(
                    tool_name="deliver_results",
                    tool_args={
                        "task_id": current_task_id,
                        "local_package_path": local_package_path,
                    },
                )

                deliver_result = self.tool_executor.execute(deliver_tool_call)
                snapshot = self.memory_facade.build_agent_snapshot(event.chat_id)

                if not deliver_result.success:
                    return AgentResult(
                        status="failed",
                        message=f"deliver_results 执行失败：{deliver_result.message}",
                        task_id=current_task_id,
                        snapshot=snapshot,
                    )

                remote_url = (
                    deliver_result.data.get("record", {}) or {}
                ).get("remote_url") or (
                    deliver_result.data.get("upload_result", {}) or {}
                ).get("root_folder_url", "")

                self.chat_session_service.update_summary_memory(
                    chat_id=event.chat_id,
                    summary_memory=f"任务 {current_task_id} 已完成完整处理链并上传飞书",
                )

                self.feishu_message_sender.send_text(
                    event.chat_id,
                    f"🎉 处理完成，请查看交付结果。\n{remote_url}" if remote_url else "🎉 处理完成，请查看交付结果。",
                )

                return AgentResult(
                    status="ok",
                    message=(
                        "完整流程已执行完成：\n"
                        "- PDF 转图片\n"
                        "- 切题 / 切解析 / 清洗\n"
                        "- manifest 生成\n"
                        "- Excel 生成\n"
                        "- 交付目录打包\n"
                        "- 飞书云上传\n"
                        f"{'交付链接：' + remote_url if remote_url else ''}"
                    ),
                    task_id=current_task_id,
                    snapshot=snapshot,
                )

            if self.confirmation_policy.is_reject_message(event.user_message):
                tool_call = ToolCall(
                    tool_name="manage_task",
                    tool_args={
                        "action": "advance_stage",
                        "task_id": current_task_id,
                        "target_stage": "collecting_materials",
                        "next_action_hint": "等待用户重新上传或补充材料",
                    },
                )

                tool_result = self.tool_executor.execute(tool_call)
                self.chat_session_service.set_waiting_for(
                    event.chat_id,
                    "materials_upload",
                )
                self.chat_session_service.update_summary_memory(
                    chat_id=event.chat_id,
                    summary_memory=f"用户认为材料有问题，任务 {current_task_id} 已退回 collecting_materials",
                )

                snapshot = self.memory_facade.build_agent_snapshot(event.chat_id)

                return AgentResult(
                    status="ok" if tool_result.success else "failed",
                    message="好的，请重新上传或补充正确的 blank_pdf / solution_pdf。",
                    task_id=current_task_id,
                    snapshot=snapshot,
                )

            # 非确认/驳回文本：进入 planner
            snapshot = self.memory_facade.build_agent_snapshot(event.chat_id)
            return self._run_planner_flow(
                event=event,
                snapshot=snapshot,
                task_id=current_task_id,
            )

        # 3. collecting_materials 阶段：文本进入 planner；其他事件兜底
        if current_stage == TaskState.COLLECTING_MATERIALS.value:
            if event.event_type == "text":
                snapshot = self.memory_facade.build_agent_snapshot(event.chat_id)
                return self._run_planner_flow(
                    event=event,
                    snapshot=snapshot,
                    task_id=current_task_id,
                )

            return AgentResult(
                status="ok",
                message="请上传 blank_pdf 和 solution_pdf，我会继续处理。支持一次上传一个，也支持一次上传多个文件。",
                task_id=current_task_id,
                snapshot=snapshot,
            )

        # 4. processing 阶段：文本进入 planner；非文本事件保留原状态说明
        if current_stage == TaskState.PROCESSING.value:
            if event.event_type == "text":
                snapshot = self.memory_facade.build_agent_snapshot(event.chat_id)
                return self._run_planner_flow(
                    event=event,
                    snapshot=snapshot,
                    task_id=current_task_id,
                )

            task_memory = snapshot.get("task_memory") or {}
            processing_summary = task_memory.get("processing_summary") or "当前任务正在处理中。"
            next_action_hint = task_memory.get("next_action_hint") or ""

            status_text = processing_summary
            if next_action_hint:
                status_text += f"\n下一步：{next_action_hint}"

            return AgentResult(
                status="ok",
                message=status_text,
                task_id=current_task_id,
                snapshot=snapshot,
            )

        # 5. 其他阶段交给 planner
        snapshot = self.memory_facade.build_agent_snapshot(event.chat_id)
        return self._run_planner_flow(
            event=event,
            snapshot=snapshot,
            task_id=current_task_id,
        )