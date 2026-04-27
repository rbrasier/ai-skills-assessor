"""Pipecat-compatible TTS frame processor backed by Kokoro-FastAPI.

Kokoro-FastAPI exposes an OpenAI-compatible endpoint:

    POST /v1/audio/speech
    Content-Type: application/json
    {"model": "kokoro", "input": "<text>", "voice": "af_bella",
     "response_format": "pcm", "speed": 1.0}

The response body is a raw PCM stream (16-bit LE, mono, default 24 kHz).
This processor receives TTSSpeakFrame objects, streams audio from Kokoro,
and emits AudioRawFrame chunks downstream — identical to ElevenLabsTTSService.

Sentence-boundary buffering: TTSSpeakFrame text is synthesised in one call per
frame; Pipecat's conversation layer already handles sentence splitting before
emitting TTSSpeakFrame events so no additional buffering is required here.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Chunk size for streaming PCM bytes from Kokoro (2 048 samples × 2 bytes = 4 KB).
_CHUNK_BYTES = 4096


class KokoroTTSService:
    """Lazy wrapper — build() must be called inside a Pipecat-available context."""

    def __init__(self, url: str, voice: str = "af_bella", sample_rate: int = 24000) -> None:
        self._url = url.rstrip("/")
        self._voice = voice
        self._sample_rate = sample_rate
        self._processor: Any | None = None

    def build(self) -> Any:
        if self._processor is None:
            self._processor = _build_processor(self._url, self._voice, self._sample_rate)
        return self._processor


def _build_processor(url: str, voice: str, sample_rate: int) -> Any:
    """Construct and return the live Pipecat FrameProcessor."""
    from pipecat.frames.frames import AudioRawFrame, EndFrame, Frame, StartFrame
    from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

    # TTSSpeakFrame is the canonical input; fall back to TextFrame in very old
    # Pipecat versions.
    try:
        from pipecat.frames.frames import TTSSpeakFrame as _SpeakFrame
    except ImportError:
        from pipecat.frames.frames import TextFrame as _SpeakFrame

    speech_endpoint = f"{url}/v1/audio/speech"

    class _KokoroFrameProcessor(FrameProcessor):
        async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
            await super().process_frame(frame, direction)

            if isinstance(frame, _SpeakFrame):
                text: str = getattr(frame, "text", "") or ""
                if text.strip():
                    await self._synthesise(text)
                # Do NOT push the TTSSpeakFrame further — it is consumed here.

            elif isinstance(frame, (StartFrame, EndFrame)):
                await self.push_frame(frame, direction)

            else:
                await self.push_frame(frame, direction)

        async def _synthesise(self, text: str) -> None:
            import httpx

            payload = {
                "model": "kokoro",
                "input": text,
                "voice": voice,
                "response_format": "pcm",
                "speed": 1.0,
            }
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    async with client.stream("POST", speech_endpoint, json=payload) as resp:
                        if resp.status_code != 200:
                            body = await resp.aread()
                            logger.error(
                                "KokoroTTS: HTTP %d — %s", resp.status_code, body[:200]
                            )
                            return
                        async for chunk in resp.aiter_bytes(_CHUNK_BYTES):
                            if chunk:
                                await self.push_frame(
                                    AudioRawFrame(
                                        audio=chunk,
                                        num_channels=1,
                                        sample_rate=sample_rate,
                                    ),
                                    FrameDirection.DOWNSTREAM,
                                )
            except Exception as exc:
                logger.error("KokoroTTS: synthesis failed for text=%r — %s", text[:40], exc)

    return _KokoroFrameProcessor()
