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


def _ensure_int16_pcm(audio: bytes) -> bytes:
    """Convert audio to int16 PCM if it's in normalized float format [-1, 1].

    Pipecat may emit audio as normalized float samples; WhisperLive expects raw int16 PCM.
    """
    import numpy as np

    if not audio:
        return audio

    try:
        # Try to interpret as int16 first
        samples = np.frombuffer(audio, dtype=np.int16)
        if len(samples) > 0:
            # Check if values look like proper int16 (typical range) or misinterpreted float
            max_abs = np.abs(samples).max()
            min_abs = np.abs(samples).min()
            logger.debug("_ensure_int16_pcm: int16 interpretation max_abs=%d min_abs=%d, bytes=%d, samples=%d",
                        max_abs, min_abs, len(audio), len(samples))
            if max_abs > 100:  # Looks like proper int16 (typical range would be thousands)
                logger.debug("_ensure_int16_pcm: returning as-is - proper int16")
                return audio
            # If all samples are 0 (silence), might be int16
            if max_abs == 0:
                logger.debug("_ensure_int16_pcm: audio is silence (all zeros)")
                return audio
            # Otherwise, it might be float32 misinterpreted, continue to next check
    except Exception as e:
        logger.debug("_ensure_int16_pcm: int16 interpretation failed: %s", e)

    # Try to interpret as float32 (Pipecat sends normalized float [-1, 1])
    try:
        float_samples = np.frombuffer(audio, dtype=np.float32)
        if len(float_samples) > 0:
            max_float = np.abs(float_samples).max()
            min_float = np.abs(float_samples).min()
            nan_count = np.isnan(float_samples).sum()
            inf_count = np.isinf(float_samples).sum()

            logger.info("_ensure_int16_pcm: float32 interpretation max=%.6f min=%.6f, samples=%d, nan=%d, inf=%d",
                       max_float, min_float, len(float_samples), nan_count, inf_count)

            # Check for NaN or Inf
            if nan_count > 0 or inf_count > 0:
                logger.error("_ensure_int16_pcm: audio contains NaN (%d) or Inf (%d) values - audio is corrupted or invalid", nan_count, inf_count)
                # Try to salvage by replacing NaN/Inf with 0
                float_samples = np.nan_to_num(float_samples, nan=0.0, posinf=1.0, neginf=-1.0)
                logger.info("_ensure_int16_pcm: replaced NaN/Inf with valid values")

            if max_float <= 1.1 or np.isnan(max_float):  # Normalized float in [-1, 1] or was NaN
                logger.info("_ensure_int16_pcm: converting float32 [-1,1] to int16 PCM (max=%.6f)", max_float)
                # Amplify quiet audio (if max is < 0.1, boost to use more of the dynamic range)
                if 0 < max_float < 0.1:
                    gain = min(1.0 / max_float, 10.0)  # Cap gain at 10x to avoid clipping
                    logger.info("_ensure_int16_pcm: applying gain %.2fx to quiet audio", gain)
                    float_samples = float_samples * gain
                int_samples = np.clip(float_samples * 32767, -32768, 32767).astype(np.int16)
                result = int_samples.tobytes()
                logger.info("_ensure_int16_pcm: converted to int16, output bytes=%d", len(result))
                return result
    except Exception as e:
        logger.debug("_ensure_int16_pcm: float32 interpretation failed: %s", e)

    # If all else fails, return as-is
    logger.warning("_ensure_int16_pcm: returning audio as-is (bytes=%d) - could not convert", len(audio))
    return audio


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
                    "use_vad": False,
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

            # Wait for receive task to finish naturally (so WhisperLive can send final results)
            # Give it up to 10 seconds to process and respond
            if self._recv_task and not self._recv_task.done():
                try:
                    await asyncio.wait_for(self._recv_task, timeout=10.0)
                except (TimeoutError, asyncio.CancelledError):
                    # If still running after timeout, cancel it
                    if not self._recv_task.done():
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
                        logger.debug("WhisperSTT: ignoring binary message (bytes=%d)", len(raw))
                        continue  # WhisperLive sends text JSON only
                    try:
                        data: dict[str, Any] = json.loads(raw)
                    except json.JSONDecodeError:
                        logger.warning("WhisperSTT: non-JSON message: %r", raw)
                        continue

                    logger.info("WhisperSTT: received message: %s", json.dumps(data)[:300])

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
                        logger.debug("WhisperSTT: status message handled (msg=%r, status=%r)", msg, status)
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
                    # Validate audio: should be int16 PCM (range -32768..32767 per sample)
                    import numpy as np
                    try:
                        samples = np.frombuffer(frame.audio, dtype=np.int16)
                        if len(samples) > 0:
                            min_val, max_val = samples.min(), samples.max()
                            logger.info(
                                "WhisperSTT: first audio frame (sample_rate=%s, bytes=%d, samples=%d, range=[%d, %d])",
                                sr, len(frame.audio), len(samples), int(min_val), int(max_val),
                            )
                        else:
                            logger.warning("WhisperSTT: first audio frame is empty")
                    except Exception as e:
                        logger.error("WhisperSTT: error validating audio: %s", e)

                if self._ws is None:
                    elapsed = time.monotonic() - self._last_connect_attempt
                    if elapsed >= _RECONNECT_COOLDOWN_S:
                        logger.info("WhisperSTT: attempting reconnect...")
                        await self._connect()

                if self._ws is not None and self._server_ready.is_set():
                    try:
                        audio = _ensure_int16_pcm(frame.audio)

                        # Skip frames that are empty
                        if audio and len(audio) > 0:
                            audio = _resample_pcm(
                                audio,
                                getattr(frame, "sample_rate", _WHISPER_SAMPLE_RATE),
                                _WHISPER_SAMPLE_RATE,
                            )
                            # Ensure audio is properly aligned for int16 PCM
                            if len(audio) % 2 != 0:
                                logger.warning("WhisperSTT: audio misaligned (%d bytes), trimming last byte", len(audio))
                                audio = audio[:-1]
                            if audio:
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
