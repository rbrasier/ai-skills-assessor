"""Pipecat-compatible STT frame processor backed by a faster-whisper WebSocket server.

The remote server (apps/whisper-stt/) accepts raw PCM audio chunks over a
WebSocket connection and returns JSON transcript events:

    {"text": "partial transcript", "is_final": false}
    {"text": "final transcript",   "is_final": true}

This processor mirrors the position of DeepgramSTTService in the pipeline:
it consumes AudioRawFrame objects, suppresses them from flowing further, and
emits TranscriptionFrame / InterimTranscriptionFrame objects downstream.

Connection is established lazily on the first StartFrame so the process-level
asyncio event loop is available.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class WhisperSTTService:
    """Pipecat FrameProcessor wrapping a faster-whisper WebSocket STT server.

    Instantiated by the STT factory and inserted into the Pipecat pipeline at
    the same position as DeepgramSTTService.  All Pipecat-specific imports are
    deferred to ``_build_processor`` so the class can be constructed in unit
    tests without the ``[voice]`` extras installed.
    """

    def __init__(self, url: str) -> None:
        self._url = url
        self._processor: Any | None = None

    def build(self) -> Any:
        """Return a live Pipecat FrameProcessor.  Call inside ``_build()``."""
        if self._processor is None:
            self._processor = _build_processor(self._url)
        return self._processor


def _build_processor(url: str) -> Any:
    """Construct and return the actual Pipecat FrameProcessor instance."""
    from pipecat.frames.frames import (
        AudioRawFrame,
        EndFrame,
        Frame,
        StartFrame,
        TranscriptionFrame,
    )
    from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

    # InterimTranscriptionFrame was added in a later Pipecat version; fall back
    # gracefully when the installed version doesn't export it.
    try:
        from pipecat.frames.frames import InterimTranscriptionFrame
        _has_interim = True
    except ImportError:
        _has_interim = False

    class _WhisperFrameProcessor(FrameProcessor):
        """Stateful processor: one WebSocket connection per pipeline run."""

        def __init__(self) -> None:
            super().__init__()
            self._ws: Any | None = None
            self._recv_task: asyncio.Task[None] | None = None

        # ── connection management ────────────────────────────────────

        async def _connect(self) -> bool:
            try:
                import websockets
                self._ws = await websockets.connect(url, ping_interval=20, ping_timeout=10)
                self._recv_task = asyncio.create_task(self._receive_loop())
                logger.info("WhisperSTT: connected to %s", url)
                return True
            except Exception as exc:
                logger.error("WhisperSTT: connection failed (%s) — audio will be dropped", exc)
                self._ws = None
                return False

        async def _disconnect(self) -> None:
            if self._recv_task and not self._recv_task.done():
                self._recv_task.cancel()
                try:
                    await self._recv_task
                except asyncio.CancelledError:
                    pass
            if self._ws is not None:
                try:
                    await self._ws.close()
                except Exception:
                    pass
                self._ws = None
            logger.info("WhisperSTT: disconnected from %s", url)

        async def _receive_loop(self) -> None:
            try:
                async for raw in self._ws:  # type: ignore[union-attr]
                    try:
                        data: dict[str, Any] = json.loads(raw)
                    except json.JSONDecodeError:
                        logger.warning("WhisperSTT: non-JSON message: %r", raw)
                        continue
                    text: str = data.get("text", "").strip()
                    is_final: bool = bool(data.get("is_final", True))
                    if not text:
                        continue
                    if is_final:
                        frame: Frame = TranscriptionFrame(
                            text=text, user_id="", timestamp="", language="en"
                        )
                    elif _has_interim:
                        frame = InterimTranscriptionFrame(
                            text=text, user_id="", timestamp="", language="en"
                        )
                    else:
                        # Older Pipecat: treat interim as final so the
                        # conversation buffer still receives something.
                        frame = TranscriptionFrame(
                            text=text, user_id="", timestamp="", language="en"
                        )
                    await self.push_frame(frame, FrameDirection.DOWNSTREAM)
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                logger.error("WhisperSTT: receive loop error: %s", exc)

        # ── FrameProcessor contract ──────────────────────────────────

        async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
            await super().process_frame(frame, direction)

            if isinstance(frame, StartFrame):
                await self._connect()
                await self.push_frame(frame, direction)

            elif isinstance(frame, EndFrame):
                await self._disconnect()
                await self.push_frame(frame, direction)

            elif isinstance(frame, AudioRawFrame) and direction == FrameDirection.DOWNSTREAM:
                # Consume the audio frame — send bytes to Whisper; do NOT
                # push it further so the conversation processor isn't flooded.
                if self._ws is not None:
                    try:
                        await self._ws.send(frame.audio)
                    except Exception as exc:
                        logger.warning("WhisperSTT: send failed: %s", exc)
                        # Reconnect on next audio frame if the socket broke.
                        self._ws = None
            else:
                await self.push_frame(frame, direction)

    return _WhisperFrameProcessor()
