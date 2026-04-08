from __future__ import annotations

from app.agent.planner.planner_input_builder import PlannerInputBuilder
from app.agent.planner.planner_models import PlannerDecision
from app.agent.schema import AgentEvent
from app.infrastructure.llm.base_llm_client import BaseLLMClient


class LLMPlanner:
    def __init__(
        self,
        llm_client: BaseLLMClient,
        planner_input_builder: PlannerInputBuilder,
    ):
        self.llm_client = llm_client
        self.planner_input_builder = planner_input_builder

    def plan(
        self,
        event: AgentEvent,
        snapshot: dict,
    ) -> PlannerDecision:
        planner_input = self.planner_input_builder.build(
            event=event,
            snapshot=snapshot,
        )

        raw = self.llm_client.structured_chat(
            system_prompt=planner_input.system_prompt,
            user_prompt=planner_input.user_prompt,
        )

        return PlannerDecision(
            intent=raw.get("intent", "unknown"),
            action=raw.get("action", "reply_only"),
            reply=raw.get("reply", "我已收到你的消息。"),
            should_call_tool=raw.get("should_call_tool", False),
            tool_name=raw.get("tool_name"),
            tool_args=raw.get("tool_args", {}) or {},
        )