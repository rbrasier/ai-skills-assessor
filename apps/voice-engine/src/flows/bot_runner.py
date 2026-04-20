"""Basic-call bot runner — Pipecat pipeline + Daily PSTN dial-out.

Phase 3 Revision 1: this module owns the Pipecat pipeline construction
and Daily event wiring. Everything here imports the ``[voice]`` extras;
it must be imported lazily so the lean CI image still boots.

Public entry point:

    bot = BasicCallBot(
        session_id=..., phone_number=..., room_url=..., room_token=...,
        settings=..., listener=..., llm_provider=...,
    )
    await bot.start()   # kicks off pipeline + dial-out
    await bot.wait()    # blocks until the pipeline terminates
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from src.config import Settings
from src.domain.ports.call_lifecycle_listener import ICallLifecycleListener
from src.domain.ports.llm_provider import ILLMProvider
from src.flows.basic_call_bot import build_scripted_conversation
from src.flows.greeting_flow import build_script

logger = logging.getLogger(__name__)


class BasicCallBot:
    """Owns a single Pipecat bot instance for one assessment session."""

    def __init__(
        self,
        *,
        session_id: str,
        phone_number: str,
        room_url: str,
        room_token: str,
        settings: Settings,
        listener: ICallLifecycleListener,
        llm_provider: ILLMProvider | None,
    ) -> None:
        self._session_id = session_id
        self._phone_number = phone_number
        self._room_url = room_url
        self._room_token = room_token
        self._settings = settings
        self._listener = listener
        self._llm = llm_provider

        self._transport: Any = None
        self._task: Any = None
        self._runner_task: asyncio.Task[None] | None = None
        self._dial_attempted = False
        self._dial_succeeded = False
        self._connected_notified = False

    # ─── Construction ────────────────────────────────────────────────

    def _build(self) -> Any:
        """Import Pipecat and assemble the pipeline + task."""
        # Lazy imports keep the lean CI image (no [voice] extras) happy.
        from pipecat.audio.vad.silero import SileroVADAnalyzer
        from pipecat.pipeline.pipeline import Pipeline
        from pipecat.pipeline.task import PipelineParams, PipelineTask
        from pipecat.services.deepgram.stt import DeepgramSTTService
        from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
        from pipecat.transports.daily.transport import (
            DailyParams,
            DailyTransport,
        )

        stt = DeepgramSTTService(
            api_key=self._settings.deepgram_api_key,
            model=self._settings.deepgram_model,
        )
        tts = ElevenLabsTTSService(
            api_key=self._settings.elevenlabs_api_key,
            voice_id=self._settings.elevenlabs_voice_id,
        )

        transport = DailyTransport(
            self._room_url,
            self._room_token,
            f"{self._settings.bot_name} — Assessment Bot",
            params=DailyParams(
                api_key=self._settings.daily_api_key,
                audio_in_enabled=True,
                audio_out_enabled=True,
                vad_analyzer=SileroVADAnalyzer(),
                transcription_enabled=False,
            ),
        )
        self._transport = transport

        script = build_script(
            bot_name=self._settings.bot_name,
            org_name=self._settings.bot_org_name,
        )
        conversation = build_scripted_conversation(
            script=script,
            llm_provider=self._llm,
            on_call_ended=self._handle_bot_initiated_hangup,
        )

        pipeline = Pipeline(
            [
                transport.input(),
                stt,
                conversation,
                tts,
                transport.output(),
            ]
        )

        task = PipelineTask(
            pipeline,
            params=PipelineParams(
                audio_in_sample_rate=8000,
                audio_out_sample_rate=8000,
            ),
        )
        self._task = task

        self._wire_daily_events(transport, task)
        return task

    # ─── Daily event handlers → listener port ───────────────────────

    def _wire_daily_events(self, transport: Any, task: Any) -> None:
        listener = self._listener
        session_id = self._session_id
        phone_number = self._phone_number
        caller_id = self._settings.daily_caller_id

        @transport.event_handler("on_joined")
        async def _on_joined(_transport: Any, _data: Any) -> None:
            if self._dial_attempted:
                return
            self._dial_attempted = True
            dial_params: dict[str, str] = {
                "phoneNumber": phone_number,
                "displayName": phone_number,
            }
            if caller_id:
                dial_params["callerId"] = caller_id
            logger.info(
                "BasicCallBot session_id=%s: start_dialout → %s",
                session_id,
                phone_number,
            )
            try:
                await transport.start_dialout(dial_params)
            except Exception as exc:  # pragma: no cover — adapter runtime
                logger.exception(
                    "start_dialout failed for session_id=%s", session_id
                )
                await listener.on_call_failed(
                    session_id, reason=f"dial_out_start_failed: {exc}"
                )
                await task.cancel()

        @transport.event_handler("on_dialout_answered")
        async def _on_answered(_transport: Any, _data: Any) -> None:
            self._dial_succeeded = True
            if not self._connected_notified:
                self._connected_notified = True
                await listener.on_call_connected(session_id)

        @transport.event_handler("on_dialout_connected")
        async def _on_connected(_transport: Any, _data: Any) -> None:
            if not self._connected_notified:
                self._connected_notified = True
                await listener.on_call_connected(session_id)

        @transport.event_handler("on_dialout_error")
        async def _on_dialout_error(_transport: Any, data: Any) -> None:
            logger.error(
                "dialout error session_id=%s data=%s", session_id, data
            )
            await listener.on_call_failed(
                session_id, reason=f"dialout_error: {data!s}"
            )
            await task.cancel()

        @transport.event_handler("on_dialout_warning")
        async def _on_dialout_warning(_transport: Any, data: Any) -> None:
            logger.warning(
                "dialout warning session_id=%s data=%s", session_id, data
            )

        @transport.event_handler("on_dialout_stopped")
        async def _on_dialout_stopped(_transport: Any, _data: Any) -> None:
            # The candidate hung up (or dial-out was cancelled). Treat
            # as a normal end; listener.on_call_ended is idempotent.
            await listener.on_call_ended(session_id)
            await task.cancel()

        @transport.event_handler("on_participant_left")
        async def _on_participant_left(
            _transport: Any, _participant: Any, _reason: Any
        ) -> None:
            await listener.on_call_ended(session_id)
            await task.cancel()

    async def _handle_bot_initiated_hangup(self) -> None:
        """Called by :class:`ScriptedConversation` after the goodbye."""
        await self._listener.on_call_ended(self._session_id)
        if self._task is not None:
            await self._task.cancel()

    # ─── Public lifecycle ────────────────────────────────────────────

    async def start(self) -> None:
        """Build the pipeline and launch it as a background task."""
        from pipecat.pipeline.runner import PipelineRunner

        task = self._build()
        runner = PipelineRunner(handle_sigint=False)

        async def _run() -> None:
            try:
                await runner.run(task)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception(
                    "BasicCallBot crashed session_id=%s", self._session_id
                )
                await self._listener.on_call_failed(
                    self._session_id,
                    reason=f"pipeline_crashed: {exc}",
                )

        self._runner_task = asyncio.create_task(_run())

    async def wait(self) -> None:
        if self._runner_task is None:
            return
        try:
            await self._runner_task
        except asyncio.CancelledError:
            pass

    async def cancel(self) -> None:
        if self._task is not None:
            try:
                await self._task.cancel()
            except Exception:  # pragma: no cover — defensive
                logger.exception("BasicCallBot.cancel task.cancel failed")
        if self._runner_task is not None and not self._runner_task.done():
            self._runner_task.cancel()


__all__ = ["BasicCallBot"]
