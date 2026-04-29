"""STT service factory — selects Deepgram or Whisper based on ``Settings``.

Must be called inside a lazy-import context (i.e. after the ``[voice]``
extras are on sys.path) because it imports pipecat internals.

Graceful fallback: if ``stt_provider == "whisper"`` but ``WHISPER_STT_URL``
is empty or the service is unreachable, a warning is logged and Deepgram is
used instead.  Reachability is tested by a lightweight HTTP health-check
before handing the processor to the pipeline.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from src.config import Settings

logger = logging.getLogger(__name__)


async def _whisper_reachable(url: str) -> bool:
    """Return True if the Whisper health endpoint responds within 3 s."""
    import httpx

    # Convert ws(s):// → http(s):// for the health probe.
    http_url = url.replace("wss://", "https://").replace("ws://", "http://")
    # Strip any path suffix so we hit the root health endpoint.
    base = http_url.split("/ws/")[0].split("/transcribe")[0]
    health_url = base.rstrip("/") + "/health"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(health_url)
            return r.status_code < 500
    except Exception as exc:
        logger.warning("WhisperSTT reachability check failed (%s): %s", health_url, exc)
        return False


def create_stt_service(settings: Settings) -> Any:
    """Return a Pipecat-compatible STT frame processor.

    Pipecat extras must be importable when this function is called.
    """
    provider = settings.stt_provider

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
                "STT_PROVIDER=whisper but WHISPER_STT_URL=%s is unreachable — "
                "falling back to Deepgram",
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
