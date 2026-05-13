"""Faster-Whisper STT processors for local transcription.

Two modes are provided:

FasterWhisperChunkedSTTService
  Designed for use WITH AudioChunkingFrameProcessor. Receives pre-chunked
  5-second AudioRawFrames and transcribes each one as it arrives.

FasterWhisperSTTService
  Designed for use WITHOUT the chunker (AUDIO_CHUNKING_ENABLED=false).
  Buffers all audio during the user's utterance, then transcribes the full
  clip in one pass once UserStoppedSpeakingFrame arrives. More accurate for
  short utterances; latency is incurred after the user stops speaking.

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
                    logger.debug("FasterWhisper: transcribing %s (%d bytes)", chunk_id, len(audio_bytes))
                    loop = asyncio.get_running_loop()
                    segments, info = await loop.run_in_executor(
                        None, self._transcribe_sync, audio_bytes
                    )
                    text = " ".join(seg.text for seg in segments).strip()
                    if text:
                        logger.info("FasterWhisper: %s → '%s'", chunk_id, text[:120])
                    else:
                        logger.debug("FasterWhisper: %s → (empty)", chunk_id)

                    if text:
                        await self.push_frame(
                            TranscriptionFrame(
                                text=text,
                                user_id="",
                                timestamp="",
                                language=info.language,
                            ),
                            FrameDirection.DOWNSTREAM,
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


# ─── Whole-clip (non-chunked) mode ───────────────────────────────────────────


class FasterWhisperSTTService:
    """Factory wrapper: buffers the full user utterance then transcribes once.

    Use when AUDIO_CHUNKING_ENABLED=false.  The entire audio clip is processed
    after UserStoppedSpeakingFrame is received, so there are no interim
    transcriptions — the single final TranscriptionFrame arrives just before
    UserStoppedSpeakingFrame is forwarded downstream.
    """

    def __init__(self, model_name: str = "tiny.en") -> None:
        self._model_name = model_name
        self._processor: Any = None

    def build(self) -> Any:
        """Return a Pipecat FrameProcessor. Call inside a lazy-import context."""
        if self._processor is None:
            self._processor = _build_faster_whisper_buffered_processor(self._model_name)
        return self._processor


def _build_faster_whisper_buffered_processor(model_name: str) -> Any:
    from pipecat.frames.frames import (
        AudioRawFrame,
        CancelFrame,
        EndFrame,
        Frame,
        StartFrame,
        TranscriptionFrame,
        UserStartedSpeakingFrame,
        UserStoppedSpeakingFrame,
    )
    from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

    class _FasterWhisperBufferedProcessor(FrameProcessor):
        """
        Accumulates audio during user speech; transcribes the full clip on stop.

        Pipeline position: replaces the chunker+STT pair when chunking is off.

            transport.input() → [this processor] → conversation/LLM → ...

        On UserStoppedSpeakingFrame the buffered PCM is transcribed
        synchronously (in a thread-pool executor) and the resulting
        TranscriptionFrame is pushed downstream before the stop frame,
        preserving the ordering that downstream processors expect.
        """

        def __init__(self) -> None:
            super().__init__()
            self._model: Any = None
            self._audio_buffer: list[bytes] = []

        async def cleanup(self) -> None:
            self._audio_buffer.clear()
            await super().cleanup()

        async def _load_model(self) -> None:
            if self._model is not None:
                return
            try:
                from faster_whisper import WhisperModel

                logger.info("FasterWhisper (buffered): loading model '%s'...", model_name)
                loop = asyncio.get_running_loop()
                self._model = await loop.run_in_executor(
                    None,
                    lambda: WhisperModel(model_name, device="auto", compute_type="auto"),
                )
                logger.info("FasterWhisper (buffered): model ready")
            except ImportError:
                logger.error(
                    "FasterWhisper: faster-whisper not installed. "
                    "Run: pip install faster-whisper"
                )

        def _transcribe_sync(self, audio_bytes: bytes) -> tuple[list[Any], Any]:
            import numpy as np

            audio_f32 = (
                np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            )
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
                logger.info("FasterWhisper (buffered): pipeline started")
                await self.push_frame(frame, direction)

            elif isinstance(frame, (EndFrame, CancelFrame)):
                self._audio_buffer.clear()
                logger.info(
                    "FasterWhisper (buffered): %s received", frame.__class__.__name__
                )
                await self.push_frame(frame, direction)

            elif isinstance(frame, UserStartedSpeakingFrame):
                self._audio_buffer.clear()
                await self.push_frame(frame, direction)

            elif isinstance(frame, AudioRawFrame) and direction == FrameDirection.DOWNSTREAM:
                if self._model is not None:
                    self._audio_buffer.append(frame.audio)
                # Audio is consumed here — not forwarded downstream.

            elif isinstance(frame, UserStoppedSpeakingFrame):
                if self._audio_buffer and self._model is not None:
                    audio = b"".join(self._audio_buffer)
                    self._audio_buffer.clear()
                    try:
                        loop = asyncio.get_running_loop()
                        segments, info = await loop.run_in_executor(
                            None, self._transcribe_sync, audio
                        )
                        text = " ".join(seg.text for seg in segments).strip()
                        if text:
                            logger.info(
                                "FasterWhisper (buffered): transcribed %d bytes → '%s'",
                                len(audio),
                                text[:120],
                            )
                            await self.push_frame(
                                TranscriptionFrame(
                                    text=text,
                                    user_id="",
                                    timestamp="",
                                    language=info.language,
                                ),
                                FrameDirection.DOWNSTREAM,
                            )
                        else:
                            logger.debug("FasterWhisper (buffered): empty transcription")
                    except Exception as exc:
                        logger.error(
                            "FasterWhisper (buffered): transcription failed: %s", exc
                        )
                        self._audio_buffer.clear()
                await self.push_frame(frame, direction)

            else:
                await self.push_frame(frame, direction)

    return _FasterWhisperBufferedProcessor()
