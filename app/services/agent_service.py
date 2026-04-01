import json
import uuid
from datetime import datetime
from typing import Any

from app.services.agent_run_service import agent_run_service
from app.services.artifact_service import artifact_service
from app.services.chat_session_service import chat_session_service
from app.services.llm_service import llm_service
from app.services.task_memory_service import task_memory_service
from app.services.chat_task_binding_service import chat_task_binding_service

from app.utils.logger import setup_logger
from app.config import settings

from app.agent.tools.tool_executor import tool_executor
from app.agent.tools.register_tools import tool_registry

logger = setup_logger(settings.log_level, settings.logs_dir)


class AgentService:
    def handle_event(
        self,
        chat_id: str,
        event_type: str,
        user_message: str | None = None,
        task_id: str | None = None,
        file_name: str | None = None,
        file_key: str | None = None,
    ) -> dict[str, Any]:
        run_id = f"run_{uuid.uuid4().hex[:12]}"
        started_at = datetime.now()

        logger.info(
            "Agent handle_event start. run_id=%s, chat_id=%s, event_type=%s",
            run_id,
            chat_id,
            event_type,
        )

        input_snapshot = {
            "chat_id": chat_id,
            "event_type": event_type,
            "user_message": user_message,
            "task_id": task_id,
            "file_name": file_name,
            "file_key": file_key,
        }

        # 1. 创建 agent run
        agent_run_service.create_run(
            run_id=run_id,
            chat_id=chat_id,
            task_id=task_id,
            event_type=event_type,
            input_snapshot=json.dumps(input_snapshot, ensure_ascii=False),
            status="running",
            model_name=llm_service.model_name,
        )

        # 2. 更新 chat session
        chat_session_service.upsert_session(
            chat_id=chat_id,
            current_task_id=task_id,
            last_user_message=user_message,
            last_message_type=event_type,
            last_uploaded_file_name=file_name,
            last_uploaded_file_key=file_key,
            current_mode="agent_running",
        )

        # 3. 拉取上下文
        session = chat_session_service.get_by_chat_id(chat_id)
        task_memory = task_memory_service.get_by_task_id(task_id) if task_id else None
        artifacts = artifact_service.list_by_task_id(task_id) if task_id else []

        # 3.1 如果当前处于“材料确认阶段”，且用户已经明确确认，则直接进入渲染
        if (
            event_type == "text"
            and session
            and session.get("waiting_for") == "materials_confirmation"
            and self._is_confirmation_message(user_message)
        ):
            confirmed_task_id = session.get("current_task_id")
            if not confirmed_task_id:
                raise ValueError("材料确认阶段缺少 current_task_id")

            # 清除等待状态，避免重复确认
            chat_session_service.update_waiting_for(chat_id, None)

            tool_call = {
                "tool": "render_pdf_pages_from_task",
                "args": {
                    "task_id": confirmed_task_id,
                    "dpi": 150,
                },
            }

            tool_result = tool_executor.execute_tool_call(tool_call)

            final_reply = "已收到您的确认，正在开始渲染 PDF 页面。"
            final_status = "success"

            if tool_result.get("status") != "success":
                final_status = "partial_success"
                final_reply = "已收到您的确认，但渲染 PDF 页面时出现了一点问题，请稍后重试。"

            latency_ms = int((datetime.now() - started_at).total_seconds() * 1000)

            agent_run_service.update_tool_calls(
                run_id=run_id,
                tool_calls_json=json.dumps([tool_call], ensure_ascii=False),
            )
            agent_run_service.update_tool_results(
                run_id=run_id,
                tool_results_json=json.dumps([tool_result], ensure_ascii=False),
            )
            agent_run_service.finish_run(
                run_id=run_id,
                status=final_status,
                latency_ms=latency_ms,
                final_reply=final_reply,
            )

            chat_session_service.update_mode(chat_id, "idle")
            chat_session_service.update_summary_memory(
                chat_id=chat_id,
                summary_memory=f"用户已确认材料，系统已进入 PDF 渲染阶段，run_id={run_id}",
            )

            return {
                "run_id": run_id,
                "status": final_status,
                "reply": final_reply,
                "planner_output": None,
                "tool_results": [tool_result],
                "final_output": {
                    "final_status": final_status,
                    "reason": "用户已确认材料，系统直接进入渲染阶段。",
                    "next_action": "render_pdf_pages_from_task",
                    "reply": final_reply,
                },
                "llm_result": None,
                "final_llm_result": None,
            }

        # 3.5 自动补挂最近上传文件到当前 task
        auto_attach_result = self._maybe_attach_last_uploaded_file(
            chat_id=chat_id,
            task_id=task_id,
            session=session,
            artifacts=artifacts,
        )

        if auto_attach_result and auto_attach_result.get("status") in ("success", "already_attached", "attached"):
            artifacts = artifact_service.list_by_task_id(task_id) if task_id else []

        retrieved_context = {
            "session": session,
            "task_memory": task_memory,
            "artifacts": artifacts,
        }

        agent_run_service.update_retrieved_context(
            run_id=run_id,
            retrieved_context=json.dumps(retrieved_context, ensure_ascii=False),
        )

        # 4. 构造 prompt
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(
            chat_id=chat_id,
            event_type=event_type,
            user_message=user_message,
            task_id=task_id,
            file_name=file_name,
            retrieved_context=retrieved_context,
        )

        agent_run_service.update_planner_prompt(
            run_id=run_id,
            planner_prompt=system_prompt + "\n\n" + user_prompt,
        )

        # 5. 调 LLM 做结构化决策
        llm_result = llm_service.structured_chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

        planner_output_json = llm_result["parsed_json"]

        agent_run_service.update_planner_output(
            run_id=run_id,
            planner_output_json=json.dumps(planner_output_json, ensure_ascii=False),
        )

        # 6. 记录 tool_calls
        tool_calls = planner_output_json.get("tool_calls", [])
        agent_run_service.update_tool_calls(
            run_id=run_id,
            tool_calls_json=json.dumps(tool_calls, ensure_ascii=False),
        )

        # 7. 真正执行 tool_calls
        tool_results = tool_executor.execute_tool_calls(tool_calls)

        agent_run_service.update_tool_results(
            run_id=run_id,
            tool_results_json=json.dumps(tool_results, ensure_ascii=False),
        )

        # 7.5 如果本轮创建了新任务，立刻把 task_id 写回 session / binding
        sync_result = self._sync_task_to_session(
            chat_id=chat_id,
            tool_results=tool_results,
        )

        if sync_result and sync_result.get("should_continue"):
            task_id = sync_result["task_id"]

            logger.info(
                "New task created, re-running planner with fresh context. chat_id=%s, task_id=%s",
                chat_id,
                task_id,
            )

            # 重新拉上下文
            session = chat_session_service.get_by_chat_id(chat_id)
            task_memory = task_memory_service.get_by_task_id(task_id)
            artifacts = artifact_service.list_by_task_id(task_id)

            retrieved_context = {
                "session": session,
                "task_memory": task_memory,
                "artifacts": artifacts,
            }

            agent_run_service.update_retrieved_context(
                run_id=run_id,
                retrieved_context=json.dumps(retrieved_context, ensure_ascii=False),
            )

            # 重新构造 prompt
            system_prompt = self._build_system_prompt()
            user_prompt = self._build_user_prompt(
                chat_id=chat_id,
                event_type=event_type,
                user_message=user_message,
                task_id=task_id,
                file_name=file_name,
                retrieved_context=retrieved_context,
            )

            agent_run_service.update_planner_prompt(
                run_id=run_id,
                planner_prompt=system_prompt + "\n\n" + user_prompt,
            )

            # 再跑一轮 planner
            llm_result = llm_service.structured_chat(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
            planner_output_json = llm_result["parsed_json"]

            agent_run_service.update_planner_output(
                run_id=run_id,
                planner_output_json=json.dumps(planner_output_json, ensure_ascii=False),
            )

            # 再执行新一轮工具
            tool_calls = planner_output_json.get("tool_calls", [])
            agent_run_service.update_tool_calls(
                run_id=run_id,
                tool_calls_json=json.dumps(tool_calls, ensure_ascii=False),
            )

            tool_results = tool_executor.execute_tool_calls(tool_calls)

            agent_run_service.update_tool_results(
                run_id=run_id,
                tool_results_json=json.dumps(tool_results, ensure_ascii=False),
            )

        # 8. 第二轮推理：基于最终 tool_results 生成最终答复
        final_prompt = self._build_final_prompt(
            planner_output=planner_output_json,
            tool_results=tool_results,
        )

        agent_run_service.update_final_prompt(
            run_id=run_id,
            final_prompt=final_prompt,
        )

        final_llm_result = llm_service.structured_chat(
            system_prompt="你是 Workflow3 的最终答复决策器，只输出 JSON。",
            user_prompt=final_prompt,
        )

        final_output_json = final_llm_result["parsed_json"]

        agent_run_service.update_final_output(
            run_id=run_id,
            final_output_json=json.dumps(final_output_json, ensure_ascii=False),
        )

        final_output_json = final_llm_result["parsed_json"]

        # 先取最终状态和回复
        final_status = final_output_json.get("final_status", "success")
        final_reply = final_output_json.get("reply", "Agent 已完成任务处理。")
        next_action = final_output_json.get("next_action", "")

        # 8.5 如果本轮进入“材料确认阶段”，则把 waiting_for 写入 session
        if (
                isinstance(next_action, str)
                and "确认" in next_action
        ) or (
                isinstance(final_reply, str)
                and "请确认" in final_reply
                and (
                        "blank_pdf" in final_reply
                        or "空白试卷" in final_reply
                        or "解析试卷" in final_reply
                        or "solution_pdf" in final_reply
                )
        ):
            chat_session_service.update_waiting_for(chat_id, "materials_confirmation")
        else:
            chat_session_service.update_waiting_for(chat_id, None)

        # 最后再写 final_output 到 agent_runs
        agent_run_service.update_final_output(
            run_id=run_id,
            final_output_json=json.dumps(final_output_json, ensure_ascii=False),
        )

        latency_ms = int((datetime.now() - started_at).total_seconds() * 1000)

        agent_run_service.finish_run(
            run_id=run_id,
            status=final_status,
            latency_ms=latency_ms,
            final_reply=final_reply,
        )

        chat_session_service.update_mode(chat_id, "idle")
        chat_session_service.update_summary_memory(
            chat_id=chat_id,
            summary_memory=f"最近一次 agent 闭环决策完成，run_id={run_id}",
        )

        logger.info("Agent handle_event success. run_id=%s", run_id)

        return {
            "run_id": run_id,
            "status": final_status,
            "reply": final_reply,
            "planner_output": planner_output_json,
            "tool_results": tool_results,
            "final_output": final_output_json,
            "llm_result": llm_result,
            "final_llm_result": final_llm_result,
        }

    def _sync_task_to_session(
            self,
            chat_id: str,
            tool_results: list[dict[str, Any]],
    ) -> dict | None:
        """
        通用 task 同步逻辑：

        从任意 tool 执行结果中提取 task_id，
        写回 session + binding，保证任务在多轮对话中不丢失。

        return:
            {
                "task_id": xxx,
                "should_continue": True
            }
        """

        for item in tool_results:
            if item.get("status") != "success":
                continue

            result = item.get("result") or {}
            task_id = result.get("task_id")

            if not task_id:
                continue

            # ✅ 写回 session
            chat_session_service.update_current_task(chat_id, task_id)

            # ✅ 写入 binding（避免丢任务）
            chat_task_binding_service.bind(chat_id, task_id)

            logger.info(
                "Task synced from tool result. chat_id=%s, task_id=%s, tool=%s",
                chat_id,
                task_id,
                item.get("tool"),
            )

            return {
                "task_id": task_id,
                "should_continue": True,
            }

        return None


    def _is_confirmation_message(self, text: str | None) -> bool:
        if not text:
            return False

        normalized = text.strip().lower()

        keywords = [
            "确认",
            "确认无误",
            "没问题",
            "对的",
            "正确",
            "可以",
            "继续",
            "继续吧",
            "渲染吧",
            "开始渲染",
            "111",
            "ok",
            "okk"
        ]

        return any(k in normalized for k in keywords)


    def _maybe_attach_last_uploaded_file(
            self,
            chat_id: str,
            task_id: str | None,
            session: dict[str, Any] | None,
            artifacts: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """
        如果：
        1. 当前已有 task_id
        2. session 里存在最近上传文件
        3. 该最近上传文件还没有挂到当前 task

        则自动把最近上传文件挂到当前 task。
        """
        if not task_id:
            return None

        if not session:
            return None

        last_uploaded_file_name = session.get("last_uploaded_file_name")
        if not last_uploaded_file_name:
            return None

        last_uploaded_file_key = session.get("last_uploaded_file_key")

        # 判断这个“最近上传文件”是否已经挂到当前 task
        already_attached = False
        for item in artifacts:
            if (
                    item.get("task_id") == task_id
                    and item.get("artifact_name") == last_uploaded_file_name
            ):
                already_attached = True
                break

        if already_attached:
            logger.info(
                "Last uploaded file already attached. chat_id=%s, task_id=%s, file_name=%s",
                chat_id,
                task_id,
                last_uploaded_file_name,
            )
            return None

        logger.info(
            "Auto attaching last uploaded file to task. chat_id=%s, task_id=%s, file_name=%s, file_key=%s",
            chat_id,
            task_id,
            last_uploaded_file_name,
            last_uploaded_file_key,
        )

        auto_tool_call = {
            "tool": "attach_last_uploaded_file_to_task",
            "args": {
                "chat_id": chat_id,
                "task_id": task_id,
            },
        }

        result = tool_executor.execute_tool_call(auto_tool_call)
        logger.info("Auto attach result: %s", result)
        return result

    def _build_system_prompt(self) -> str:
        tool_prompt = self._build_tool_prompt()

        return (
            "你是 Workflow3 的任务型 Agent。\n"
            "你的职责是根据当前事件、会话上下文、任务记忆和产物信息，"
            "输出一个严格的 JSON 决策结果。\n"
            "你不能输出 markdown，不要输出解释性前缀，不要输出代码块。\n"
            "你必须只输出一个 JSON object。\n"
            "严禁输出自然语言解释、严禁输出 [TOOL_CALL]、严禁输出 markdown、严禁输出代码块。\n"
            "如果你想调用工具，只能把它放进 JSON 的 tool_calls 字段里。\n"
            "任何非 JSON 内容都会导致系统解析失败。\n"
            f"{tool_prompt}\n\n"
            "重要规则：\n"
            "1. tool_calls 里只能使用上面列出的已注册工具名。\n"
            "2. 不允许虚构工具名，不允许输出未注册工具。\n"
            "3. 如果现有工具不足以完成任务，就让 tool_calls 为空，并在 reply 中说明原因。\n\n"
            "4. 如果当前上下文中已经存在 task_id，那么所有需要操作任务的 tool_calls 都必须显式带上 task_id。\n"
            "5. 不允许省略 task_id，也不允许假设系统会自动补全 task_id。\n\n"
            "JSON 格式要求：\n"
            "{\n"
            '  "intent": "字符串，表示用户意图",\n'
            '  "task_action": "字符串，表示是新任务、继续任务、等待用户输入等",\n'
            '  "reason": "字符串，说明判断原因",\n'
            '  "tool_calls": [\n'
            "    {\n"
            '      "tool": "工具名，必须来自已注册工具列表",\n'
            '      "args": {}\n'
            "    }\n"
            "  ],\n"
            '  "reply": "给用户的自然语言回复"\n'
            "}\n"
        )

    def _build_user_prompt(
        self,
        chat_id: str,
        event_type: str,
        user_message: str | None,
        task_id: str | None,
        file_name: str | None,
        retrieved_context: dict[str, Any],
    ) -> str:
        return (
            f"当前事件信息如下：\n"
            f"- chat_id: {chat_id}\n"
            f"- event_type: {event_type}\n"
            f"- task_id: {task_id}\n"
            f"- user_message: {user_message}\n"
            f"- file_name: {file_name}\n\n"
            f"当前检索到的上下文如下：\n"
            f"{json.dumps(retrieved_context, ensure_ascii=False, indent=2)}\n\n"
            "请根据这些信息，输出严格 JSON，判断：\n"
            "1. 当前用户意图是什么\n"
            "2. 是新任务还是继续旧任务\n"
            "3. 建议调用哪些工具\n"
            "4. 给用户一句简洁回复\n"
        )

    def _build_final_prompt(
            self,
            planner_output: dict[str, Any],
            tool_results: list[dict[str, Any]],
    ) -> str:
        return (
            "你是 Workflow3 的任务型 Agent。\n"
            "现在你已经完成了第一轮决策，并且系统已经执行了工具。\n"
            "请基于第一轮决策和工具执行结果，输出最终严格 JSON。\n"
            "不要输出 markdown，不要输出代码块，只输出 JSON object。\n\n"
            "严禁输出自然语言解释、严禁输出 markdown、严禁输出代码块、严禁输出 [TOOL_CALL] 或类似标签。\n"
            "你必须只输出一个合法 JSON object，不能输出 JSON 之外的任何字符。\n"
            "重要判断规则：\n"
            "1. 工具执行结果（tool_results）是本轮最新事实来源，优先级高于 task_memory 等历史缓存字段。\n"
            "2. 如果 tool_results 中已经给出了 missing_materials、has_missing、artifact_types 等结果，必须优先依据这些结果判断。\n"
            "3. 不要仅根据旧的 memory.missing_materials_json 下结论。\n"
            "4. 如果工具结果和 memory 不一致，以工具结果为准。\n"
            "5. 如果缺少 blank_pdf 或 solution_pdf，就应判断为 waiting_user，而不是 success。\n"
            "6. 如果材料齐全，不能直接自动渲染，先要求用户确认。\n"
            "7. 如果 tool_results 中存在 check_missing_materials 工具结果，优先直接读取其 result.missing 字段生成最终答复。\n"
            "8. 如果工具结果显示 excel、blank_pdf、solution_pdf 都已齐全，不要立刻自动开始渲染。请先列出当前任务绑定的材料文件名和 PDF 页数，并请求用户确认这些文件是否正确。\n"
            "9. 只有当用户明确回复“确认”“确认无误”“没问题”“正确”等确认意图后，才可以进入 render_pdf_pages_from_task。\n\n"
            "10. 如果当前阶段是材料确认阶段，则只能围绕“材料是否正确”进行回复，不要扩展到 OCR、切题、生成答题卡、批改解析、JSON生成、云同步等后续功能。\n"
            "11. 材料确认阶段的回复目标只有两个：列出材料信息、请求用户确认。\n"
            "12. 未收到用户确认之前，不允许讨论后续处理细节，也不允许让用户选择 OCR 或其他步骤。\n"
            "13. 如果 tool_results 中存在 summarize_task_materials 结果，则确认回复必须直接使用其中的 artifact_name 和 page_count 字段，不要用“1个文件”这类笼统表述代替。\n\n"
            "输出格式要求：\n"
            "{\n"
            '  "final_status": "success / waiting_user / failed / partial_success",\n'
            '  "reason": "字符串，说明最终判断原因",\n'
            '  "next_action": "字符串，表示下一步动作",\n'
            '  "reply": "给用户的最终自然语言回复"\n'
            "}\n\n"
            f"第一轮决策结果如下：\n{json.dumps(planner_output, ensure_ascii=False, indent=2)}\n\n"
            f"工具执行结果如下：\n{json.dumps(tool_results, ensure_ascii=False, indent=2)}\n"
        )

    def _build_tool_prompt(self) -> str:
        return (
            "当前系统已注册、允许调用的工具如下：\n"
            "- get_task_state: 获取任务当前状态、artifact情况和最新缺失材料；args: {task_id: str}\n"
            "- check_missing_materials: 重新根据 artifacts 计算缺失材料，并同步更新 task_memory；args: {task_id: str}\n"
            "- task_create: 创建任务；args: {created_by: str}\n"
            "- task_update_status: 更新任务状态；args: {task_id: str, status: str}\n"
            "- render_pdf_pages_from_task: 根据 task_id 自动查找 blank_pdf 和 solution_pdf 并渲染页图；args: {task_id: str, dpi: int}\n"
            "\n"
            "重要：如果要判断当前缺少哪些材料，优先调用 check_missing_materials，或调用 get_task_state（它会返回最新缺失材料）。\n"
            "注意：tool_calls 中 args 只能包含该工具声明的参数，不能添加其他字段。\n"
        )


agent_service = AgentService()