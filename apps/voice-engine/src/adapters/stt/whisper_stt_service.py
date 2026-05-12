"""Pipecat-compatible STT frame processor backed by a WhisperLive WebSocket server.

WhisperLive (ghcr.io/collabora/whisperlive-cpu) listens on port 9090 and uses
a custom WebSocket protocol:

  1. Client connects to ws://host:9090
  2. Client sends a JSON handshake:
       {"uid": "<uuid4>", "language": "en", "task": "transcribe",
        "model": "tiny.en", "use_vad": true, "send_last_n_segments": 10}
  3. Server replies with {"uid": "...", "message": "SERVER_READY"}
  4. Client streams raw PCM audio (16-bit, mono, 16 kHz) as binary frames
  5. Server streams JSON transcript messages:
       {"uid": "...", "segments": [
         {"text": "hello world", "start": 0.0, "end": 1.5, "completed": true},
         {"text": "how are",     "start": 1.5, "end": 2.1, "completed": false}
       ]}
     completed=true  → segment is final and will not change
     completed=false → segment is still being refined (interim)
  6. Client sends b"END_OF_AUDIO" before closing

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
import time
import uuid
from typing import Any

logger = logging.getLogger(__name__)

_WHISPER_SAMPLE_RATE = 16_000
_DROP_WARN_INTERVAL = 200
_RECONNECT_COOLDOWN_S = 2.0


def _resample_pcm(audio: bytes, from_rate: int, to_rate: int) -> bytes:
    """Resample 16-bit mono PCM from from_rate to to_rate using linear interpolation."""
    if from_rate == to_rate or not audio:
        return audio
    import numpy as np

    samples = np.frombuffer(audio, dtype=np.int16).astype(np.float32)
    new_length = max(1, int(round(len(samples) * to_rate / from_rate)))
    resampled = np.interp(
        np.linspace(0, len(samples) - 1, new_length),
        np.arange(len(samples)),
        samples,
    ).astype(np.int16)
    return resampled.tobytes()


class WhisperSTTService:
    """Pipecat FrameProcessor wrapping a WhisperLive WebSocket STT server.

    Instantiated by the STT factory and inserted into the Pipecat pipeline at
    the same position as DeepgramSTTService. All Pipecat-specific imports are
    deferred to ``_build_processor`` so the class can be constructed in unit
    tests without the ``[voice]`` extras installed.
    """

    def __init__(self, url: str) -> None:
        self._url = url
        self._processor: Any | None = None

    def build(self) -> Any:
        """Return a live Pipecat FrameProcessor. Call inside ``_build()``."""
        if self._processor is None:
            self._processor = _build_processor(self._url)
        return self._processor


def _build_processor(url: str) -> Any:
    """Construct and return the actual Pipecat FrameProcessor instance."""
    from pipecat.frames.frames import (
        AudioRawFrame,
        CancelFrame,
        EndFrame,
        Frame,
        StartFrame,
        TranscriptionFrame,
    )
    from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

    try:
        from pipecat.frames.frames import InterimTranscriptionFrame
        _has_interim = True
    except ImportError:
        _has_interim = False

    class _WhisperLiveFrameProcessor(FrameProcessor):
        """Stateful processor: one WhisperLive WebSocket connection per pipeline run."""

        def __init__(self) -> None:
            super().__init__()
            self._ws: Any | None = None
            self._recv_task: asyncio.Task[None] | None = None
            self._server_ready = asyncio.Event()
            self._uid = str(uuid.uuid4())
            # How many completed segments have already been emitted as finals.
            # WhisperLive sends cumulative segments, so we track the count to
            # avoid re-emitting segments that were already pushed downstream.
            self._completed_count = 0
            self._audio_frames_received: int = 0
            self._audio_frames_dropped: int = 0
            self._last_connect_attempt: float = 0.0

        # ── Pipecat lifecycle ────────────────────────────────────────

        async def cleanup(self) -> None:
            await self._disconnect()
            await super().cleanup()

        # ── connection management ────────────────────────────────────

        async def _connect(self) -> bool:
            self._last_connect_attempt = time.monotonic()
            self._server_ready.clear()
            self._completed_count = 0
            try:
                import websockets
                self._ws = await websockets.connect(url, ping_interval=20, ping_timeout=10)
                self._recv_task = asyncio.create_task(self._receive_loop())
                handshake = {
                    "uid": self._uid,
                    "language": "en",
                    "task": "transcribe",
                    "model": "tiny.en",
                    "use_vad": True,
                    "send_last_n_segments": 10,
                }
                await self._ws.send(json.dumps(handshake))
                logger.info("WhisperSTT: connected to %s — awaiting SERVER_READY", url)
                try:
                    await asyncio.wait_for(self._server_ready.wait(), timeout=15.0)
                    logger.info("WhisperSTT: server ready")
                except TimeoutError:
                    logger.warning("WhisperSTT: SERVER_READY not received within 15 s — proceeding anyway")
                return True
            except Exception as exc:
                logger.error("WhisperSTT: connection failed (%s) — audio will be dropped", exc)
                self._ws = None
                return False

        async def _disconnect(self) -> None:
            if self._ws is not None:
                try:
                    await self._ws.send(b"END_OF_AUDIO")
                except Exception:
                    pass
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
            logger.info(
                "WhisperSTT: disconnected (frames received=%d, dropped=%d)",
                self._audio_frames_received,
                self._audio_frames_dropped,
            )

        async def _receive_loop(self) -> None:
            try:
                async for raw in self._ws:  # type: ignore[union-attr]
                    if isinstance(raw, bytes):
                        continue  # WhisperLive sends text JSON only
                    try:
                        data: dict[str, Any] = json.loads(raw)
                    except json.JSONDecodeError:
                        logger.warning("WhisperSTT: non-JSON message: %r", raw)
                        continue

                    # Status / control messages (no segments key).
                    if "segments" not in data:
                        msg = data.get("message", "")
                        status = data.get("status", "")
                        if msg == "SERVER_READY":
                            self._server_ready.set()
                        elif status == "WAIT":
                            logger.info("WhisperSTT: server at capacity — queued (%s)", data.get("message", ""))
                        elif status == "ERROR":
                            logger.error("WhisperSTT: server error: %s", data.get("message", ""))
                        continue

                    segments: list[dict[str, Any]] = data.get("segments", [])
                    if not segments:
                        continue

                    completed = [s for s in segments if s.get("completed")]
                    incomplete = [s for s in segments if not s.get("completed")]

                    # Emit newly completed segments as final transcriptions.
                    for seg in completed[self._completed_count:]:
                        text = seg.get("text", "").strip()
                        if text:
                            logger.info("WhisperSTT: final segment: %s", text[:120])
                            await self.push_frame(
                                TranscriptionFrame(text=text, user_id="", timestamp="", language="en"),
                                FrameDirection.DOWNSTREAM,
                            )
                    self._completed_count = len(completed)

                    # Emit the latest incomplete segment as an interim transcription.
                    if incomplete and _has_interim:
                        text = incomplete[-1].get("text", "").strip()
                        if text:
                            await self.push_frame(
                                InterimTranscriptionFrame(text=text, user_id="", timestamp="", language="en"),
                                FrameDirection.DOWNSTREAM,
                            )

                logger.warning("WhisperSTT: server closed connection — will reconnect on next audio frame")
                self._ws = None
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.error("WhisperSTT: receive loop error: %s", exc)
                self._ws = None

        # ── FrameProcessor contract ──────────────────────────────────

        async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
            await super().process_frame(frame, direction)

            if isinstance(frame, StartFrame):
                await self._connect()
                await self.push_frame(frame, direction)

            elif isinstance(frame, (EndFrame, CancelFrame)):
                await self._disconnect()
                await self.push_frame(frame, direction)

            elif isinstance(frame, AudioRawFrame) and direction == FrameDirection.DOWNSTREAM:
                self._audio_frames_received += 1

                if self._audio_frames_received == 1:
                    sr = getattr(frame, "sample_rate", "unknown")
                    logger.info(
                        "WhisperSTT: first audio frame (sample_rate=%s, bytes=%d)",
                        sr, len(frame.audio),
                    )

                if self._ws is None:
                    elapsed = time.monotonic() - self._last_connect_attempt
                    if elapsed >= _RECONNECT_COOLDOWN_S:
                        logger.info("WhisperSTT: attempting reconnect...")
                        await self._connect()

                if self._ws is not None and self._server_ready.is_set():
                    try:
                        audio = _resample_pcm(
                            frame.audio,
                            getattr(frame, "sample_rate", _WHISPER_SAMPLE_RATE),
                            _WHISPER_SAMPLE_RATE,
                        )
                        await self._ws.send(audio)
                    except Exception as exc:
                        logger.warning("WhisperSTT: send failed: %s", exc)
                        self._ws = None
                else:
                    self._audio_frames_dropped += 1
                    if self._audio_frames_dropped % _DROP_WARN_INTERVAL == 1:
                        logger.warning(
                            "WhisperSTT: no connection — audio dropped "
                            "(dropped=%d so far). Check WHISPER_STT_URL and "
                            "that the whisper-stt container is running.",
                            self._audio_frames_dropped,
                        )
            else:
                await self.push_frame(frame, direction)

    return _WhisperLiveFrameProcessor()
