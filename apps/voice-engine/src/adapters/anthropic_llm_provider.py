"""Anthropic LLM provider adapter.

Implements :class:`ILLMProvider` against the Anthropic Python SDK. Kept
intentionally thin — Phase 3 Revision 1 only needs a one-shot text
completion for the bot's acknowledgement line. The retry / streaming
behaviour required by later phases (claim extraction, interjections)
lives in their own phases.

If the ``anthropic`` package is not installed (lean CI), importing this
module still works; calling ``complete`` raises a descriptive error so
the failure surfaces as a `/api/v1/assessment/trigger` 503, not a
startup crash.
"""

from __future__ import annotations

import logging
from typing import Any

from src.domain.ports.llm_provider import ILLMProvider, LLMMessage

logger = logging.getLogger(__name__)

_anthropic_module: Any
try:  # ``anthropic`` is part of the [voice] extras; CI's lean install skips it.
    import anthropic as _anthropic_module
except ImportError:  # pragma: no cover — exercised in lean CI only
    _anthropic_module = None

anthropic: Any = _anthropic_module


class AnthropicLLMProvider(ILLMProvider):
    def __init__(
        self,
        api_key: str,
        default_model: str = "claude-3-5-haiku-latest",
    ) -> None:
        self._api_key = api_key
        self._default_model = default_model
        self._client: Any = None

    def _get_client(self) -> Any:
        if anthropic is None:
            raise RuntimeError(
                "anthropic SDK is not installed; install voice-engine with "
                "`pip install -e .[voice]` to use AnthropicLLMProvider."
            )
        if not self._api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set; cannot call Anthropic API."
            )
        if self._client is None:
            self._client = anthropic.AsyncAnthropic(api_key=self._api_key)
        return self._client

    async def complete(
        self,
        messages: list[LLMMessage],
        model: str | None = None,
        max_tokens: int = 1024,
    ) -> str:
        client = self._get_client()

        # Anthropic's Messages API separates system prompts from user /
        # assistant turns; split the incoming list accordingly.
        system_parts: list[str] = []
        turns: list[dict[str, str]] = []
        for msg in messages:
            if msg.role == "system":
                system_parts.append(msg.content)
            elif msg.role in ("user", "assistant"):
                turns.append({"role": msg.role, "content": msg.content})
            else:
                logger.warning(
                    "AnthropicLLMProvider: ignoring unsupported role %r",
                    msg.role,
                )

        if not turns:
            # The API requires at least one user turn.
            turns.append({"role": "user", "content": "Please continue."})

        kwargs: dict[str, Any] = {
            "model": model or self._default_model,
            "max_tokens": max_tokens,
            "messages": turns,
        }
        if system_parts:
            kwargs["system"] = "\n\n".join(system_parts)

        response = await client.messages.create(**kwargs)

        # Concatenate text blocks — Claude may return multiple.
        chunks: list[str] = []
        for block in getattr(response, "content", []) or []:
            text = getattr(block, "text", None)
            if isinstance(text, str):
                chunks.append(text)
        return "".join(chunks).strip()


__all__ = ["AnthropicLLMProvider"]
