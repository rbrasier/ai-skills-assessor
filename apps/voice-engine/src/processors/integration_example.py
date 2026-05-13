"""Integration example: Audio chunking + Faster-Whisper + Anthropic LLM.

Shows how to wire the chunking processor into a Pipecat pipeline.

Pipeline topology:
  Transport.input()
    ↓ AudioRawFrame
  AudioChunkingFrameProcessor   ← buffers 5-sec chunks; intercepts STT results;
    ↓ AudioRawFrame (chunk)       tracks latest LLM response
  FasterWhisperChunkedSTT       ← local on-device transcription
    ↑ TranscriptionFrame (upstream)
  [chunker intercepts, calls prepare_response_fn, stores LLMResponse]
    ↓ TextFrame (on UserStoppedSpeakingFrame)
  TTS processor                 ← synthesises latest response
    ↓ AudioFrame
  Transport.output()
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def build_chunked_pipeline(
    tts_service: Any,
    transport: Any,
    anthropic_api_key: str,
    anthropic_model: str = "claude-haiku-4-5",
    chunk_duration_s: float = 5.0,
) -> Any:
    """
    Build a Pipecat pipeline with chunked STT and pre-computed LLM responses.

    Args:
        tts_service: Configured Pipecat TTS processor (ElevenLabs, Kokoro, etc.).
        transport: Pipecat transport (DailyTransport or LiveKitTransport).
        anthropic_api_key: Anthropic API key for response preparation.
        anthropic_model: Claude model for in-call responses (default: haiku).
        chunk_duration_s: Audio chunk size in seconds (default 5).

    Returns:
        Configured Pipecat Pipeline ready to pass to PipelineTask.

    Example (in bot_runner.py)::

        pipeline = await build_chunked_pipeline(
            tts_service=tts_service,
            transport=self._transport,
            anthropic_api_key=settings.anthropic_api_key,
        )
        self._task = PipelineTask(pipeline, PipelineParams(allow_interruptions=True))
        await self._task.run()
    """
    import anthropic
    from pipecat.pipeline.pipeline import Pipeline

    from src.adapters.stt.faster_whisper_chunked_stt import FasterWhisperChunkedSTTService
    from src.processors.pipecat_audio_chunker import build_audio_chunking_frame_processor

    client = anthropic.AsyncAnthropic(api_key=anthropic_api_key)

    async def prepare_response(transcript: str) -> str:
        """Call Claude to pre-compute a response for the current transcript."""
        message = await client.messages.create(
            model=anthropic_model,
            max_tokens=256,
            messages=[{"role": "user", "content": transcript}],
        )
        return message.content[0].text if message.content else ""

    chunker = build_audio_chunking_frame_processor(
        chunk_duration_s=chunk_duration_s,
        prepare_response_fn=prepare_response,
    )

    stt = FasterWhisperChunkedSTTService(model_name="tiny.en").build()

    pipeline = Pipeline([
        transport.input(),
        chunker,
        stt,
        tts_service,
        transport.output(),
    ])

    logger.info("Chunked pipeline built (chunk=%.1fs, model=%s)", chunk_duration_s, anthropic_model)
    return pipeline
