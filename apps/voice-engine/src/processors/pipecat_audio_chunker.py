"""Pipecat frame processor for audio chunking with batched STT and pre-computed LLM.

Pipeline topology:
  Transport.input()
    ↓ AudioRawFrame (downstream)
  _AudioChunkingFrameProcessor  ← this file
    ↓ AudioRawFrame (buffered 5-sec chunks, downstream)
  FasterWhisperChunkedSTT
    ↑ TranscriptionFrame (upstream, back to chunker)
  [chunker calls prepare_response_fn, stores latest response]
    ↓ TextFrame (downstream, when UserStoppedSpeakingFrame received)
  TTS processor
    ↓ AudioFrame (downstream)
  Transport.output()
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)


def build_audio_chunking_frame_processor(
    chunk_duration_s: float = 5.0,
    prepare_response_fn: Callable[[str], Awaitable[str]] | None = None,
) -> Any:
    """
    Create a Pipecat FrameProcessor for audio chunking with pre-computed LLM responses.

    Args:
        chunk_duration_s: Duration of each audio chunk sent to STT (default 5s).
        prepare_response_fn: Async callable that takes the accumulated transcript
            and returns a response string. Called for each completed STT segment.
            If None, transcript is accumulated but no LLM responses are prepared.

    Returns:
        A Pipecat FrameProcessor ready to insert before FasterWhisperChunkedSTT.
    """
    from pipecat.frames.frames import (
        AudioRawFrame,
        CancelFrame,
        EndFrame,
        Frame,
        StartFrame,
        TextFrame,
        TranscriptionFrame,
    )
    from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

    try:
        from pipecat.frames.frames import UserStoppedSpeakingFrame

        _has_vad = True
    except ImportError:
        _has_vad = False
        logger.warning("AudioChunking: UserStoppedSpeakingFrame not available — speech-end detection disabled")

    try:
        from pipecat.frames.frames import InterimTranscriptionFrame

        _has_interim = True
    except ImportError:
        _has_interim = False

    from src.processors.audio_chunking_processor import AudioChunkingProcessor, SegmentTranscription

    class _AudioChunkingFrameProcessor(FrameProcessor):
        """
        Sits before FasterWhisperChunkedSTT in the pipeline.

        - Buffers AudioRawFrames into 5-second chunks, emits each downstream.
        - Intercepts TranscriptionFrames flowing upstream from STT.
        - Calls prepare_response_fn per transcription; tracks latest response.
        - On UserStoppedSpeakingFrame: flushes remaining audio, fires on_speech_ended(),
          then pushes latest response text downstream to TTS.
        """

        def __init__(self) -> None:
            super().__init__()
            self._chunker = AudioChunkingProcessor(
                chunk_duration_s=chunk_duration_s,
                prepare_response_fn=prepare_response_fn,
            )
            self._sample_rate = 16_000
            self._num_channels = 1

        async def cleanup(self) -> None:
            partial = self._chunker.flush_partial()
            if partial:
                logger.info("AudioChunking: discarding %d partial segment(s) on cleanup", len(partial))
            await super().cleanup()

        async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
            await super().process_frame(frame, direction)

            if isinstance(frame, StartFrame):
                logger.info("AudioChunking: pipeline started (chunk=%.1fs)", chunk_duration_s)
                await self.push_frame(frame, direction)

            elif isinstance(frame, (EndFrame, CancelFrame)):
                logger.info(
                    "AudioChunking: %s — transcript: '%s'",
                    frame.__class__.__name__,
                    self._chunker.get_full_transcript()[:120],
                )
                await self.push_frame(frame, direction)

            elif isinstance(frame, AudioRawFrame) and direction == FrameDirection.DOWNSTREAM:
                self._sample_rate = getattr(frame, "sample_rate", 16_000)
                self._num_channels = getattr(frame, "num_channels", 1)
                ready_segments = self._chunker.push_audio_frame(frame.audio, self._sample_rate)
                for segment in ready_segments:
                    chunk_frame = AudioRawFrame(
                        audio=segment.audio,
                        sample_rate=self._sample_rate,
                        num_channels=self._num_channels,
                    )
                    await self.push_frame(chunk_frame, FrameDirection.DOWNSTREAM)

            elif isinstance(frame, TranscriptionFrame) and direction == FrameDirection.UPSTREAM:
                # FasterWhisperSTT pushes TranscriptionFrames upstream to this processor.
                logger.info("AudioChunking: transcription received: '%s'", frame.text[:120])
                transcription = SegmentTranscription(
                    segment_id=getattr(frame, "segment_id", f"seg_{id(frame)}"),
                    text=frame.text,
                )
                await self._chunker.on_stt_complete(transcription)
                # Frame consumed here; the response is tracked internally.

            elif _has_interim and isinstance(frame, InterimTranscriptionFrame):
                # Pass interim transcriptions through without processing.
                await self.push_frame(frame, direction)

            elif _has_vad and isinstance(frame, UserStoppedSpeakingFrame):
                await self._handle_speech_ended(frame, direction)

            else:
                await self.push_frame(frame, direction)

        async def _handle_speech_ended(self, frame: Frame, direction: FrameDirection) -> None:
            """Flush remaining audio, fire speech-ended, push latest response to TTS."""
            # Flush any partial audio buffered since the last full chunk
            partial_segments = self._chunker.flush_partial()
            for segment in partial_segments:
                chunk_frame = AudioRawFrame(
                    audio=segment.audio,
                    sample_rate=self._sample_rate,
                    num_channels=self._num_channels,
                )
                await self.push_frame(chunk_frame, FrameDirection.DOWNSTREAM)

            # Notify chunker that speech has ended
            await self._chunker.on_speech_ended()

            # Push latest pre-computed response to TTS if available
            response = self._chunker.get_latest_response()
            if response and response.text:
                logger.info(
                    "AudioChunking: pushing latest response to TTS: '%s'",
                    response.text[:100],
                )
                await self.push_frame(TextFrame(text=response.text), FrameDirection.DOWNSTREAM)
            else:
                logger.info("AudioChunking: no pre-computed response available — passing speech-end frame")

            # Let the rest of the pipeline know speech stopped
            await self.push_frame(frame, direction)

    return _AudioChunkingFrameProcessor()
