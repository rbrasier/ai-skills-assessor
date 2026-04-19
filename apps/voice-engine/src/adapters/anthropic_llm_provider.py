"""Anthropic LLM provider adapter — stub for Phase 1."""

from __future__ import annotations

from src.domain.ports.llm_provider import ILLMProvider, LLMMessage


class AnthropicLLMProvider(ILLMProvider):
    def __init__(self, api_key: str, default_model: str = "claude-3-5-sonnet-latest") -> None:
        self._api_key = api_key
        self._default_model = default_model

    async def complete(
        self,
        messages: list[LLMMessage],
        model: str | None = None,
        max_tokens: int = 1024,
    ) -> str:
        raise NotImplementedError(
            "AnthropicLLMProvider.complete is implemented in the claim-extraction phase",
        )
