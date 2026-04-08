from __future__ import annotations

from abc import ABC, abstractmethod


class BaseLLMClient(ABC):
    @abstractmethod
    def structured_chat(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> dict:
        raise NotImplementedError