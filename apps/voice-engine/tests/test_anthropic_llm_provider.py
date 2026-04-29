"""Unit tests for ``AnthropicLLMProvider``.

Covers the Messages API wiring (system-prompt extraction, role
mapping, text-block concatenation) using a stub SDK object so the
tests never make a network call.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from src.adapters import anthropic_llm_provider as module
from src.adapters.anthropic_llm_provider import AnthropicLLMProvider
from src.domain.ports.llm_provider import LLMMessage

pytestmark = pytest.mark.asyncio


@dataclass
class _TextBlock:
    text: str


@dataclass
class _FakeResponse:
    content: list[_TextBlock]


class _FakeMessages:
    def __init__(self, reply_text: str) -> None:
        self.reply_text = reply_text
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> _FakeResponse:
        self.calls.append(kwargs)
        return _FakeResponse(content=[_TextBlock(text=self.reply_text)])


class _FakeAnthropic:
    def __init__(self, api_key: str, reply_text: str = "Thanks, got it.") -> None:
        self.api_key = api_key
        self.messages = _FakeMessages(reply_text)


class _FakeAnthropicModule:
    def __init__(self, reply_text: str = "Thanks, got it.") -> None:
        self._reply_text = reply_text
        self.last_client: _FakeAnthropic | None = None

    def AsyncAnthropic(self, api_key: str) -> _FakeAnthropic:  # noqa: N802
        client = _FakeAnthropic(api_key=api_key, reply_text=self._reply_text)
        self.last_client = client
        return client


async def test_complete_splits_system_prompts_from_turns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeAnthropicModule(reply_text="Ack ✓")
    monkeypatch.setattr(module, "anthropic", fake)

    provider = AnthropicLLMProvider(api_key="sk-test", default_model="claude-haiku")
    reply = await provider.complete(
        [
            LLMMessage(role="system", content="Be brief."),
            LLMMessage(role="user", content="Hello"),
            LLMMessage(role="assistant", content="Hi there"),
            LLMMessage(role="user", content="How are you?"),
        ],
        max_tokens=64,
    )

    assert reply == "Ack ✓"
    assert fake.last_client is not None
    call = fake.last_client.messages.calls[0]
    assert call["model"] == "claude-haiku"
    assert call["max_tokens"] == 64
    assert call["system"] == "Be brief."
    assert call["messages"] == [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there"},
        {"role": "user", "content": "How are you?"},
    ]


async def test_complete_inserts_synthetic_user_when_turns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeAnthropicModule(reply_text="…")
    monkeypatch.setattr(module, "anthropic", fake)

    provider = AnthropicLLMProvider(api_key="sk-test")
    await provider.complete([LLMMessage(role="system", content="Rules.")])

    assert fake.last_client is not None
    call = fake.last_client.messages.calls[0]
    assert call["messages"] == [{"role": "user", "content": "Please continue."}]


async def test_complete_without_api_key_raises_at_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeAnthropicModule()
    monkeypatch.setattr(module, "anthropic", fake)

    provider = AnthropicLLMProvider(api_key="")
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        await provider.complete([LLMMessage(role="user", content="hi")])


async def test_complete_without_sdk_raises_at_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(module, "anthropic", None)

    provider = AnthropicLLMProvider(api_key="sk-test")
    with pytest.raises(RuntimeError, match="anthropic SDK is not installed"):
        await provider.complete([LLMMessage(role="user", content="hi")])
