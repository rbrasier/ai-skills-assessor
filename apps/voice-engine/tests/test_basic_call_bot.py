"""Unit tests for the scripted-conversation state machine.

These cover :class:`ScriptedConversationMixin` directly — Pipecat's
``FrameProcessor`` is not imported or exercised here. The goal is to
prove the greeting → question → ack → goodbye → hangup sequence works
against the :class:`BasicCallScript` without needing the ``[voice]``
extras.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.domain.ports.llm_provider import ILLMProvider, LLMMessage
from src.flows.basic_call_bot import ConversationState, ScriptedConversationMixin
from src.flows.greeting_flow import build_script

pytestmark = pytest.mark.asyncio


class _RecordingHarness(ScriptedConversationMixin):
    """Test double: captures TTS / End calls instead of pushing frames."""

    def __init__(
        self,
        *,
        llm_provider: ILLMProvider | None = None,
        reply_pause_seconds: float = 0.01,
        ack_timeout_seconds: float = 5.0,
        reply_timeout_seconds: float = 30.0,
    ) -> None:
        super().__init__(
            script=build_script(),
            llm_provider=llm_provider,
            on_call_ended=self._on_ended,
            ack_timeout_seconds=ack_timeout_seconds,
            reply_timeout_seconds=reply_timeout_seconds,
            reply_pause_seconds=reply_pause_seconds,
        )
        self.spoken: list[str] = []
        self.ended = False
        self.end_callback_fired = False

    async def _push_frame(self, frame: Any, direction: Any) -> None:
        return

    async def _emit_tts(self, text: str) -> None:
        self.spoken.append(text)

    async def _emit_end(self) -> None:
        self.ended = True

    async def _on_ended(self) -> None:
        self.end_callback_fired = True


class _FakeLLM(ILLMProvider):
    def __init__(self, reply: str = "Got it, thanks for sharing.") -> None:
        self.reply = reply
        self.seen: list[list[LLMMessage]] = []

    async def complete(
        self,
        messages: list[LLMMessage],
        model: str | None = None,
        max_tokens: int = 1024,
    ) -> str:
        self.seen.append(messages)
        return self.reply


class _BoomLLM(ILLMProvider):
    async def complete(
        self,
        messages: list[LLMMessage],
        model: str | None = None,
        max_tokens: int = 1024,
    ) -> str:
        raise RuntimeError("llm boom")


async def test_full_sequence_with_llm_ack() -> None:
    llm = _FakeLLM(reply="Interesting — the platform team handles a lot.")
    harness = _RecordingHarness(llm_provider=llm)

    await harness._start_conversation()
    assert harness._state == ConversationState.WAITING_FOR_REPLY
    assert harness.spoken == [harness._script.greeting, harness._script.question]

    harness._buffer_reply("I lead the platform team and own our ingestion.")
    # Wait for debounce + LLM + goodbye.
    assert harness._reply_waiter is not None
    await harness._reply_waiter
    # Drain any follow-up tasks the mixin kicked off.
    import asyncio

    for _ in range(5):
        await asyncio.sleep(0)

    assert harness._state == ConversationState.ENDING
    assert harness.ended is True
    assert harness.end_callback_fired is True
    assert harness.spoken[2] == "Interesting — the platform team handles a lot."
    assert harness.spoken[3] == harness._script.goodbye
    assert len(llm.seen) == 1


async def test_llm_failure_falls_back_to_safe_ack() -> None:
    harness = _RecordingHarness(llm_provider=_BoomLLM())

    await harness._start_conversation()
    harness._buffer_reply("I do data engineering work.")
    assert harness._reply_waiter is not None
    await harness._reply_waiter

    assert harness.spoken[2] == harness._script.fallback_ack()
    assert harness.ended is True


async def test_empty_reply_does_not_finalise_early() -> None:
    harness = _RecordingHarness(llm_provider=_FakeLLM())
    await harness._start_conversation()
    harness._buffer_reply("   ")  # whitespace only
    # Nothing buffered, no waiter scheduled.
    assert harness._reply_waiter is None
    assert harness._state == ConversationState.WAITING_FOR_REPLY


async def test_transcription_ignored_outside_waiting_state() -> None:
    harness = _RecordingHarness(llm_provider=_FakeLLM())
    # Still IDLE
    harness._buffer_reply("Anything I say now should be dropped.")
    assert harness._reply_waiter is None
    assert harness._reply_buffer == []


async def test_end_is_idempotent() -> None:
    harness = _RecordingHarness(llm_provider=None)
    await harness._end()
    await harness._end()
    assert harness.ended is True
    # Callback fired exactly once.
    assert harness.end_callback_fired is True


async def test_without_llm_uses_fallback() -> None:
    harness = _RecordingHarness(llm_provider=None)
    await harness._start_conversation()
    harness._buffer_reply("I do platform engineering.")
    assert harness._reply_waiter is not None
    await harness._reply_waiter

    assert harness.spoken[2] == harness._script.fallback_ack()
    assert harness.ended is True
