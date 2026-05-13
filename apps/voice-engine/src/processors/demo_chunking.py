"""Demo: Audio chunking processor in action.

Run this to see how the chunker buffers audio, emits segments, and tracks
LLM responses. Useful for verifying the flow without a full Pipecat pipeline.

Usage:
    python -m src.processors.demo_chunking
"""

import asyncio
import logging

from src.processors.audio_chunking_processor import (
    AudioChunkingProcessor,
    LLMResponse,
    SegmentTranscription,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


async def mock_llm(transcript: str) -> str:
    """Simulate an LLM call (replace with real provider in production)."""
    await asyncio.sleep(0.1)  # simulate network latency
    return f"Response to: '{transcript[-60:]}'"


async def demo() -> None:
    """Simulate a user speaking 3 sentences over 15 seconds."""
    chunker = AudioChunkingProcessor(
        chunk_duration_s=5.0,
        sample_rate=16_000,
        prepare_response_fn=mock_llm,
    )

    async def on_stt(seg: SegmentTranscription) -> None:
        logger.info("[CALLBACK] STT done: %s = '%s'", seg.segment_id, seg.text)

    async def on_llm(resp: LLMResponse) -> None:
        logger.info("[CALLBACK] LLM ready: %s → '%s'", resp.segment_id, resp.text[:80])

    async def on_speech_ended(transcript: str) -> None:
        logger.info("[CALLBACK] Speech ended. Transcript: '%s'", transcript)

    chunker.register_stt_complete(on_stt)
    chunker.register_llm_ready(on_llm)
    chunker.register_speech_ended(on_speech_ended)

    chunk_size = 5 * 16_000 * 2  # 5s × 16 kHz × int16
    dummy_audio = b"\x00\x01" * (chunk_size // 2)

    logger.info("=" * 70)
    logger.info("Demo: 3 × 5-second audio segments")
    logger.info("=" * 70)

    # Push three 5-second chunks — each triggers one ready segment
    for i, text in enumerate(
        [
            "Hello, my name is Alice and I specialize in Python",
            "I have 8 years of experience",
            "including cloud architecture and DevOps",
        ],
        start=1,
    ):
        logger.info("\n[Audio push] Segment %d", i)
        segments = chunker.push_audio_frame(dummy_audio)
        assert len(segments) == 1, f"Expected 1 segment, got {len(segments)}"

        logger.info("[STT returns ] Segment %d: '%s'", i, text)
        await chunker.on_stt_complete(
            SegmentTranscription(segment_id=segments[0].segment_id, text=text)
        )
        await asyncio.sleep(0.1)

    # Simulate UserStoppedSpeakingFrame (flush + speech ended)
    logger.info("\n[VAD         ] Speech ended")
    await chunker.on_speech_ended()

    logger.info("\n" + "=" * 70)
    logger.info("RESULTS")
    logger.info("=" * 70)
    response = chunker.get_latest_response()
    logger.info("Latest response (play to user): %s", response)
    logger.info("Full transcript (for record)  : '%s'", chunker.get_full_transcript())
    logger.info("=" * 70)


if __name__ == "__main__":
    asyncio.run(demo())
