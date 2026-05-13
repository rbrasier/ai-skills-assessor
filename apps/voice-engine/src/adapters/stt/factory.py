"""STT service factory — selects Deepgram or Whisper based on ``Settings``.

Must be called inside a lazy-import context (i.e. after the ``[voice]``
extras are on sys.path) because it imports pipecat internals.

Graceful fallback: if ``stt_provider == "whisper"`` but ``WHISPER_STT_URL``
is empty or the service is unreachable, a warning is logged and Deepgram is
used instead. Reachability is tested by a TCP connect to the WhisperLive port
(WhisperLive has no HTTP health endpoint — it is a WebSocket-only server).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import urlparse

from src.config import Settings

logger = logging.getLogger(__name__)


async def _whisper_reachable(url: str) -> bool:
    """Return True if the WhisperLive WebSocket port accepts a TCP connection within 3 s."""
    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 9090
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=3.0
        )
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return True
    except Exception as exc:
        logger.warning("WhisperLive reachability check failed (%s:%s): %s", host, port, exc)
        return False


def create_stt_service(settings: Settings) -> Any:
    """Return a Pipecat-compatible STT frame processor.

    Pipecat extras must be importable when this function is called.
    """
    provider = settings.stt_provider

    if provider == "local":
        model = settings.local_stt_model
        if settings.audio_chunking_enabled:
            logger.info("STT provider: local faster-whisper chunked (model=%s)", model)
            from src.adapters.stt.faster_whisper_chunked_stt import FasterWhisperChunkedSTTService
            return FasterWhisperChunkedSTTService(model_name=model).build()
        else:
            logger.info("STT provider: local faster-whisper buffered/full-clip (model=%s)", model)
            from src.adapters.stt.faster_whisper_chunked_stt import FasterWhisperSTTService
            return FasterWhisperSTTService(model_name=model).build()

    if provider == "whisper":
        url = settings.whisper_stt_url.strip()
        if not url:
            logger.warning(
                "STT_PROVIDER=whisper but WHISPER_STT_URL is not set — "
                "falling back to Deepgram"
            )
            return _create_deepgram(settings)

        # Synchronous reachability probe (we're inside a sync _build() call).
        try:
            reachable = asyncio.get_event_loop().run_until_complete(_whisper_reachable(url))
        except RuntimeError:
            # Already inside a running event loop (rare in tests).
            reachable = True  # optimistically proceed; connection errors surface later

        if not reachable:
            logger.error(
                "STT_PROVIDER=whisper but WHISPER_STT_URL=%s is unreachable (TCP connect failed) — "
                "falling back to Deepgram. Is the whisper-stt container running on port 9090?",
                url,
            )
            return _create_deepgram(settings)

        logger.info("STT provider: whisper (url=%s)", url)
        from src.adapters.stt.whisper_stt_service import WhisperSTTService
        return WhisperSTTService(url=url).build()

    # Default: Deepgram
    return _create_deepgram(settings)


def _create_deepgram(settings: Settings) -> Any:
    logger.info("STT provider: deepgram (model=%s)", settings.deepgram_model)
    from pipecat.services.deepgram.stt import DeepgramSTTService

    return DeepgramSTTService(
        api_key=settings.deepgram_api_key,
        model=settings.deepgram_model,
        # Wait 1 s of silence before declaring an utterance final.  The
        # default (10 ms) is far too aggressive for conversational speech —
        # a natural breath pause triggers a premature end-of-utterance.
        endpointing=1000,
        # Stream partial transcripts so the bot can reset its debounce
        # timer while the candidate is still speaking.
        interim_results=True,
    )
