from __future__ import annotations

from app.infrastructure.llm.base_llm_client import BaseLLMClient


class MockLLMClient(BaseLLMClient):
    def structured_chat(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> dict:
        user_prompt_lower = user_prompt.lower()

        if "processing" in user_prompt_lower:
            return {
                "intent": "processing_in_progress",
                "action": "reply_only",
                "reply": "当前任务已进入处理阶段，我会继续执行后续步骤。",
                "should_call_tool": False,
                "tool_name": None,
                "tool_args": {},
            }

        if "waiting_confirmation" in user_prompt_lower:
            return {
                "intent": "confirm_materials",
                "action": "ask_for_confirmation",
                "reply": "当前材料已就绪，请确认 blank_pdf 和 solution_pdf 是否正确。",
                "should_call_tool": False,
                "tool_name": None,
                "tool_args": {},
            }

        if "collecting_materials" in user_prompt_lower:
            return {
                "intent": "collect_materials",
                "action": "request_upload",
                "reply": "请上传 blank_pdf 和 solution_pdf，我会继续处理。",
                "should_call_tool": False,
                "tool_name": None,
                "tool_args": {},
            }




        return {
            "intent": "general_continue",
            "action": "reply_only",
            "reply": "我已收到你的消息，正在继续当前任务。",
            "should_call_tool": False,
            "tool_name": None,
            "tool_args": {},
        }