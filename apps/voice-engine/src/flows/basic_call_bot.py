"""Scripted conversation FrameProcessor for the basic call (Phase 3 Rev 1).

Runs the :class:`BasicCallScript` against a Pipecat pipeline:

  TRANSPORT_IN ─► STT ─► ScriptedConversation ─► TTS ─► TRANSPORT_OUT

State machine inside :class:`ScriptedConversation`:

    IDLE ─(StartFrame)─► SPEAKING_GREETING
    SPEAKING_GREETING ─(combined greeting+question TTS enqueued)─► WAITING_FOR_REPLY
    WAITING_FOR_REPLY ─(TranscriptionFrame)─► GENERATING_ACK
    GENERATING_ACK ─(LLM returns)─► SPEAKING_ACK
    SPEAKING_ACK ─(TTS enqueued)─► SPEAKING_GOODBYE
    SPEAKING_GOODBYE ─(TTS enqueued, sleep for audio)─► ENDING
    ENDING → emit EndFrame → pipeline drains → transport.hangup()

Note: SPEAKING_QUESTION state exists in the enum for backwards compatibility
but is no longer visited in the flow — greeting and question are emitted as
a single TTS call.

Pipecat is imported lazily so the lean CI image still loads the
module. Tests that want to cover the state machine can import
:class:`ConversationState` directly without depending on Pipecat.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from enum import Enum
from typing import Any

from src.domain.ports.llm_provider import ILLMProvider, LLMMessage
from src.flows.greeting_flow import BasicCallScript

logger = logging.getLogger(__name__)


class ConversationState(str, Enum):
    IDLE = "idle"
    SPEAKING_GREETING = "speaking_greeting"
    SPEAKING_QUESTION = "speaking_question"
    WAITING_FOR_REPLY = "waiting_for_reply"
    GENERATING_ACK = "generating_ack"
    SPEAKING_ACK = "speaking_ack"
    SPEAKING_GOODBYE = "speaking_goodbye"
    ENDING = "ending"


class ScriptedConversationMixin:
    """State machine + LLM plumbing.

    Split out as a plain mixin so mypy can type-check the logic
    without needing Pipecat's ``FrameProcessor`` base in scope. The
    runtime class (built in :func:`build_scripted_conversation`)
    inherits from both this mixin and Pipecat's ``FrameProcessor``.
    """

    def __init__(
        self,
        *,
        script: BasicCallScript,
        llm_provider: ILLMProvider | None,
        on_call_ended: Callable[[], Awaitable[None] | None] | None,
        ack_timeout_seconds: float,
        reply_timeout_seconds: float,
        reply_pause_seconds: float,
        wait_for_participant: bool = False,
        post_speech_delay_seconds: float | None = None,
    ) -> None:
        self._state: ConversationState = ConversationState.IDLE
        self._script = script
        self._llm = llm_provider
        self._ack_timeout = ack_timeout_seconds
        self._reply_timeout = reply_timeout_seconds
        self._reply_pause = reply_pause_seconds
        self._on_call_ended = on_call_ended
        self._reply_buffer: list[str] = []
        self._reply_waiter: asyncio.Task[None] | None = None
        self._ended = False
        # None → estimate delay from word count at runtime; explicit float → use that value.
        # Set to 0.0 in test harnesses where _emit_tts is a no-op.
        self._post_speech_delay: float | None = post_speech_delay_seconds
        # When True, _start_conversation waits until on_participant_joined() is called
        self._participant_ready: asyncio.Event | None = (
            asyncio.Event() if wait_for_participant else None
        )

    # Overridden at runtime by the concrete FrameProcessor subclass.
    async def _push_frame(self, frame: Any, direction: Any) -> None:
        raise NotImplementedError

    async def _emit_tts(self, text: str) -> None:
        raise NotImplementedError

    async def _emit_end(self) -> None:
        raise NotImplementedError

    # ─── State transitions ───────────────────────────────────────────

    def on_participant_joined(self) -> None:
        """Unblock _start_conversation when wait_for_participant=True."""
        if self._participant_ready is not None:
            self._participant_ready.set()

    async def _start_conversation(self) -> None:
        if self._state != ConversationState.IDLE:
            return
        if self._participant_ready is not None:
            logger.info("ScriptedConversation: waiting for participant to join…")
            await self._participant_ready.wait()
            # Brief pause so the browser can subscribe to the bot's audio track
            # before we start speaking — without this the first ~500ms of the
            # greeting may be missed because the track subscription hasn't
            # completed on the client side yet.
            await asyncio.sleep(1.0)
            logger.info("ScriptedConversation: participant joined — starting conversation")
        self._state = ConversationState.SPEAKING_GREETING
        logger.info("→ TTS [greeting]: %s", self._script.greeting[:120])
        logger.info("→ TTS [question]: %s", self._script.question[:120])
        # Emit greeting and question as one TTS call so the speech engine
        # produces natural prosody across the full intro without a jarring
        # gap between the two utterances.
        await self._emit_tts(f"{self._script.greeting} {self._script.question}")
        self._state = ConversationState.WAITING_FOR_REPLY
        asyncio.create_task(self._reply_timeout_guard())

    def _buffer_reply(self, text: str) -> None:
        if self._state != ConversationState.WAITING_FOR_REPLY:
            return
        cleaned = text.strip()
        if not cleaned:
            return
        logger.info("← STT [candidate]: %s", cleaned[:200])
        self._reply_buffer.append(cleaned)
        if self._reply_waiter is not None:
            self._reply_waiter.cancel()
        self._reply_waiter = asyncio.create_task(
            self._finalise_reply_after_pause()
        )

    async def _finalise_reply_after_pause(self) -> None:
        try:
            await asyncio.sleep(self._reply_pause)
        except asyncio.CancelledError:
            return
        if self._state != ConversationState.WAITING_FOR_REPLY:
            return
        reply = " ".join(self._reply_buffer).strip()
        if not reply:
            return
        await self._on_reply_complete(reply)

    async def _reply_timeout_guard(self) -> None:
        await asyncio.sleep(self._reply_timeout)
        if self._state == ConversationState.WAITING_FOR_REPLY:
            logger.info(
                "ScriptedConversation: reply timeout; using fallback ack",
            )
            await self._on_reply_complete("")

    async def _on_reply_complete(self, reply: str) -> None:
        self._state = ConversationState.GENERATING_ACK
        if reply:
            logger.info("← STT [candidate, final]: %s", reply[:200])
        ack = await self._generate_ack(reply)
        self._state = ConversationState.SPEAKING_ACK
        logger.info("→ TTS [ack]: %s", ack[:120])
        await self._emit_tts(ack)
        self._state = ConversationState.SPEAKING_GOODBYE
        logger.info("→ TTS [goodbye]: %s", self._script.goodbye[:120])
        await self._emit_tts(self._script.goodbye)
        self._state = ConversationState.ENDING
        # push_frame(TTSSpeakFrame) returns immediately — TTS synthesis and
        # audio streaming happen asynchronously downstream. Sleep for the
        # estimated playback duration before sending EndFrame so the call
        # does not disconnect while the bot is still speaking.
        await self._sleep_for_speech(f"{ack} {self._script.goodbye}")
        await self._end()

    async def _sleep_for_speech(self, text: str) -> None:
        """Sleep long enough for the TTS pipeline to finish speaking *text*.

        If ``post_speech_delay_seconds`` was set at construction time that
        value is used directly (pass ``0.0`` in test harnesses). Otherwise
        the delay is estimated from the word count: approx. 130 wpm + 5 s
        headroom for TTS API latency and WebRTC network buffer.
        """
        if self._post_speech_delay is not None:
            await asyncio.sleep(self._post_speech_delay)
            return
        words = len(text.split())
        seconds = (words / 130.0) * 60.0 + 5.0
        logger.debug(
            "Waiting %.1fs for TTS/audio to complete (%d words)", seconds, words
        )
        await asyncio.sleep(seconds)

    async def _generate_ack(self, reply: str) -> str:
        if not reply or self._llm is None:
            return self._script.fallback_ack()
        prompt = self._script.build_ack_messages(reply)
        messages = [
            LLMMessage(role=m["role"], content=m["content"]) for m in prompt
        ]
        logger.info("→ LLM [ack request]: generating acknowledgement for %d-char reply", len(reply))
        try:
            ack = await asyncio.wait_for(
                self._llm.complete(messages, max_tokens=80),
                timeout=self._ack_timeout,
            )
        except TimeoutError:
            logger.warning("LLM ack timed out after %.1fs", self._ack_timeout)
            return self._script.fallback_ack()
        except Exception:
            logger.exception("LLM ack failed")
            return self._script.fallback_ack()

        ack = (ack or "").strip()
        logger.info("← LLM [ack response]: %s", ack[:120])
        return ack or self._script.fallback_ack()

    async def _end(self) -> None:
        if self._ended:
            return
        self._ended = True
        await self._emit_end()
        if self._on_call_ended is not None:
            try:
                result = self._on_call_ended()
                if asyncio.iscoroutine(result):
                    await result
            except Exception:  # pragma: no cover — defensive
                logger.exception("on_call_ended callback failed")


def build_scripted_conversation(
    *,
    script: BasicCallScript,
    llm_provider: ILLMProvider | None,
    on_call_ended: Callable[[], Awaitable[None] | None] | None = None,
    ack_timeout_seconds: float = 10.0,
    reply_timeout_seconds: float = 90.0,
    reply_pause_seconds: float = 1.5,
    wait_for_participant: bool = False,
    post_speech_delay_seconds: float | None = None,
) -> Any:
    """Instantiate the ScriptedConversation Pipecat FrameProcessor."""

    # Lazy imports keep the lean CI image (no [voice] extras) happy.
    try:
        from pipecat.frames.frames import (
            EndFrame,
            StartFrame,
            TranscriptionFrame,
            TTSSpeakFrame,
        )
        from pipecat.processors.frame_processor import (
            FrameDirection,
            FrameProcessor,
        )
    except ImportError as exc:  # pragma: no cover — lean CI only
        raise RuntimeError(
            "pipecat-ai is not installed; install voice-engine with "
            "`pip install -e .[voice]` to use the basic-call pipeline."
        ) from exc

    class ScriptedConversation(ScriptedConversationMixin, FrameProcessor):
        def __init__(self) -> None:
            FrameProcessor.__init__(self)
            ScriptedConversationMixin.__init__(
                self,
                script=script,
                llm_provider=llm_provider,
                on_call_ended=on_call_ended,
                ack_timeout_seconds=ack_timeout_seconds,
                reply_timeout_seconds=reply_timeout_seconds,
                reply_pause_seconds=reply_pause_seconds,
                wait_for_participant=wait_for_participant,
                post_speech_delay_seconds=post_speech_delay_seconds,
            )

        async def process_frame(
            self,
            frame: Any,
            direction: Any,
        ) -> None:
            await FrameProcessor.process_frame(self, frame, direction)
            await self.push_frame(frame, direction)

            if isinstance(frame, StartFrame):
                await self._start_conversation()
                return

            if (
                isinstance(frame, TranscriptionFrame)
                and direction == FrameDirection.DOWNSTREAM
            ):
                self._buffer_reply(getattr(frame, "text", "") or "")

        async def _emit_tts(self, text: str) -> None:
            await self.push_frame(TTSSpeakFrame(text), FrameDirection.DOWNSTREAM)

        async def _emit_end(self) -> None:
            await self.push_frame(EndFrame(), FrameDirection.DOWNSTREAM)

    return ScriptedConversation()


__all__ = [
    "ConversationState",
    "ScriptedConversationMixin",
    "build_scripted_conversation",
]
