"""Audio chunking processor for batched STT with streaming LLM responses.

Pipeline flow:
  AudioRawFrame (streaming)
    ↓
  push_audio_frame() → returns ready AudioSegments
    ↓
  [Pipecat processor emits each segment downstream to STT]
    ↓
  STT emits TranscriptionFrame upstream → on_stt_complete()
    ↓
  [prepare_response_fn called with accumulated transcript]
    ↓
  [latest LLMResponse tracked]
    ↓
  UserStoppedSpeakingFrame → on_speech_ended()
    ↓
  [Pipecat processor pushes latest response text downstream to TTS]
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_CHUNK_DURATION_S = 5.0
_DEFAULT_SAMPLE_RATE = 16_000


@dataclass
class AudioSegment:
    """A buffered audio segment ready for STT."""

    audio: bytes
    duration_s: float
    segment_id: str


@dataclass
class SegmentTranscription:
    """Result from STT on a single segment."""

    segment_id: str
    text: str
    full_transcript: str = ""
    start_time: float = field(default_factory=time.time)


@dataclass
class LLMResponse:
    """Prepared LLM response for a segment transcription."""

    segment_id: str
    text: str
    full_context: str
    prepared_at: float = field(default_factory=time.time)


class AudioChunkingProcessor:
    """
    Buffers audio into fixed-duration chunks for batched STT while queueing
    LLM responses in parallel.

    Intended flow:
      1. Caller pushes audio frames via push_audio_frame() (synchronous).
         Returns ready AudioSegments when a chunk boundary is crossed.
      2. Pipecat processor sends each segment to FasterWhisperSTT downstream.
      3. STT emits TranscriptionFrame upstream; Pipecat processor calls
         on_stt_complete() with the result (async).
      4. on_stt_complete() accumulates the transcript and calls
         prepare_response_fn(transcript) to pre-compute an LLM reply.
      5. When UserStoppedSpeakingFrame arrives, on_speech_ended() is called
         and the Pipecat processor pushes the latest response to TTS.
    """

    def __init__(
        self,
        chunk_duration_s: float = _DEFAULT_CHUNK_DURATION_S,
        sample_rate: int = _DEFAULT_SAMPLE_RATE,
        prepare_response_fn: Callable[[str], Awaitable[str]] | None = None,
    ) -> None:
        self.chunk_duration_s = chunk_duration_s
        self.sample_rate = sample_rate
        self._prepare_response_fn = prepare_response_fn

        self._audio_buffer = bytearray()
        self._segment_counter = 0
        self._chunk_size_bytes = int(chunk_duration_s * sample_rate * 2)  # int16 = 2 bytes

        self._accumulated_transcript = ""
        self._latest_response: LLMResponse | None = None

        self._on_stt_complete_callbacks: list[Callable[[SegmentTranscription], Any]] = []
        self._on_llm_ready_callbacks: list[Callable[[LLMResponse], Any]] = []
        self._on_speech_ended_callbacks: list[Callable[[str], Any]] = []

    # ── Public synchronous API ──────────────────────────────────────────────

    def push_audio_frame(self, audio: bytes, sample_rate: int | None = None) -> list[AudioSegment]:
        """Buffer audio and return any complete segments ready for STT."""
        if sample_rate and sample_rate != self.sample_rate:
            logger.warning(
                "AudioChunking: sample rate mismatch (expected %d, got %d)",
                self.sample_rate,
                sample_rate,
            )
        self._audio_buffer.extend(audio)

        ready: list[AudioSegment] = []
        while len(self._audio_buffer) >= self._chunk_size_bytes:
            chunk = bytes(self._audio_buffer[: self._chunk_size_bytes])
            del self._audio_buffer[: self._chunk_size_bytes]
            self._segment_counter += 1
            segment_id = f"seg_{self._segment_counter}"
            ready.append(
                AudioSegment(
                    audio=chunk,
                    duration_s=self.chunk_duration_s,
                    segment_id=segment_id,
                )
            )
            logger.info("AudioChunking: segment %s ready (%.1fs)", segment_id, self.chunk_duration_s)
        return ready

    def flush_partial(self) -> list[AudioSegment]:
        """Return remaining buffered audio as a partial segment (call at end of speech)."""
        if not self._audio_buffer:
            return []
        self._segment_counter += 1
        segment_id = f"seg_{self._segment_counter}_final"
        duration = len(self._audio_buffer) / (self.sample_rate * 2)
        segment = AudioSegment(
            audio=bytes(self._audio_buffer),
            duration_s=duration,
            segment_id=segment_id,
        )
        self._audio_buffer.clear()
        logger.info("AudioChunking: flushed partial segment %s (%.2fs)", segment_id, duration)
        return [segment]

    def get_latest_response(self) -> LLMResponse | None:
        """Return the most recently prepared LLM response, or None."""
        return self._latest_response

    def get_full_transcript(self) -> str:
        """Return accumulated transcript of all completed segments."""
        return self._accumulated_transcript

    def register_stt_complete(self, callback: Callable[[SegmentTranscription], Any]) -> None:
        self._on_stt_complete_callbacks.append(callback)

    def register_llm_ready(self, callback: Callable[[LLMResponse], Any]) -> None:
        self._on_llm_ready_callbacks.append(callback)

    def register_speech_ended(self, callback: Callable[[str], Any]) -> None:
        self._on_speech_ended_callbacks.append(callback)

    # ── Public async API ────────────────────────────────────────────────────

    async def on_stt_complete(self, transcription: SegmentTranscription) -> None:
        """Called by the Pipecat processor when STT returns a segment result."""
        logger.info(
            "AudioChunking: STT complete for %s: '%s'",
            transcription.segment_id,
            transcription.text[:120],
        )

        if transcription.text.strip():
            if self._accumulated_transcript:
                self._accumulated_transcript += " "
            self._accumulated_transcript += transcription.text
            transcription.full_transcript = self._accumulated_transcript

        for callback in self._on_stt_complete_callbacks:
            try:
                result = callback(transcription)
                if hasattr(result, "__await__"):
                    await result
            except Exception as exc:
                logger.error("AudioChunking: STT callback error: %s", exc)

        await self._prepare_llm_response(transcription)

    async def on_speech_ended(self) -> None:
        """Called by the Pipecat processor on UserStoppedSpeakingFrame."""
        logger.info(
            "AudioChunking: speech ended. Transcript so far: '%s'",
            self._accumulated_transcript[:100],
        )
        for callback in self._on_speech_ended_callbacks:
            try:
                result = callback(self._accumulated_transcript)
                if hasattr(result, "__await__"):
                    await result
            except Exception as exc:
                logger.error("AudioChunking: speech-ended callback error: %s", exc)

    # ── Internal ────────────────────────────────────────────────────────────

    async def _prepare_llm_response(self, transcription: SegmentTranscription) -> None:
        if self._prepare_response_fn is None:
            logger.debug("AudioChunking: no prepare_response_fn — skipping LLM for %s", transcription.segment_id)
            return

        try:
            response_text = await self._prepare_response_fn(transcription.full_transcript)
            response = LLMResponse(
                segment_id=transcription.segment_id,
                text=response_text,
                full_context=transcription.full_transcript,
            )
            self._latest_response = response
            logger.info("AudioChunking: LLM response ready for %s", transcription.segment_id)

            for callback in self._on_llm_ready_callbacks:
                try:
                    result = callback(response)
                    if hasattr(result, "__await__"):
                        await result
                except Exception as exc:
                    logger.error("AudioChunking: LLM callback error: %s", exc)

        except Exception as exc:
            logger.error("AudioChunking: LLM preparation failed for %s: %s", transcription.segment_id, exc)
