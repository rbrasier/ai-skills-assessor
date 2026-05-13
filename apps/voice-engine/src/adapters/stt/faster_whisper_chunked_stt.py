"""Faster-Whisper STT processor for chunked audio.

Replaces WhisperLive with a local faster-whisper model. Designed to work
with AudioChunkingFrameProcessor:

  1. Receives 5-second AudioRawFrame chunks from the chunking processor.
  2. Transcribes each chunk locally in a thread pool (non-blocking).
  3. Emits TranscriptionFrame *upstream* so the chunking processor can
     accumulate transcriptions and queue LLM responses.

No external service required — faster-whisper runs in-process.

Install:
    pip install faster-whisper
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class FasterWhisperChunkedSTTService:
    """Factory wrapper: creates a Pipecat FrameProcessor backed by faster-whisper."""

    def __init__(self, model_name: str = "tiny.en") -> None:
        self._model_name = model_name
        self._processor: Any = None

    def build(self) -> Any:
        """Return a Pipecat FrameProcessor. Call inside a lazy-import context."""
        if self._processor is None:
            self._processor = _build_faster_whisper_processor(self._model_name)
        return self._processor


def _build_faster_whisper_processor(model_name: str) -> Any:
    from pipecat.frames.frames import (
        AudioRawFrame,
        CancelFrame,
        EndFrame,
        Frame,
        StartFrame,
        TranscriptionFrame,
    )
    from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

    class _FasterWhisperProcessor(FrameProcessor):
        """
        Transcribes 5-second audio chunks from AudioChunkingFrameProcessor.

        Pushes TranscriptionFrame *upstream* so the chunking processor
        intercepts it before it reaches the LLM/TTS stages.
        """

        def __init__(self) -> None:
            super().__init__()
            self._model: Any = None
            self._transcribe_queue: asyncio.Queue[tuple[str, bytes] | None] = asyncio.Queue()
            self._transcribe_task: asyncio.Task[None] | None = None
            self._chunk_counter = 0

        async def cleanup(self) -> None:
            await self._transcribe_queue.put(None)  # sentinel
            if self._transcribe_task and not self._transcribe_task.done():
                try:
                    await asyncio.wait_for(self._transcribe_task, timeout=5.0)
                except (TimeoutError, asyncio.CancelledError):
                    self._transcribe_task.cancel()
            await super().cleanup()

        async def _load_model(self) -> None:
            if self._model is not None:
                return
            try:
                from faster_whisper import WhisperModel

                logger.info("FasterWhisper: loading model '%s'...", model_name)
                loop = asyncio.get_running_loop()
                self._model = await loop.run_in_executor(
                    None,
                    lambda: WhisperModel(model_name, device="auto", compute_type="auto"),
                )
                logger.info("FasterWhisper: model ready")
            except ImportError:
                logger.error(
                    "FasterWhisper: faster-whisper not installed. "
                    "Run: pip install faster-whisper"
                )

        async def _transcribe_worker(self) -> None:
            while True:
                item = await self._transcribe_queue.get()
                if item is None:
                    break
                chunk_id, audio_bytes = item
                try:
                    logger.info("FasterWhisper: transcribing %s (%d bytes)", chunk_id, len(audio_bytes))
                    loop = asyncio.get_running_loop()
                    segments, info = await loop.run_in_executor(
                        None, self._transcribe_sync, audio_bytes
                    )
                    text = " ".join(seg.text for seg in segments).strip()
                    logger.info("FasterWhisper: %s → '%s'", chunk_id, text[:120])

                    if text:
                        await self.push_frame(
                            TranscriptionFrame(
                                text=text,
                                user_id="",
                                timestamp="",
                                language=info.language,
                            ),
                            FrameDirection.UPSTREAM,
                        )
                except Exception as exc:
                    logger.error("FasterWhisper: transcription failed for %s: %s", chunk_id, exc)

        def _transcribe_sync(self, audio_bytes: bytes) -> tuple[list[Any], Any]:
            """Run in thread pool — blocks until transcription completes."""
            import numpy as np

            audio_f32 = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            segments, info = self._model.transcribe(
                audio_f32,
                language="en",
                task="transcribe",
                beam_size=5,
            )
            return list(segments), info

        async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
            await super().process_frame(frame, direction)

            if isinstance(frame, StartFrame):
                await self._load_model()
                if self._transcribe_task is None:
                    self._transcribe_task = asyncio.create_task(self._transcribe_worker())
                logger.info("FasterWhisper: pipeline started")
                await self.push_frame(frame, direction)

            elif isinstance(frame, (EndFrame, CancelFrame)):
                await self._transcribe_queue.put(None)
                logger.info("FasterWhisper: %s received", frame.__class__.__name__)
                await self.push_frame(frame, direction)

            elif isinstance(frame, AudioRawFrame) and direction == FrameDirection.DOWNSTREAM:
                if self._model is None:
                    logger.warning("FasterWhisper: model not loaded — dropping chunk")
                    return
                self._chunk_counter += 1
                chunk_id = f"chunk_{self._chunk_counter}"
                await self._transcribe_queue.put((chunk_id, frame.audio))
                # Do not forward audio downstream — it has been queued for transcription.

            else:
                await self.push_frame(frame, direction)

    return _FasterWhisperProcessor()
