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
from app.services.delivery import DeliveryService
from app.infrastructure.feishu import FeishuMessageSender


class AgentOrchestrator:
    CANCEL_KEYWORDS = {
        "取消",
        "取消任务",
        "取消这个任务",
        "不要这个了",
        "停止处理",
        "停止",
        "先别做了",
        "算了",
    }

    RESTART_KEYWORDS = {
        "重新开始",
        "新建一个任务",
        "从头再来",
        "从头开始",
        "重来",
    }

    RESULT_QUERY_KEYWORDS = {
        "结果",
        "下载链接",
        "结果给我",
        "再发我一次",
        "刚刚那个结果",
        "结果在哪",
        "上一个任务结果",
        "上一个任务的结果",
        "最近一次结果",
        "最近一次处理结果",
    }

    CURRENT_TASK_STATUS_QUERY_KEYWORDS = {
        "当前任务是哪个",
        "我当前任务是哪个",
        "当前任务是什么",
        "我当前任务是什么",
        "现在在处理哪个任务",
        "当前在处理哪个任务",
        "当前任务是哪一个",
        "当前处理的是哪个任务",
        "当前任务情况",
        "当前任务状态",
        "现在任务是什么",
        "现在处理到哪个任务",
    }

    CURRENT_TASK_RESULT_QUERY_KEYWORDS = {
        "当前任务结果",
        "当前任务的结果",
        "当前任务下载链接",
        "当前任务的下载链接",
        "这个任务的结果",
        "这个任务结果",
        "这个任务的下载链接",
        "这个任务下载链接",
        "把这个任务的结果给我",
        "把这个任务的下载链接给我",
        "把他的下载链接给我",
        "把它的下载链接给我",
        "他的下载链接",
        "它的下载链接",
        "当前任务访问链接",
        "当前任务的访问链接",
        "这个任务的访问链接",
    }

    MISSING_MATERIALS_QUERY_KEYWORDS = {
        "哪些任务还缺材料",
        "哪些任务缺材料",
        "有哪些任务还缺材料",
        "有哪些任务缺材料",
        "目前有哪些任务还缺材料",
        "当前有哪些任务还缺材料",
        "我目前有哪些任务缺材料",
        "还有哪些任务缺材料",
        "有哪些任务没传完",
        "哪些任务没传完",
    }

    CANCEL_EMPTY_TASKS_KEYWORDS = {
        "把没有上传任何材料的任务都取消掉",
        "把没有上传任何材料的任务全部取消掉",
        "把什么材料都没有上传的任务都取消掉",
        "把什么材料都没有上传的任务全部取消掉",
        "把空任务都取消掉",
        "把空任务全部取消掉",
        "把没上传材料的任务都取消掉",
        "把没上传材料的任务全部取消掉",
    }

    CANCEL_MISSING_TASKS_KEYWORDS = {
        "把缺材料的任务都取消掉",
        "把缺材料的任务全部取消掉",
        "把待补材料任务都取消掉",
        "把待补材料任务全部取消掉",
        "把上面这些任务都取消掉",
        "把上面这些任务全部取消掉",
        "把上面这三个任务都取消掉",
        "上面这三个任务都取消掉",
        "上面这些任务都取消掉",
    }

    COMPLETED_TASK_LINK_QUERY_KEYWORDS = {
        "完成任务的访问链接",
        "已完成任务的访问链接",
        "已完成任务的下载链接",
        "已完成任务的文件链接",
        "完成任务的下载链接",
        "完成任务的文件链接",
        "他们的文件链接",
        "他们的访问链接",
        "刚才那些已完成任务的链接",
        "给我完成任务的访问链接",
        "我想要他们的文件链接",
        "我要他们的文件链接",
        "我要已完成任务的链接",
    }

    CURRENT_TASK_RERUN_EXCEL_KEYWORDS = {
        "当前任务只重新生成excel",
        "当前任务重新生成excel",
        "当前任务重跑excel",
        "当前任务只重跑excel",
        "当前任务重新做excel",
        "当前任务更新excel",
        "当前任务重新导出excel",
        "当前任务重做excel",
        "当前任务重新生成 Excel",
        "当前任务重跑 Excel",
        "当前任务只重跑 Excel",
        "当前任务重新做 Excel",
        "当前任务只重新生成 Excel",
        "当前任务更新 Excel",
        "当前任务重新导出 Excel",
        "当前任务重做 Excel",
        "重新生成Excel吧",
        "重新生成Excel",
        "重新导出Excel",
        "重做Excel",
    }

    CURRENT_TASK_REPACKAGE_KEYWORDS = {
        "当前任务只重新打包",
        "当前任务重新打包",
        "当前任务重跑打包",
        "当前任务重新打包一下",
        "当前任务重新整理打包",
        "当前任务重新生成交付包",
        "当前任务重新整理结果",
        "重新打包吧",
        "重新打包",
        "重新整理打包",
        "重新生成交付包",
    }

    CURRENT_TASK_REDELIVER_KEYWORDS = {
        "当前任务只重新上传结果",
        "当前任务重新上传结果",
        "当前任务重新上传",
        "当前任务重跑上传",
        "当前任务重新上传到飞书",
        "当前任务重新上传最新结果",
        "当前任务重新交付",
        "重新上传吧",
        "重新上传",
        "上传结果",
        "上传最新结果",
        "重新交付",
    }

    LATEST_COMPLETED_REDELIVER_KEYWORDS = {
        "把最近完成的任务重新上传",
        "把刚才完成的那个任务重新上传",
        "最近一次已完成任务重新上传结果",
        "最近完成任务重新上传",
        "把最近完成的任务重新上传结果",
    }

    CURRENT_TASK_RERUN_MANIFEST_KEYWORDS = {
        "当前任务只重新生成manifest",
        "当前任务重新生成manifest",
        "当前任务重跑manifest",
        "当前任务只重跑manifest",
        "当前任务重新构建manifest",
        "当前任务重新生成 manifest",
        "当前任务重跑 manifest",
        "当前任务只重跑 manifest",
        "当前任务重新构建 manifest",
        "当前任务重新生成清单",
        "当前任务重建清单",
        "重新生成manifest",
        "重新生成manifest",
        "重跑manifest",
        "只重跑manifest",
        "重新构建manifest",
        "重新生成 manifest",
        "重跑 manifest",
        "只重跑 manifest",
        "重新构建 manifest",
        "重新生成清单",
        "重建清单",
    }

    CURRENT_TASK_RERUN_ANALYSIS_KEYWORDS = {
        "当前任务重新分析答案和知识点",
        "当前任务只重新分析答案和知识点",
        "当前任务重新识别答案和知识点",
        "当前任务只重新识别答案和知识点",
        "当前任务重新分析答案",
        "当前任务重新分析知识点",
        "当前任务重跑答案和知识点分析",

        # 兼容旧说法
        "当前任务重新提取答案和知识点",
        "当前任务只重新提取答案和知识点",
        "当前任务重跑答案和知识点",
        "当前任务只重新提取答案",
        "当前任务重新提取答案",
        "当前任务重新提取知识点",
        "当前任务重新识别答案",
        "当前任务重新识别知识点",

        # 不带“当前任务”的宽松兼容
        "重新分析答案和知识点",
        "只重新分析答案和知识点",
        "重新识别答案和知识点",
        "只重新识别答案和知识点",
        "重新分析答案",
        "重新分析知识点",
        "重跑答案和知识点分析",
        "重新提取答案和知识点",
        "只重新提取答案和知识点",
        "重跑答案和知识点",
        "重新提取答案",
        "重新提取知识点",
        "重新识别答案",
        "重新识别知识点",
    }

    CURRENT_TASK_RERUN_CUT_KEYWORDS = {
        "当前任务重新切题",
        "当前任务重跑切题",
        "当前任务重新切图",
        "当前任务重新解析试卷结构",
        "当前任务重新解析结构",
        "当前任务重新切割题目",
        "当前任务重新分题",
        "当前任务重新切分题目",
        "重新切题",
        "重跑切题",
        "重新切图",
        "重新解析试卷结构",
        "重新解析结构",
        "重新切割题目",
        "重新分题",
        "重新切分题目",
    }

    TERMINAL_STATUSES = {
        TaskState.COMPLETED.value,
        TaskState.FAILED.value,
        TaskState.CANCELLED.value,
    }

    MATERIAL_EDITABLE_STAGES = {
        TaskState.COLLECTING_MATERIALS.value,
        TaskState.WAITING_CONFIRMATION.value,
    }

    NEW_TASK_ON_UPLOAD_STAGES = {
        TaskState.PROCESSING.value,
        TaskState.DELIVERING.value,
        TaskState.COMPLETED.value,
        TaskState.FAILED.value,
        TaskState.CANCELLED.value,
    }

    def __init__(
        self,
        task_service: TaskService,
        chat_session_service: ChatSessionService,
        memory_facade: MemoryFacade,
        llm_planner: LLMPlanner,
        tool_executor: ToolExecutor,
        confirmation_policy: ConfirmationPolicy,
        feishu_message_sender: FeishuMessageSender,
        delivery_service: DeliveryService,
    ):
        self.task_service = task_service
        self.chat_session_service = chat_session_service
        self.memory_facade = memory_facade
        self.llm_planner = llm_planner
        self.tool_executor = tool_executor
        self.confirmation_policy = confirmation_policy
        self.feishu_message_sender = feishu_message_sender
        self.delivery_service = delivery_service

    def _get_task_display_name(self, task_id: str | None) -> str:
        return self.memory_facade.get_task_display_name(task_id)

    def _with_task_prefix(self, task_id: str | None, text: str) -> str:
        display_name = self._get_task_display_name(task_id)
        return f"【{display_name}】{text}"

    def _send_task_text(
        self,
        chat_id: str,
        task_id: str | None,
        text: str,
    ) -> None:
        self.feishu_message_sender.send_text(
            chat_id,
            self._with_task_prefix(task_id, text),
        )

    def _get_task_root(self, task_id: str) -> Path:
        return Path(settings.tasks_dir) / task_id

    def _get_task_artifact_paths(self, task_id: str) -> dict[str, Path]:
        task_root = self._get_task_root(task_id)

        return {
            "task_root": task_root,
            "manifest_path": task_root / "manifest" / "manifest.json",
            "excel_path": task_root / "excel" / f"{task_id}.xlsx",
            "question_dir": task_root / "question_images",
            "analysis_dir": task_root / "analysis_images",
            "cleaned_analysis_dir": task_root / "cleaned_analysis_images",
        }

    def _require_path(
            self,
            path: Path,
            error_message: str,
    ) -> str | None:
        if not path.exists():
            return error_message
        return None

    def _get_task_material_paths(self, task_id: str) -> tuple[str, str]:
        task_root = self._get_task_root(task_id)
        uploads_dir = task_root / "uploads"

        if not uploads_dir.exists():
            return "", ""

        pdf_files = [p for p in uploads_dir.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"]

        blank_pdf_path = ""
        solution_pdf_path = ""

        for p in pdf_files:
            name = p.name.lower()

            # 解析 / 答案 / solution 视为解析PDF
            if ("解析" in p.name) or ("answer" in name) or ("solution" in name):
                if not solution_pdf_path:
                    solution_pdf_path = str(p)
            else:
                # 其余 PDF 默认视为空白试卷 PDF
                if not blank_pdf_path:
                    blank_pdf_path = str(p)

        return blank_pdf_path, solution_pdf_path

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

    def _is_cancel_message(self, text: str | None) -> bool:
        if not text:
            return False
        normalized = text.strip().lower()
        return any(keyword in normalized for keyword in self.CANCEL_KEYWORDS)

    def _is_restart_message(self, text: str | None) -> bool:
        if not text:
            return False
        normalized = text.strip().lower()
        return any(keyword in normalized for keyword in self.RESTART_KEYWORDS)

    def _is_current_task_result_query(self, text: str | None) -> bool:
        if not text:
            return False
        normalized = text.strip().lower()
        return any(keyword in normalized for keyword in self.CURRENT_TASK_RESULT_QUERY_KEYWORDS)

    def _is_result_query(self, text: str | None) -> bool:
        if not text:
            return False
        normalized = text.strip().lower()
        return any(keyword in normalized for keyword in self.RESULT_QUERY_KEYWORDS)

    def _is_missing_materials_query(self, text: str | None) -> bool:
        if not text:
            return False
        normalized = text.strip().lower()
        return any(keyword in normalized for keyword in self.MISSING_MATERIALS_QUERY_KEYWORDS)

    def _is_cancel_empty_tasks_message(self, text: str | None) -> bool:
        if not text:
            return False
        normalized = text.strip().lower()
        return any(keyword in normalized for keyword in self.CANCEL_EMPTY_TASKS_KEYWORDS)

    def _is_cancel_missing_tasks_message(self, text: str | None) -> bool:
        if not text:
            return False
        normalized = text.strip().lower()
        return any(keyword in normalized for keyword in self.CANCEL_MISSING_TASKS_KEYWORDS)

    def _is_completed_task_link_query(self, text: str | None) -> bool:
        if not text:
            return False
        normalized = text.strip().lower()
        return any(keyword in normalized for keyword in self.COMPLETED_TASK_LINK_QUERY_KEYWORDS)

    def _is_current_task_rerun_excel_query(self, text: str | None) -> bool:
        if not text:
            return False
        normalized = text.strip().lower()
        return any(keyword in normalized for keyword in self.CURRENT_TASK_RERUN_EXCEL_KEYWORDS)

    def _is_current_task_repackage_query(self, text: str | None) -> bool:
        if not text:
            return False
        normalized = text.strip().lower()
        return any(keyword in normalized for keyword in self.CURRENT_TASK_REPACKAGE_KEYWORDS)

    def _is_current_task_redeliver_query(self, text: str | None) -> bool:
        if not text:
            return False
        normalized = text.strip().lower()
        return any(keyword in normalized for keyword in self.CURRENT_TASK_REDELIVER_KEYWORDS)

    def _is_latest_completed_redeliver_query(self, text: str | None) -> bool:
        if not text:
            return False
        normalized = text.strip().lower()
        return any(keyword in normalized for keyword in self.LATEST_COMPLETED_REDELIVER_KEYWORDS)

    def _is_current_task_rerun_manifest_query(self, text: str | None) -> bool:
        if not text:
            return False
        normalized = text.strip().lower()
        return any(keyword in normalized for keyword in self.CURRENT_TASK_RERUN_MANIFEST_KEYWORDS)

    def _is_current_task_rerun_analysis_query(self, text: str | None) -> bool:
        if not text:
            return False
        normalized = text.strip().lower()
        return any(keyword in normalized for keyword in self.CURRENT_TASK_RERUN_ANALYSIS_KEYWORDS)

    def _is_current_task_rerun_cut_query(self, text: str | None) -> bool:
        if not text:
            return False
        normalized = text.strip().lower()
        return any(keyword in normalized for keyword in self.CURRENT_TASK_RERUN_CUT_KEYWORDS)

    def _is_current_task_status_query(self, text: str | None) -> bool:
        if not text:
            return False
        normalized = text.strip().lower()
        return any(keyword in normalized for keyword in self.CURRENT_TASK_STATUS_QUERY_KEYWORDS)

    def _handle_cancel_current_task(
        self,
        chat_id: str,
        task_id: str | None,
    ) -> AgentResult:
        if not task_id:
            snapshot = self.memory_facade.build_agent_snapshot(chat_id)
            return AgentResult(
                status="ok",
                message="当前没有进行中的任务可取消。",
                task_id=None,
                snapshot=snapshot,
            )

        self.task_service.mark_cancelled(task_id)
        self.chat_session_service.unbind_task(chat_id)
        self.chat_session_service.clear_waiting_for(chat_id)
        self.chat_session_service.update_summary_memory(
            chat_id=chat_id,
            summary_memory=f"已取消当前任务 {task_id}，当前会话无进行中的任务",
        )

        snapshot = self.memory_facade.build_agent_snapshot(chat_id)

        return AgentResult(
            status="ok",
            message="好的，当前任务已取消。现在没有进行中的任务了。如需继续，你可以重新开始，或重新上传材料。",
            task_id=None,
            snapshot=snapshot,
        )

    def _handle_cancel_empty_tasks(
        self,
        chat_id: str,
        current_task_id: str | None,
    ) -> AgentResult:
        empty_tasks = self.memory_facade.list_empty_material_tasks(chat_id)
        snapshot = self.memory_facade.build_agent_snapshot(chat_id)

        if not empty_tasks:
            return AgentResult(
                status="ok",
                message="当前没有未上传任何材料的空任务可取消。",
                task_id=current_task_id,
                snapshot=snapshot,
            )

        cancelled_ids: list[str] = []
        for item in empty_tasks:
            task_id = item.get("task_id")
            if not task_id:
                continue
            self.task_service.mark_cancelled(task_id)
            cancelled_ids.append(task_id)

        if current_task_id in cancelled_ids:
            self.chat_session_service.unbind_task(chat_id)
            self.chat_session_service.clear_waiting_for(chat_id)

        snapshot = self.memory_facade.build_agent_snapshot(chat_id)

        return AgentResult(
            status="ok",
            message=f"好的，已取消 {len(cancelled_ids)} 个未上传任何材料的空任务。",
            task_id=None if current_task_id in cancelled_ids else current_task_id,
            snapshot=snapshot,
        )

    def _handle_cancel_missing_tasks(
        self,
        chat_id: str,
        current_task_id: str | None,
    ) -> AgentResult:
        missing_tasks = self.memory_facade.list_missing_material_tasks(chat_id)
        snapshot = self.memory_facade.build_agent_snapshot(chat_id)

        if not missing_tasks:
            return AgentResult(
                status="ok",
                message="当前没有仍然缺材料的任务可取消。",
                task_id=current_task_id,
                snapshot=snapshot,
            )

        cancelled_ids: list[str] = []
        for item in missing_tasks:
            task_id = item.get("task_id")
            if not task_id:
                continue
            self.task_service.mark_cancelled(task_id)
            cancelled_ids.append(task_id)

        if current_task_id in cancelled_ids:
            self.chat_session_service.unbind_task(chat_id)
            self.chat_session_service.clear_waiting_for(chat_id)

        snapshot = self.memory_facade.build_agent_snapshot(chat_id)

        return AgentResult(
            status="ok",
            message=f"好的，已取消 {len(cancelled_ids)} 个缺材料任务。",
            task_id=None if current_task_id in cancelled_ids else current_task_id,
            snapshot=snapshot,
        )

    def _build_current_task_no_result_message(
        self,
        snapshot: dict,
    ) -> str:
        current_task_summary = snapshot.get("current_task_summary") or {}
        latest_materials_summary = current_task_summary.get("latest_materials_summary") or {}
        stage = current_task_summary.get("stage")
        status = current_task_summary.get("status")

        has_blank = latest_materials_summary.get("has_blank_pdf")
        has_solution = latest_materials_summary.get("has_solution_pdf")

        if status == TaskState.CANCELLED.value:
            return "当前任务已取消，因此没有可获取的处理结果。"

        if status == TaskState.FAILED.value:
            return "当前任务执行失败，因此暂时没有可获取的处理结果。"

        if stage == TaskState.COLLECTING_MATERIALS.value:
            if has_blank and not has_solution:
                return (
                    "当前任务还没有可获取的处理结果。\n"
                    "目前该任务仍处于材料收集阶段，已上传试卷 PDF，但还缺答案解析 PDF。"
                    "请继续上传缺失材料，处理完成后我再把下载链接发给你。"
                )
            if has_solution and not has_blank:
                return (
                    "当前任务还没有可获取的处理结果。\n"
                    "目前该任务仍处于材料收集阶段，已上传答案解析 PDF，但还缺空白试卷 PDF。"
                    "请继续上传缺失材料，处理完成后我再把下载链接发给你。"
                )
            return (
                "当前任务还没有可获取的处理结果。\n"
                "目前该任务仍处于材料收集阶段，请先上传完整材料并完成处理。"
            )

        if stage == TaskState.WAITING_CONFIRMATION.value:
            return (
                "当前任务还没有可获取的处理结果。\n"
                "目前材料已经收齐，但你还没有确认开始处理。回复“开始”后，处理完成我再把下载链接发给你。"
            )

        if stage == TaskState.PROCESSING.value:
            return "当前任务正在处理中，暂时还没有可获取的下载链接。处理完成后我会返回结果。"

        if stage == TaskState.DELIVERING.value:
            return "当前任务正在上传交付结果，暂时还没有可获取的下载链接。上传完成后我会返回结果。"

        return "当前任务还没有可获取的处理结果，请先完成处理。"

    def _handle_current_task_status_query(
            self,
            chat_id: str,
            current_task_id: str | None,
    ) -> AgentResult:
        snapshot = self.memory_facade.build_agent_snapshot(chat_id)

        if not current_task_id:
            return AgentResult(
                status="ok",
                message="当前没有绑定任务。",
                task_id=None,
                snapshot=snapshot,
            )

        current_task_summary = snapshot.get("current_task_summary") or {}
        latest_materials_summary = current_task_summary.get("latest_materials_summary") or {}

        display_name = self._get_task_display_name(current_task_id)
        status_text = current_task_summary.get("status") or "未知状态"
        stage_text = current_task_summary.get("stage") or "未知阶段"

        has_blank = latest_materials_summary.get("has_blank_pdf")
        has_solution = latest_materials_summary.get("has_solution_pdf")

        material_desc = []
        if has_blank:
            material_desc.append("已上传试卷 PDF")
        if has_solution:
            material_desc.append("已上传答案解析 PDF")
        if not material_desc:
            material_desc.append("尚未上传任何文件")

        message = (
            f"当前任务是：{display_name}\n"
            f"状态：{status_text}\n"
            f"阶段：{stage_text}\n"
            f"材料情况：{'，'.join(material_desc)}"
        )

        return AgentResult(
            status="ok",
            message=message,
            task_id=current_task_id,
            snapshot=snapshot,
        )

    def _handle_current_task_result_query(
        self,
        chat_id: str,
        current_task_id: str | None,
    ) -> AgentResult:
        snapshot = self.memory_facade.build_agent_snapshot(chat_id)

        if not current_task_id:
            return AgentResult(
                status="ok",
                message="当前没有进行中的任务，因此也没有当前任务的下载链接。",
                task_id=None,
                snapshot=snapshot,
            )

        result = self.delivery_service.get_result_by_task_id(current_task_id)
        if result:
            return AgentResult(
                status="ok",
                message=(
                    "找到了当前任务的处理结果：\n\n"
                    f"📁 交付文件夹：{result['package_name']}\n"
                    f"🔗 下载链接：{result['remote_url']}"
                ),
                task_id=current_task_id,
                snapshot=snapshot,
            )

        return AgentResult(
            status="ok",
            message=self._build_current_task_no_result_message(snapshot),
            task_id=current_task_id,
            snapshot=snapshot,
        )

    def _handle_result_query(
        self,
        chat_id: str,
        current_task_id: str | None,
    ) -> AgentResult:
        if current_task_id:
            result = self.delivery_service.get_result_by_task_id(current_task_id)
            if result:
                return AgentResult(
                    status="ok",
                    message=(
                        "找到了当前任务的处理结果：\n\n"
                        f"📁 交付文件夹：{result['package_name']}\n"
                        f"🔗 下载链接：{result['remote_url']}"
                    ),
                    task_id=current_task_id,
                    snapshot=self.memory_facade.build_agent_snapshot(chat_id),
                )

        result = self.delivery_service.get_latest_result_by_chat_id(chat_id)
        if result:
            return AgentResult(
                status="ok",
                message=(
                    "找到了最近一次处理结果：\n\n"
                    f"📁 交付文件夹：{result['package_name']}\n"
                    f"🔗 下载链接：{result['remote_url']}"
                ),
                task_id=result["task_id"],
                snapshot=self.memory_facade.build_agent_snapshot(chat_id),
            )

        return AgentResult(
            status="ok",
            message="目前还没有可获取的处理结果，请先上传试卷并完成处理。",
            task_id=current_task_id,
            snapshot=self.memory_facade.build_agent_snapshot(chat_id),
        )

    def _handle_current_task_rerun_excel(
            self,
            chat_id: str,
            current_task_id: str | None,
    ) -> AgentResult:
        snapshot = self.memory_facade.build_agent_snapshot(chat_id)

        if not current_task_id:
            record = self.delivery_service.get_latest_completed_delivery_record_by_chat_id(chat_id)
            if not record:
                return AgentResult(
                    status="ok",
                    message="当前没有可用于重跑 Excel 的任务。",
                    task_id=None,
                    snapshot=snapshot,
                )
            current_task_id = record.get("task_id")

            if current_task_id:
                self.chat_session_service.bind_task(
                    chat_id=chat_id,
                    task_id=current_task_id,
                )
                self.chat_session_service.clear_waiting_for(chat_id)
                self.chat_session_service.update_summary_memory(
                    chat_id=chat_id,
                    summary_memory=f"已将当前会话上下文切换到最近一次已完成任务 {current_task_id}，用于执行 Excel 单项重跑",
                )
                snapshot = self.memory_facade.build_agent_snapshot(chat_id)

        paths = self._get_task_artifact_paths(current_task_id)

        err = self._require_path(
            paths["manifest_path"],
            "无法只重跑 Excel，因为当前任务缺少 manifest.json。请先完整重跑上游步骤。",
        )
        if err:
            return AgentResult(
                status="ok",
                message=err,
                task_id=current_task_id,
                snapshot=snapshot,
            )

        self._send_task_text(
            chat_id,
            current_task_id,
            "正在重新生成 Excel，请稍等……",
        )

        tool_call = ToolCall(
            tool_name="write_excel",
            tool_args={
                "task_id": current_task_id,
                "manifest_path": str(paths["manifest_path"]),
                "output_path": str(paths["excel_path"]),
                "school": "",
                "year": "",
                "paper_note": "",
            },
        )

        tool_result = self.tool_executor.execute(tool_call)
        snapshot = self.memory_facade.build_agent_snapshot(chat_id)

        if not tool_result.success:
            return AgentResult(
                status="failed",
                message=f"重跑 Excel 失败：{tool_result.message}",
                task_id=current_task_id,
                snapshot=snapshot,
            )

        self.chat_session_service.set_waiting_for(
            chat_id,
            "rerun_excel_followup",
        )

        return AgentResult(
            status="ok",
            message=self._with_task_prefix(
                current_task_id,
                "已重新生成 Excel。\n"
                "是否继续重新打包并上传最新结果？"
            ),
            task_id=current_task_id,
            snapshot=snapshot,
        )

    def _handle_current_task_rerun_cut(
            self,
            chat_id: str,
            current_task_id: str | None,
    ) -> AgentResult:
        snapshot = self.memory_facade.build_agent_snapshot(chat_id)

        # 如果当前没有任务，则回退到最近一次已完成任务
        if not current_task_id:
            record = self.delivery_service.get_latest_completed_delivery_record_by_chat_id(chat_id)
            if not record:
                return AgentResult(
                    status="ok",
                    message="当前没有可用于重新切题的任务。",
                    task_id=None,
                    snapshot=snapshot,
                )
            current_task_id = record.get("task_id")

            if current_task_id:
                self.chat_session_service.bind_task(
                    chat_id=chat_id,
                    task_id=current_task_id,
                )
                self.chat_session_service.clear_waiting_for(chat_id)
                self.chat_session_service.update_summary_memory(
                    chat_id=chat_id,
                    summary_memory=f"已将当前会话上下文切换到最近一次已完成任务 {current_task_id}，用于重新切题",
                )
                snapshot = self.memory_facade.build_agent_snapshot(chat_id)

        blank_pdf_path, solution_pdf_path = self._get_task_material_paths(current_task_id)

        if not blank_pdf_path or not Path(blank_pdf_path).exists():
            return AgentResult(
                status="ok",
                message="无法重新切题，因为当前任务缺少可用的空白试卷 PDF。",
                task_id=current_task_id,
                snapshot=snapshot,
            )

        if not solution_pdf_path or not Path(solution_pdf_path).exists():
            return AgentResult(
                status="ok",
                message="无法重新切题，因为当前任务缺少可用的答案解析 PDF。",
                task_id=current_task_id,
                snapshot=snapshot,
            )

        work_dir = str(settings.tasks_dir)

        self._send_task_text(
            chat_id,
            current_task_id,
            "正在重新切题并解析试卷结构，请稍等……",
        )

        tool_call = ToolCall(
            tool_name="process_paper",
            tool_args={
                "task_id": current_task_id,
                "work_dir": work_dir,
            },
        )

        tool_result = self.tool_executor.execute(tool_call)
        snapshot = self.memory_facade.build_agent_snapshot(chat_id)

        if not tool_result.success:
            return AgentResult(
                status="failed",
                message=f"重新切题失败：{tool_result.message}",
                task_id=current_task_id,
                snapshot=snapshot,
            )

        self.chat_session_service.set_waiting_for(
            chat_id,
            "rerun_cut_followup",
        )

        return AgentResult(
            status="ok",
            message=self._with_task_prefix(
                current_task_id,
                "已重新切题。\n"
                "如需让最新结果生效，建议继续：\n"
                "1. 重新分析答案和知识点\n"
                "2. 重新生成 Excel\n"
                "3. 重新打包并上传\n\n"
                "是否继续？"
            ),
            task_id=current_task_id,
            snapshot=snapshot,
        )

    def _handle_current_task_rerun_manifest(
            self,
            chat_id: str,
            current_task_id: str | None,
    ) -> AgentResult:
        snapshot = self.memory_facade.build_agent_snapshot(chat_id)

        # 如果当前没有任务，则回退到最近一次已完成任务
        if not current_task_id:
            record = self.delivery_service.get_latest_completed_delivery_record_by_chat_id(chat_id)
            if not record:
                return AgentResult(
                    status="ok",
                    message="当前没有可用于重新生成 manifest 的任务。",
                    task_id=None,
                    snapshot=snapshot,
                )
            current_task_id = record.get("task_id")

            if current_task_id:
                self.chat_session_service.bind_task(
                    chat_id=chat_id,
                    task_id=current_task_id,
                )
                self.chat_session_service.clear_waiting_for(chat_id)
                self.chat_session_service.update_summary_memory(
                    chat_id=chat_id,
                    summary_memory=f"已将当前会话上下文切换到最近一次已完成任务 {current_task_id}，用于重新生成 manifest",
                )
                snapshot = self.memory_facade.build_agent_snapshot(chat_id)

        paths = self._get_task_artifact_paths(current_task_id)
        task_root = paths["task_root"]

        # 这里直接沿用你当前项目的真实目录结构
        question_dir = paths["question_dir"]
        analysis_dir = paths["analysis_dir"]
        cleaned_analysis_dir = paths["cleaned_analysis_dir"]
        manifest_path = paths["manifest_path"]

        # 前置依赖校验：
        # 重新生成 manifest 需要已有切题与解析图片产物
        if not question_dir.exists():
            return AgentResult(
                status="ok",
                message="无法重新生成 manifest，因为当前任务缺少 question_images 目录。请先完成切题。",
                task_id=current_task_id,
                snapshot=snapshot,
            )

        if not analysis_dir.exists():
            return AgentResult(
                status="ok",
                message="无法重新生成 manifest，因为当前任务缺少 analysis_images 目录。请先完成切题。",
                task_id=current_task_id,
                snapshot=snapshot,
            )

        if not cleaned_analysis_dir.exists():
            return AgentResult(
                status="ok",
                message="无法重新生成 manifest，因为当前任务缺少 cleaned_analysis_images 目录。请先完成切题。",
                task_id=current_task_id,
                snapshot=snapshot,
            )

        self._send_task_text(
            chat_id,
            current_task_id,
            "正在重新分析答案和知识点，请稍等……",
        )

        tool_call = ToolCall(
            tool_name="build_manifest",
            tool_args={
                "task_id": current_task_id,
                "question_root_dir": str(question_dir),
                "analysis_root_dir": str(analysis_dir),
                "cleaned_analysis_root_dir": str(cleaned_analysis_dir),
                "output_path": str(manifest_path),
            },
        )

        tool_result = self.tool_executor.execute(tool_call)
        snapshot = self.memory_facade.build_agent_snapshot(chat_id)

        if not tool_result.success:
            return AgentResult(
                status="failed",
                message=f"重新生成 manifest 失败：{tool_result.message}",
                task_id=current_task_id,
                snapshot=snapshot,
            )

        return AgentResult(
            status="ok",
            message=self._with_task_prefix(
                current_task_id,
                "已重新生成 manifest。我已基于当前任务已有的切题结果和解析图片重新构建清单。",
            ),
            task_id=current_task_id,
            snapshot=snapshot,
        )

    def _handle_current_task_rerun_analysis(
            self,
            chat_id: str,
            current_task_id: str | None,
    ) -> AgentResult:
        snapshot = self.memory_facade.build_agent_snapshot(chat_id)

        # 如果当前没有任务，则回退到最近一次已完成任务
        if not current_task_id:
            record = self.delivery_service.get_latest_completed_delivery_record_by_chat_id(chat_id)
            if not record:
                return AgentResult(
                    status="ok",
                    message="当前没有可用于重新分析答案和知识点的任务。",
                    task_id=None,
                    snapshot=snapshot,
                )
            current_task_id = record.get("task_id")

            if current_task_id:
                self.chat_session_service.bind_task(
                    chat_id=chat_id,
                    task_id=current_task_id,
                )
                self.chat_session_service.clear_waiting_for(chat_id)
                self.chat_session_service.update_summary_memory(
                    chat_id=chat_id,
                    summary_memory=f"已将当前会话上下文切换到最近一次已完成任务 {current_task_id}，用于重新分析答案和知识点",
                )
                snapshot = self.memory_facade.build_agent_snapshot(chat_id)

        paths = self._get_task_artifact_paths(current_task_id)

        # 前置依赖：重新分析答案和知识点依赖已有图片目录
        checks = [
            self._require_path(
                paths["question_dir"],
                "无法重新分析答案和知识点，因为当前任务缺少 question_images 目录。请先完成切题。"
            ),
            self._require_path(
                paths["analysis_dir"],
                "无法重新分析答案和知识点，因为当前任务缺少 analysis_images 目录。请先完成切题。"
            ),
            self._require_path(
                paths["cleaned_analysis_dir"],
                "无法重新分析答案和知识点，因为当前任务缺少 cleaned_analysis_images 目录。请先完成切题。"
            ),
        ]

        for err in checks:
            if err:
                return AgentResult(
                    status="ok",
                    message=err,
                    task_id=current_task_id,
                    snapshot=snapshot,
                )

        self._send_task_text(
            chat_id,
            current_task_id,
            "正在重新分析答案和知识点，请稍等……",
        )

        tool_call = ToolCall(
            tool_name="build_manifest",
            tool_args={
                "task_id": current_task_id,
                "question_root_dir": str(paths["question_dir"]),
                "analysis_root_dir": str(paths["analysis_dir"]),
                "cleaned_analysis_root_dir": str(paths["cleaned_analysis_dir"]),
                "output_path": str(paths["manifest_path"]),
            },
        )

        tool_result = self.tool_executor.execute(tool_call)
        snapshot = self.memory_facade.build_agent_snapshot(chat_id)

        if not tool_result.success:
            return AgentResult(
                status="failed",
                message=f"重新分析答案和知识点失败：{tool_result.message}",
                task_id=current_task_id,
                snapshot=snapshot,
            )

        self.chat_session_service.set_waiting_for(
            chat_id,
            "rerun_analysis_followup",
        )

        return AgentResult(
            status="ok",
            message=self._with_task_prefix(
                current_task_id,
                "已重新分析答案和知识点，并更新题目清单。\n"
                "是否继续重新生成 Excel，并打包上传最新结果？"
            ),
            task_id=current_task_id,
            snapshot=snapshot,
        )

    def _handle_current_task_repackage(
            self,
            chat_id: str,
            current_task_id: str | None,
    ) -> AgentResult:
        snapshot = self.memory_facade.build_agent_snapshot(chat_id)

        if not current_task_id:
            record = self.delivery_service.get_latest_completed_delivery_record_by_chat_id(chat_id)
            if not record:
                return AgentResult(
                    status="ok",
                    message="当前没有可用于重新打包的任务。",
                    task_id=None,
                    snapshot=snapshot,
                )
            current_task_id = record.get("task_id")

            if current_task_id:
                self.chat_session_service.bind_task(
                    chat_id=chat_id,
                    task_id=current_task_id,
                )
                self.chat_session_service.clear_waiting_for(chat_id)
                self.chat_session_service.update_summary_memory(
                    chat_id=chat_id,
                    summary_memory=f"已将当前会话上下文切换到最近一次已完成任务 {current_task_id}，用于执行重新打包",
                )
                snapshot = self.memory_facade.build_agent_snapshot(chat_id)

        paths = self._get_task_artifact_paths(current_task_id)

        checks = [
            self._require_path(
                paths["manifest_path"],
                "无法只重新打包，因为当前任务缺少 manifest.json。"
            ),
            self._require_path(
                paths["excel_path"],
                "无法只重新打包，因为当前任务缺少 Excel 文件。请先重跑 Excel 或完整处理。"
            ),
            self._require_path(
                paths["question_dir"],
                "无法只重新打包，因为当前任务缺少 question_images 目录。"
            ),
            self._require_path(
                paths["analysis_dir"],
                "无法只重新打包，因为当前任务缺少 analysis_images 目录。"
            ),
            self._require_path(
                paths["cleaned_analysis_dir"],
                "无法只重新打包，因为当前任务缺少 cleaned_analysis_images 目录。"
            ),
        ]

        for err in checks:
            if err:
                return AgentResult(
                    status="ok",
                    message=err,
                    task_id=current_task_id,
                    snapshot=snapshot,
                )

        blank_pdf_path = (
                             (snapshot.get("current_task_summary") or {})
                             .get("latest_materials_summary", {})
                             .get("blank_pdf_local_path")
                         ) or ""

        self._send_task_text(
            chat_id,
            current_task_id,
            "正在重新打包结果，请稍等……",
        )

        tool_call = ToolCall(
            tool_name="package_results",
            tool_args={
                "task_id": current_task_id,
                "task_root": str(settings.tasks_dir),
                "excel_path": str(paths["excel_path"]),
                "question_dir": str(paths["question_dir"]),
                "analysis_dir": str(paths["analysis_dir"]),
                "cleaned_analysis_dir": str(paths["cleaned_analysis_dir"]),
                "manifest_path": str(paths["manifest_path"]),
                "source_pdf_path": blank_pdf_path,
            },
        )

        tool_result = self.tool_executor.execute(tool_call)
        snapshot = self.memory_facade.build_agent_snapshot(chat_id)

        if not tool_result.success:
            return AgentResult(
                status="failed",
                message=f"重新打包失败：{tool_result.message}",
                task_id=current_task_id,
                snapshot=snapshot,
            )

        self.chat_session_service.set_waiting_for(
            chat_id,
            "rerun_package_followup",
        )

        return AgentResult(
            status="ok",
            message=self._with_task_prefix(
                current_task_id,
                "已重新打包完成。\n"
                "是否现在上传最新结果？"
            ),
            task_id=current_task_id,
            snapshot=snapshot,
        )

    def _handle_current_task_redeliver(
            self,
            chat_id: str,
            current_task_id: str | None,
    ) -> AgentResult:
        snapshot = self.memory_facade.build_agent_snapshot(chat_id)

        if not current_task_id:
            record = self.delivery_service.get_latest_completed_delivery_record_by_chat_id(chat_id)
            if not record:
                return AgentResult(
                    status="ok",
                    message="当前没有可用于重新上传的任务。",
                    task_id=None,
                    snapshot=snapshot,
                )
            current_task_id = record.get("task_id")

            if current_task_id:
                self.chat_session_service.bind_task(
                    chat_id=chat_id,
                    task_id=current_task_id,
                )
                self.chat_session_service.clear_waiting_for(chat_id)
                self.chat_session_service.update_summary_memory(
                    chat_id=chat_id,
                    summary_memory=f"已将当前会话上下文切换到最近一次已完成任务 {current_task_id}，用于执行重新上传结果",
                )
                snapshot = self.memory_facade.build_agent_snapshot(chat_id)

        record = self.delivery_service.get_latest_delivery_record_by_task_id(current_task_id)
        if not record:
            return AgentResult(
                status="ok",
                message="当前任务还没有可复用的打包结果，无法只重新上传。请先完成打包或完整处理。",
                task_id=current_task_id,
                snapshot=snapshot,
            )

        local_package_path = record.get("local_package_path")
        if not local_package_path or not Path(local_package_path).exists():
            return AgentResult(
                status="ok",
                message="当前任务缺少可用的本地打包目录，无法只重新上传结果。",
                task_id=current_task_id,
                snapshot=snapshot,
            )

        self._send_task_text(
            chat_id,
            current_task_id,
            "正在重新上传最新结果，请稍等……",
        )

        tool_call = ToolCall(
            tool_name="deliver_results",
            tool_args={
                "task_id": current_task_id,
                "local_package_path": local_package_path,
            },
        )

        tool_result = self.tool_executor.execute(tool_call)
        snapshot = self.memory_facade.build_agent_snapshot(chat_id)

        if not tool_result.success:
            return AgentResult(
                status="failed",
                message=f"重新上传失败：{tool_result.message}",
                task_id=current_task_id,
                snapshot=snapshot,
            )

        remote_url = (
                (tool_result.data.get("record", {}) or {}).get("remote_url")
                or (tool_result.data.get("upload_result", {}) or {}).get("root_folder_url", "")
        )

        self.chat_session_service.clear_waiting_for(chat_id)

        message = self._with_task_prefix(
            current_task_id,
            "已完成重新上传。",
        )
        if remote_url:
            message += f"\n访问链接：{remote_url}"

        return AgentResult(
            status="ok",
            message=message,
            task_id=current_task_id,
            snapshot=snapshot,
        )

    def _handle_rerun_analysis_followup(
            self,
            event: AgentEvent,
            current_task_id: str | None,
    ) -> AgentResult:
        snapshot = self.memory_facade.build_agent_snapshot(event.chat_id)

        if self.confirmation_policy.is_confirm_message(event.user_message):
            self.chat_session_service.clear_waiting_for(event.chat_id)

            excel_result = self._handle_current_task_rerun_excel(
                chat_id=event.chat_id,
                current_task_id=current_task_id,
            )
            if excel_result.status != "ok":
                return excel_result

            # Excel 成功后会设置 rerun_excel_followup，这里要直接继续，所以清掉
            self.chat_session_service.clear_waiting_for(event.chat_id)

            repackage_result = self._handle_current_task_repackage(
                chat_id=event.chat_id,
                current_task_id=excel_result.task_id or current_task_id,
            )
            if repackage_result.status != "ok":
                return repackage_result

            # 打包成功后会设置 rerun_package_followup，这里要直接继续，所以清掉
            self.chat_session_service.clear_waiting_for(event.chat_id)

            return self._handle_current_task_redeliver(
                chat_id=event.chat_id,
                current_task_id=repackage_result.task_id or current_task_id,
            )

        if self.confirmation_policy.is_reject_message(event.user_message):
            self.chat_session_service.clear_waiting_for(event.chat_id)
            return AgentResult(
                status="ok",
                message="好的，当前已停留在重新分析答案和知识点的结果。",
                task_id=current_task_id,
                snapshot=snapshot,
            )

        return AgentResult(
            status="ok",
            message="如果你希望我继续处理下游步骤，请回复“继续”；如果暂时不用，请回复“不用了”。",
            task_id=current_task_id,
            snapshot=snapshot,
        )

    def _handle_rerun_cut_followup(
            self,
            event: AgentEvent,
            current_task_id: str | None,
    ) -> AgentResult:
        snapshot = self.memory_facade.build_agent_snapshot(event.chat_id)

        if self.confirmation_policy.is_confirm_message(event.user_message):
            self.chat_session_service.clear_waiting_for(event.chat_id)

            analysis_result = self._handle_current_task_rerun_analysis(
                chat_id=event.chat_id,
                current_task_id=current_task_id,
            )
            if analysis_result.status != "ok":
                return analysis_result

            # analysis 成功后会设置 rerun_analysis_followup，这里要直接继续，所以清掉
            self.chat_session_service.clear_waiting_for(event.chat_id)

            excel_result = self._handle_current_task_rerun_excel(
                chat_id=event.chat_id,
                current_task_id=analysis_result.task_id or current_task_id,
            )
            if excel_result.status != "ok":
                return excel_result

            self.chat_session_service.clear_waiting_for(event.chat_id)

            repackage_result = self._handle_current_task_repackage(
                chat_id=event.chat_id,
                current_task_id=excel_result.task_id or current_task_id,
            )
            if repackage_result.status != "ok":
                return repackage_result

            self.chat_session_service.clear_waiting_for(event.chat_id)

            return self._handle_current_task_redeliver(
                chat_id=event.chat_id,
                current_task_id=repackage_result.task_id or current_task_id,
            )

        if self.confirmation_policy.is_reject_message(event.user_message):
            self.chat_session_service.clear_waiting_for(event.chat_id)
            return AgentResult(
                status="ok",
                message="好的，当前已停留在重新切题的结果。",
                task_id=current_task_id,
                snapshot=snapshot,
            )

        return AgentResult(
            status="ok",
            message="如果你希望我继续处理下游步骤，请回复“继续”；如果暂时不用，请回复“不用了”。",
            task_id=current_task_id,
            snapshot=snapshot,
        )

    def _handle_rerun_excel_followup(
            self,
            event: AgentEvent,
            current_task_id: str | None,
    ) -> AgentResult:
        snapshot = self.memory_facade.build_agent_snapshot(event.chat_id)

        if self.confirmation_policy.is_confirm_message(event.user_message):
            self.chat_session_service.clear_waiting_for(event.chat_id)

            repackage_result = self._handle_current_task_repackage(
                chat_id=event.chat_id,
                current_task_id=current_task_id,
            )
            if repackage_result.status != "ok":
                return repackage_result

            # 重新打包成功后会设置 rerun_package_followup，
            # 这里我们要直接继续上传，所以先清掉
            self.chat_session_service.clear_waiting_for(event.chat_id)

            return self._handle_current_task_redeliver(
                chat_id=event.chat_id,
                current_task_id=repackage_result.task_id or current_task_id,
            )

        if self.confirmation_policy.is_reject_message(event.user_message):
            self.chat_session_service.clear_waiting_for(event.chat_id)
            return AgentResult(
                status="ok",
                message="好的，当前已停留在重新生成 Excel 的结果。",
                task_id=current_task_id,
                snapshot=snapshot,
            )

        return AgentResult(
            status="ok",
            message="如果你希望我继续处理下游步骤，请回复“继续”；如果暂时不用，请回复“不用了”。",
            task_id=current_task_id,
            snapshot=snapshot,
        )

    def _handle_rerun_package_followup(
            self,
            event: AgentEvent,
            current_task_id: str | None,
    ) -> AgentResult:
        snapshot = self.memory_facade.build_agent_snapshot(event.chat_id)

        if self.confirmation_policy.is_confirm_message(event.user_message):
            self.chat_session_service.clear_waiting_for(event.chat_id)

            return self._handle_current_task_redeliver(
                chat_id=event.chat_id,
                current_task_id=current_task_id,
            )

        if self.confirmation_policy.is_reject_message(event.user_message):
            self.chat_session_service.clear_waiting_for(event.chat_id)
            return AgentResult(
                status="ok",
                message="好的，当前已停留在重新打包的结果。",
                task_id=current_task_id,
                snapshot=snapshot,
            )

        return AgentResult(
            status="ok",
            message="如果你希望我继续上传最新结果，请回复“继续”；如果暂时不用，请回复“不用了”。",
            task_id=current_task_id,
            snapshot=snapshot,
        )


    def _handle_latest_completed_task_redeliver(
            self,
            chat_id: str,
            current_task_id: str | None,
    ) -> AgentResult:
        snapshot = self.memory_facade.build_agent_snapshot(chat_id)

        record = self.delivery_service.get_latest_completed_delivery_record_by_chat_id(chat_id)
        if not record:
            return AgentResult(
                status="ok",
                message="当前没有可用于重新上传的已完成任务记录。",
                task_id=current_task_id,
                snapshot=snapshot,
            )

        target_task_id = record.get("task_id")
        local_package_path = record.get("local_package_path")

        if not target_task_id or not local_package_path or not Path(local_package_path).exists():
            return AgentResult(
                status="ok",
                message="最近一次已完成任务缺少可用的本地打包目录，无法重新上传。",
                task_id=current_task_id,
                snapshot=snapshot,
            )

        self._send_task_text(
            chat_id,
            target_task_id,
            "正在重新上传最近一次已完成任务的结果，请稍等……",
        )

        tool_call = ToolCall(
            tool_name="deliver_results",
            tool_args={
                "task_id": target_task_id,
                "local_package_path": local_package_path,
            },
        )

        tool_result = self.tool_executor.execute(tool_call)
        snapshot = self.memory_facade.build_agent_snapshot(chat_id)

        if not tool_result.success:
            return AgentResult(
                status="failed",
                message=f"最近一次已完成任务重新上传失败：{tool_result.message}",
                task_id=target_task_id,
                snapshot=snapshot,
            )

        remote_url = (
                (tool_result.data.get("record", {}) or {}).get("remote_url")
                or (tool_result.data.get("upload_result", {}) or {}).get("root_folder_url", "")
        )

        self.chat_session_service.clear_waiting_for(chat_id)

        message = self._with_task_prefix(
            target_task_id,
            "已完成重新上传。我已基于最近一次已完成任务的现有打包目录重新上传结果。",
        )
        if remote_url:
            message += f"\n访问链接：{remote_url}"

        return AgentResult(
            status="ok",
            message=message,
            task_id=target_task_id,
            snapshot=snapshot,
        )

    def _handle_completed_task_link_query(
            self,
            chat_id: str,
            current_task_id: str | None,
    ) -> AgentResult:
        snapshot = self.memory_facade.build_agent_snapshot(chat_id)
        completed_results = self.delivery_service.get_completed_task_results_by_chat_id(chat_id)

        if not completed_results:
            return AgentResult(
                status="ok",
                message="我找到了已完成任务范围，但暂时没有查到对应的交付链接记录。",
                task_id=current_task_id,
                snapshot=snapshot,
            )

        if len(completed_results) == 1:
            item = completed_results[0]
            return AgentResult(
                status="ok",
                message=(
                    "我找到了 1 个已完成任务的访问链接：\n\n"
                    f"📁 交付文件夹：{item['package_name']}\n"
                    f"🔗 访问链接：{item['remote_url']}"
                ),
                task_id=item["task_id"],
                snapshot=snapshot,
            )

        lines = [f"我找到了 {len(completed_results)} 个已完成任务的访问链接：", ""]
        for idx, item in enumerate(completed_results, start=1):
            lines.extend(
                [
                    f"{idx}. {item['package_name']}",
                    f"   访问链接：{item['remote_url']}",
                    "",
                ]
            )

        return AgentResult(
            status="ok",
            message="\n".join(lines).strip(),
            task_id=current_task_id,
            snapshot=snapshot,
        )


    def _handle_missing_materials_query(
        self,
        chat_id: str,
        current_task_id: str | None,
    ) -> AgentResult:
        missing_tasks = self.memory_facade.list_missing_material_tasks(chat_id)
        snapshot = self.memory_facade.build_agent_snapshot(chat_id)

        if not missing_tasks:
            return AgentResult(
                status="ok",
                message="当前没有仍然缺材料的任务。",
                task_id=current_task_id,
                snapshot=snapshot,
            )

        lines = [f"当前共有 {len(missing_tasks)} 个任务还缺材料：", ""]
        for idx, item in enumerate(missing_tasks, start=1):
            uploaded_text = "、".join(item["uploaded_parts"]) if item["uploaded_parts"] else "暂无"
            missing_text = "、".join(item["missing_parts"]) if item["missing_parts"] else "无"

            lines.extend(
                [
                    f"{idx}️⃣ {item['display_name']}",
                    f"   - 已上传：{uploaded_text}",
                    f"   - 缺少：{missing_text}",
                    "",
                ]
            )

        lines.append("请上传对应缺失材料后，我即可继续处理。")

        return AgentResult(
            status="ok",
            message="\n".join(lines),
            task_id=current_task_id,
            snapshot=snapshot,
        )

    def _handle_restart_current_task(
        self,
        chat_id: str,
        current_task_id: str | None,
    ) -> AgentResult:
        if current_task_id:
            self.task_service.mark_cancelled(current_task_id)

        self.chat_session_service.unbind_task(chat_id)
        self.chat_session_service.clear_waiting_for(chat_id)

        new_task = self.task_service.create_task(
            chat_id=chat_id,
            created_by="agent",
        )
        new_task_id = new_task["task_id"]

        self.chat_session_service.bind_task(
            chat_id=chat_id,
            task_id=new_task_id,
        )
        self.chat_session_service.set_waiting_for(
            chat_id,
            "materials_upload",
        )
        self.chat_session_service.update_summary_memory(
            chat_id=chat_id,
            summary_memory=f"已重新开始并创建新任务 {new_task_id}，等待上传材料",
        )

        created_task = self.task_service.get_task(new_task_id)
        latest_session = self.chat_session_service.get_session(chat_id)
        snapshot = self.memory_facade.build_agent_snapshot(chat_id)

        if not created_task:
            return AgentResult(
                status="failed",
                message="重新开始失败：新任务创建后未能查询到任务记录，请检查数据库写入情况。",
                task_id=None,
                snapshot=snapshot,
            )

        if not latest_session:
            return AgentResult(
                status="failed",
                message="重新开始失败：新任务已创建，但未能读取当前会话信息。",
                task_id=new_task_id,
                snapshot=snapshot,
            )

        if latest_session.get("current_task_id") != new_task_id:
            return AgentResult(
                status="failed",
                message=(
                    "重新开始失败：新任务已创建，但当前会话未正确绑定到新任务。"
                    f"新任务ID：{new_task_id}"
                ),
                task_id=new_task_id,
                snapshot=snapshot,
            )

        if latest_session.get("waiting_for") != "materials_upload":
            return AgentResult(
                status="failed",
                message=(
                    "重新开始失败：新任务已创建，但当前会话未进入材料上传等待状态。"
                    f"新任务ID：{new_task_id}"
                ),
                task_id=new_task_id,
                snapshot=snapshot,
            )

        return AgentResult(
            status="ok",
            message=(
                "好的，已经从头重新开始。\n\n"
                "我已为你创建一个新的空任务，请重新上传以下材料：\n"
                "- 空白试卷 PDF\n"
                "- 答案解析 PDF\n\n"
                "你可以一次上传一个，也可以两个一起上传。"
            ),
            task_id=new_task_id,
            snapshot=snapshot,
        )

    def _resolve_task_for_file_upload(
        self,
        chat_id: str,
        current_task_id: str | None,
        bound_task: dict | None,
        latest_uploaded_file_name: str | None,
    ) -> tuple[str, str | None]:
        if not current_task_id or not bound_task:
            new_task = self.task_service.create_task(
                chat_id=chat_id,
                created_by="agent",
            )
            new_task_id = new_task["task_id"]

            self.chat_session_service.bind_task(
                chat_id=chat_id,
                task_id=new_task_id,
            )
            self.chat_session_service.set_waiting_for(
                chat_id,
                "materials_upload",
            )
            self.chat_session_service.update_summary_memory(
                chat_id=chat_id,
                summary_memory=f"已自动创建任务 {new_task_id} 并接收新上传材料",
            )

            return new_task_id, None

        current_stage = bound_task.get("current_stage")
        current_status = bound_task.get("status")

        if current_stage in self.MATERIAL_EDITABLE_STAGES:
            return current_task_id, None

        if current_stage in self.NEW_TASK_ON_UPLOAD_STAGES or current_status in self.TERMINAL_STATUSES:
            new_task = self.task_service.create_task(
                chat_id=chat_id,
                created_by="agent",
            )
            new_task_id = new_task["task_id"]

            self.chat_session_service.bind_task(
                chat_id=chat_id,
                task_id=new_task_id,
            )
            self.chat_session_service.set_waiting_for(
                chat_id,
                "materials_upload",
            )

            reason_text = "当前任务状态不适合继续补充材料"
            if current_stage == TaskState.PROCESSING.value:
                reason_text = "检测到当前任务正在处理中"
            elif current_stage == TaskState.DELIVERING.value:
                reason_text = "检测到当前任务正在上传交付结果"
            elif current_stage == TaskState.COMPLETED.value or current_status == TaskState.COMPLETED.value:
                reason_text = "检测到当前任务已经完成"
            elif current_stage == TaskState.FAILED.value or current_status == TaskState.FAILED.value:
                reason_text = "检测到当前任务已经失败"
            elif current_stage == TaskState.CANCELLED.value or current_status == TaskState.CANCELLED.value:
                reason_text = "检测到当前任务已经取消"

            self.chat_session_service.update_summary_memory(
                chat_id=chat_id,
                summary_memory=f"{reason_text}，已自动创建新任务 {new_task_id} 来接收本次上传材料",
            )

            switched_name = latest_uploaded_file_name or self._get_task_display_name(new_task_id)
            handoff_message = (
                f"ℹ️ {reason_text}，我会把这次新上传的文件作为一个新任务来处理。\n"
                f"👉 当前任务已切换为：{switched_name}"
            )

            return new_task_id, handoff_message

        new_task = self.task_service.create_task(
            chat_id=chat_id,
            created_by="agent",
        )
        new_task_id = new_task["task_id"]

        self.chat_session_service.bind_task(
            chat_id=chat_id,
            task_id=new_task_id,
        )
        self.chat_session_service.set_waiting_for(
            chat_id,
            "materials_upload",
        )
        self.chat_session_service.update_summary_memory(
            chat_id=chat_id,
            summary_memory=f"检测到未知任务阶段，已自动创建新任务 {new_task_id} 来接收本次上传材料",
        )

        switched_name = latest_uploaded_file_name or self._get_task_display_name(new_task_id)
        return new_task_id, f"ℹ️ 检测到当前任务状态异常，我会把这次新上传的文件作为一个新任务来处理。\n👉 当前任务已切换为：{switched_name}"

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
        bound_task = self.task_service.get_task(current_task_id) if current_task_id else None

        # 重要：
        # 不再因为普通文本消息就自动解绑 completed / failed / cancelled 任务。
        # 这样当用户刚刚通过“单项重跑”把上下文切到最近一次已完成任务后，
        # 后续继续问“当前任务是哪个 / 当前任务只重新上传结果 / 当前任务只重新打包”
        # 都还能沿用同一个 task 上下文。
        #
        # 是否切换到新任务，只在文件上传时由 _resolve_task_for_file_upload() 决定。

        waiting_for = session.get("waiting_for")

        if event.event_type == "text":
            # follow-up 模式下：
            # 只有“确认 / 拒绝”继续留在 follow-up 分流里；
            # 其他任何文本，一律视为新的业务命令，先清掉 waiting_for，再按正常逻辑处理。
            if waiting_for:
                if self.confirmation_policy.is_confirm_message(event.user_message):
                    if waiting_for == "rerun_cut_followup":
                        return self._handle_rerun_cut_followup(
                            event=event,
                            current_task_id=current_task_id,
                        )

                    if waiting_for == "rerun_analysis_followup":
                        return self._handle_rerun_analysis_followup(
                            event=event,
                            current_task_id=current_task_id,
                        )

                    if waiting_for == "rerun_excel_followup":
                        return self._handle_rerun_excel_followup(
                            event=event,
                            current_task_id=current_task_id,
                        )

                    if waiting_for == "rerun_package_followup":
                        return self._handle_rerun_package_followup(
                            event=event,
                            current_task_id=current_task_id,
                        )

                if self.confirmation_policy.is_reject_message(event.user_message):
                    if waiting_for == "rerun_cut_followup":
                        return self._handle_rerun_cut_followup(
                            event=event,
                            current_task_id=current_task_id,
                        )

                    if waiting_for == "rerun_analysis_followup":
                        return self._handle_rerun_analysis_followup(
                            event=event,
                            current_task_id=current_task_id,
                        )

                    if waiting_for == "rerun_excel_followup":
                        return self._handle_rerun_excel_followup(
                            event=event,
                            current_task_id=current_task_id,
                        )

                    if waiting_for == "rerun_package_followup":
                        return self._handle_rerun_package_followup(
                            event=event,
                            current_task_id=current_task_id,
                        )

                # 不是确认 / 拒绝，就默认视为新命令
                self.chat_session_service.clear_waiting_for(event.chat_id)
                waiting_for = None

            if self._is_cancel_empty_tasks_message(event.user_message):
                return self._handle_cancel_empty_tasks(
                    chat_id=event.chat_id,
                    current_task_id=current_task_id,
                )

            if self._is_cancel_missing_tasks_message(event.user_message):
                return self._handle_cancel_missing_tasks(
                    chat_id=event.chat_id,
                    current_task_id=current_task_id,
                )

            if self._is_cancel_message(event.user_message):
                return self._handle_cancel_current_task(
                    chat_id=event.chat_id,
                    task_id=current_task_id,
                )

            if self._is_restart_message(event.user_message):
                return self._handle_restart_current_task(
                    chat_id=event.chat_id,
                    current_task_id=current_task_id,
                )

            if self._is_current_task_rerun_cut_query(event.user_message):
                return self._handle_current_task_rerun_cut(
                    chat_id=event.chat_id,
                    current_task_id=current_task_id,
                )

            if self._is_current_task_rerun_analysis_query(event.user_message):
                return self._handle_current_task_rerun_analysis(
                    chat_id=event.chat_id,
                    current_task_id=current_task_id,
                )

            if self._is_current_task_rerun_excel_query(event.user_message):
                return self._handle_current_task_rerun_excel(
                    chat_id=event.chat_id,
                    current_task_id=current_task_id,
                )

            if self._is_current_task_repackage_query(event.user_message):
                return self._handle_current_task_repackage(
                    chat_id=event.chat_id,
                    current_task_id=current_task_id,
                )

            if self._is_current_task_rerun_manifest_query(event.user_message):
                return self._handle_current_task_rerun_manifest(
                    chat_id=event.chat_id,
                    current_task_id=current_task_id,
                )

            if self._is_current_task_redeliver_query(event.user_message):
                return self._handle_current_task_redeliver(
                    chat_id=event.chat_id,
                    current_task_id=current_task_id,
                )

            if self._is_latest_completed_redeliver_query(event.user_message):
                return self._handle_latest_completed_task_redeliver(
                    chat_id=event.chat_id,
                    current_task_id=current_task_id,
                )

            if self._is_current_task_result_query(event.user_message):
                return self._handle_current_task_result_query(
                    chat_id=event.chat_id,
                    current_task_id=current_task_id,
                )

            if self._is_missing_materials_query(event.user_message):
                return self._handle_missing_materials_query(
                    chat_id=event.chat_id,
                    current_task_id=current_task_id,
                )

            if self._is_result_query(event.user_message):
                return self._handle_result_query(
                    chat_id=event.chat_id,
                    current_task_id=current_task_id,
                )

            if self._is_current_task_status_query(event.user_message):
                return self._handle_current_task_status_query(
                    chat_id=event.chat_id,
                    current_task_id=current_task_id,
                )

        if event.event_type == "file_upload" and event.files:
            target_task_id, handoff_message = self._resolve_task_for_file_upload(
                chat_id=event.chat_id,
                current_task_id=current_task_id,
                bound_task=bound_task,
                latest_uploaded_file_name=event.files[-1].file_name if event.files else None,
            )

            if handoff_message:
                self.feishu_message_sender.send_text(
                    event.chat_id,
                    handoff_message,
                )

            tool_call = ToolCall(
                tool_name="ingest_materials",
                tool_args={
                    "task_id": target_task_id,
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
                task_id=target_task_id,
                snapshot=snapshot,
            )

        if not current_task_id and event.event_type == "file_upload":
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

        if (
            current_stage == TaskState.WAITING_CONFIRMATION.value
            and event.event_type == "text"
        ):
            if self.confirmation_policy.is_confirm_message(event.user_message):
                self.feishu_message_sender.send_text(
                    event.chat_id,
                    self._with_task_prefix(
                        current_task_id,
                        "✅ 已确认材料，开始处理试卷。\n\n"
                        "我会依次完成：\n"
                        "- 试卷结构解析与切题\n"
                        "- 答案与知识点提取\n"
                        "- 结果整理并上传\n\n"
                        "请稍候，处理中..."
                    ),
                )

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

                self._send_task_text(
                    event.chat_id,
                    current_task_id,
                    "🔄 当前正在解析试卷结构并切题......",
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

                self._send_task_text(
                    event.chat_id,
                    current_task_id,
                    "🔄 试卷结构解析已完成！当前正在提取答案与知识点，用于填写 Excel 表格 (耗时1-2分钟，请耐心等待) ......",
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

                self._send_task_text(
                    event.chat_id,
                    current_task_id,
                    "🔄 答案与知识点解析已完成！当前正在填写 Excel 表格 (tags.xlsx)......",
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

                self._send_task_text(
                    event.chat_id,
                    current_task_id,
                    "🔄 Excel 表格已填写完成！当前正在打包所有资料......",
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
                package_name = package_result.data.get("package_name") or ""
                package_contents = package_result.data.get("package_contents") or []
                if not local_package_path:
                    snapshot = self.memory_facade.build_agent_snapshot(event.chat_id)
                    return AgentResult(
                        status="failed",
                        message="package_results 成功但没有返回 local_package_path",
                        task_id=current_task_id,
                        snapshot=snapshot,
                    )

                self._send_task_text(
                    event.chat_id,
                    current_task_id,
                    "🔄 所有材料均已打包完成！当前正在上传到飞书云盘文件夹......",
                )

                deliver_tool_call = ToolCall(
                    tool_name="deliver_results",
                    tool_args={
                        "task_id": current_task_id,
                        "local_package_path": local_package_path,
                    },
                )

                deliver_result = self.tool_executor.execute(deliver_tool_call)
                print("DELIVER_RESULT_DATA =", deliver_result.data)
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

                finish_text_parts = [
                    self._with_task_prefix(current_task_id, "🎉 处理完成！"),
                    "",
                ]

                if package_name:
                    finish_text_parts.extend([
                        "📁 交付文件夹：",
                        package_name,
                        "",
                    ])

                if package_contents:
                    finish_text_parts.extend([
                        "📦 包含内容：",
                        *[f"- {item}" for item in package_contents],
                        "",
                    ])

                if remote_url:
                    finish_text_parts.extend([
                        "🔗 查看结果：",
                        remote_url,
                        "",
                    ])
                else:
                    finish_text_parts.extend([
                        "结果已上传到飞书云盘。若你这边暂时没看到链接，我可以继续帮你检查上传返回信息。",
                        "",
                    ])

                finish_text_parts.append("如需重新处理、修改或补充材料，可以直接告诉我。")

                self.feishu_message_sender.send_text(
                    event.chat_id,
                    "\n".join(finish_text_parts),
                )

                result_message = self._with_task_prefix(current_task_id, "处理完成，结果已上传。")

                if package_name:
                    result_message += f"\n交付文件夹：{package_name}"

                if remote_url:
                    result_message += f"\n查看链接：{remote_url}"

                return AgentResult(
                    status="ok",
                    message=result_message,
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
                    message="好的，请重新上传或补充正确的 空白试卷文件 / 解析试卷文件。",
                    task_id=current_task_id,
                    snapshot=snapshot,
                )

            snapshot = self.memory_facade.build_agent_snapshot(event.chat_id)
            return self._run_planner_flow(
                event=event,
                snapshot=snapshot,
                task_id=current_task_id,
            )

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
                message="请上传空白试卷 PDF 和答案解析 PDF，我会继续处理。支持一次上传一个，也支持一次上传多个文件。",
                task_id=current_task_id,
                snapshot=snapshot,
            )

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

            status_text = self._with_task_prefix(current_task_id, processing_summary)
            if next_action_hint:
                status_text += f"\n下一步：{next_action_hint}"

            return AgentResult(
                status="ok",
                message=status_text,
                task_id=current_task_id,
                snapshot=snapshot,
            )

        snapshot = self.memory_facade.build_agent_snapshot(event.chat_id)
        return self._run_planner_flow(
            event=event,
            snapshot=snapshot,
            task_id=current_task_id,
        )