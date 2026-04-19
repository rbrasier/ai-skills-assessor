"""``ILLMProvider`` port — text generation abstraction (stub for Phase 1)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


class ILLMProvider(ABC):
    @abstractmethod
    async def complete(
        self,
        messages: list[LLMMessage],
        model: str | None = None,
        max_tokens: int = 1024,
    ) -> str:
        """Return a single text completion for the supplied messages."""
        ...
