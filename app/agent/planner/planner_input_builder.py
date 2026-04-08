from __future__ import annotations

import json

from app.agent.planner.planner_models import PlannerInput
from app.agent.schema import AgentEvent


class PlannerInputBuilder:
    def build(
        self,
        event: AgentEvent,
        snapshot: dict,
    ) -> PlannerInput:
        system_prompt = (
            "你是 Workflow3 的任务型 Agent Planner。\n"
            "你必须基于当前任务状态、会话记忆和用户输入，输出一个严格的 JSON 决策。\n"
            "你不能自由发挥，也不能跳过状态机约束。\n"
            "如果当前任务处于 waiting_confirmation，则只能围绕“材料确认”做决策。\n"
            "如果当前任务处于 collecting_materials，则优先处理材料上传。\n"
            "如果当前任务处于 processing，则说明系统已经进入正式处理阶段，不要要求用户重新确认材料。\n"
            "如果事件类型为 file_upload，且 files 非空，应优先考虑调用 ingest_materials。\n"
            "当前允许使用的工具有：\n"
            "- manage_task\n"
            "- ingest_materials\n"
            "- process_paper\n"
            "其中：\n"
            "1. manage_task 支持 action=advance_stage / mark_failed\n"
            "2. ingest_materials 用于接收上传文件并登记材料\n"
            "3. process_paper 用于执行 PDF 转图片、切题、切解析、清洗解析\n"
            "你的输出必须包含以下字段：\n"
            "{\n"
            '  "intent": "字符串",\n'
            '  "action": "字符串",\n'
            '  "reply": "字符串",\n'
            '  "should_call_tool": true 或 false,\n'
            '  "tool_name": "字符串或 null",\n'
            '  "tool_args": {}\n'
            "}\n"
            "不要输出 markdown，不要输出代码块，不要输出解释。"
        )

        user_prompt = (
            f"当前事件：\n"
            f"- chat_id: {event.chat_id}\n"
            f"- event_type: {event.event_type}\n"
            f"- user_message: {event.user_message}\n"
            f"- files: {json.dumps([file.__dict__ for file in event.files], ensure_ascii=False)}\n\n"
            f"当前 snapshot：\n"
            f"{json.dumps(snapshot, ensure_ascii=False, indent=2)}\n\n"
            "请输出严格 JSON 决策。"
        )

        return PlannerInput(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            snapshot=snapshot,
        )