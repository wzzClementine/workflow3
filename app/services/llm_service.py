import json
import re
import time
from typing import Any

from openai import OpenAI

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(settings.log_level, settings.logs_dir)


class LLMService:
    def __init__(self) -> None:
        self.provider = settings.llm_provider
        self.model_name = settings.volcengine_model or "ark-code-latest"
        self.mock_mode = settings.llm_mock_mode

        self.api_key = settings.volcengine_api_key
        self.base_url = settings.volcengine_base_url

        self.client: OpenAI | None = None

        if not self.mock_mode:
            if not self.api_key:
                raise ValueError("缺少 VOLCENGINE_API_KEY，无法初始化真实 LLM 客户端。")
            if not self.base_url:
                raise ValueError("缺少 VOLCENGINE_BASE_URL，无法初始化真实 LLM 客户端。")

            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
            )

    def health_check(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model_name": self.model_name,
            "mock_mode": self.mock_mode,
            "status": "ready",
        }

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 2000,
    ) -> dict[str, Any]:
        started_at = time.time()

        logger.info(
            "LLM chat called. provider=%s, model=%s, mock_mode=%s",
            self.provider,
            self.model_name,
            self.mock_mode,
        )
        logger.info("LLM system_prompt: %s", system_prompt)
        logger.info("LLM user_prompt: %s", user_prompt)

        if self.mock_mode:
            content = self._mock_chat_response(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        else:
            content = self._call_real_llm(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        latency_ms = int((time.time() - started_at) * 1000)

        return {
            "provider": self.provider,
            "model_name": self.model_name,
            "content": content,
            "latency_ms": latency_ms,
        }

    def structured_chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 2000,
    ) -> dict[str, Any]:
        started_at = time.time()

        # 第一次调用
        first_result = self.chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        first_content = first_result["content"]

        try:
            parsed_json = self._extract_json(first_content)
            total_latency_ms = int((time.time() - started_at) * 1000)
            return {
                "provider": first_result["provider"],
                "model_name": first_result["model_name"],
                "content": first_content,
                "parsed_json": parsed_json,
                "latency_ms": total_latency_ms,
                "retry_used": False,
            }
        except Exception as first_error:
            logger.warning(
                "LLM structured_chat first parse failed: %s. raw_content=%s",
                first_error,
                first_content,
            )

        # 第二次调用：纠错重试
        repair_system_prompt = (
            "你是一个 JSON 修复器。\n"
            "你必须只输出一个合法 JSON object。\n"
            "严禁输出自然语言解释、严禁输出 markdown、严禁输出代码块、严禁输出 [TOOL_CALL]、严禁输出任何 JSON 之外的字符。\n"
            "如果原始内容中包含工具调用意图，请把它整理进 JSON 字段，而不是用自定义标记。\n"
        )
        repair_user_prompt = self._build_json_repair_prompt(first_content)

        second_result = self.chat(
            system_prompt=repair_system_prompt,
            user_prompt=repair_user_prompt,
            temperature=0.0,
            max_tokens=max_tokens,
        )

        second_content = second_result["content"]

        try:
            parsed_json = self._extract_json(second_content)
            total_latency_ms = int((time.time() - started_at) * 1000)
            return {
                "provider": second_result["provider"],
                "model_name": second_result["model_name"],
                "content": second_content,
                "parsed_json": parsed_json,
                "latency_ms": total_latency_ms,
                "retry_used": True,
            }
        except Exception as second_error:
            logger.error(
                "LLM structured_chat retry parse failed: %s. raw_content=%s",
                second_error,
                second_content,
            )
            raise ValueError(
                "无法从 LLM 输出中解析 JSON。第一次输出与重试输出都不是合法 JSON。"
            ) from second_error

    def _build_json_repair_prompt(self, raw_text: str) -> str:
        return (
            "下面是模型刚才输出的原始内容，但它不是合法 JSON。\n"
            "请你严格重写为一个合法 JSON object。\n"
            "要求：\n"
            "1. 只输出 JSON object\n"
            "2. 不要输出解释\n"
            "3. 不要输出 markdown\n"
            "4. 不要输出 [TOOL_CALL] 或任何自定义标签\n"
            "5. 如果原文中已经表达了工具调用意图，请将其整理进 JSON 的 tool_calls 字段\n\n"
            f"原始内容如下：\n{raw_text}"
        )

    def _extract_json(self, text: str) -> dict[str, Any]:
        text = text.strip()

        # 1. 先尝试直接解析
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return data
            raise ValueError("LLM 输出不是 JSON object")
        except Exception:
            pass

        # 2. 尝试提取 ```json ... ``` 代码块
        code_block_match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
        if code_block_match:
            candidate = code_block_match.group(1).strip()
            try:
                data = json.loads(candidate)
                if isinstance(data, dict):
                    return data
            except Exception:
                pass

        # 3. 尝试提取最外层大括号
        brace_match = re.search(r"(\{.*\})", text, re.DOTALL)
        if brace_match:
            candidate = brace_match.group(1).strip()
            try:
                data = json.loads(candidate)
                if isinstance(data, dict):
                    return data
            except Exception:
                pass

        # 4. 尝试去掉常见噪声标记后再提取
        cleaned = text
        cleaned = re.sub(r"\[/?TOOL_CALL\]", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"^.*?(\{)", r"\1", cleaned, flags=re.DOTALL)
        cleaned = cleaned.strip()

        brace_match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
        if brace_match:
            candidate = brace_match.group(1).strip()
            try:
                data = json.loads(candidate)
                if isinstance(data, dict):
                    return data
            except Exception:
                pass

        raise ValueError(f"无法从 LLM 输出中解析 JSON: {text}")

    def _mock_chat_response(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        lower_prompt = user_prompt.lower()

        if "json" in lower_prompt or "结构化" in user_prompt:
            return json.dumps(
                {
                    "intent": "generate_structured_output",
                    "reason": "mock mode 命中 JSON/结构化关键词",
                    "next_action": {
                        "tool": "generate_json_from_excel_and_images",
                        "args": {},
                    },
                    "reply": "这是 mock 模式下返回的结构化结果。",
                },
                ensure_ascii=False,
            )

        return "这是 mock 模式下的普通文本回复。"

    def _call_real_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        if not self.client:
            raise ValueError("真实 LLM 客户端尚未初始化。")

        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )

        content = response.choices[0].message.content
        if not content:
            raise ValueError("LLM 返回内容为空。")

        logger.info("LLM raw response: %s", content)
        return content.strip()


llm_service = LLMService()