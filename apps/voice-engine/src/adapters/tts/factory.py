"""TTS service factory — selects ElevenLabs or Kokoro based on ``Settings``.

Must be called inside a lazy-import context (i.e. after the ``[voice]``
extras are on sys.path) because it imports pipecat internals.

Graceful fallback: if ``tts_provider == "kokoro"`` but ``KOKORO_TTS_URL``
is empty or the service is unreachable, a warning is logged and ElevenLabs
is used instead.  Reachability is tested by a lightweight HTTP health-check
before handing the processor to the pipeline.
"""

from __future__ import annotations

import logging
from typing import Any

from src.config import Settings

logger = logging.getLogger(__name__)


def _kokoro_reachable_sync(url: str) -> bool:
    """Synchronous health probe — called from inside the sync ``_build()`` method."""
    import httpx

    health_url = url.rstrip("/") + "/health"
    try:
        r = httpx.get(health_url, timeout=3.0)
        return r.status_code < 500
    except Exception as exc:
        logger.warning("KokoroTTS reachability check failed (%s): %s", health_url, exc)
        return False


def create_tts_service(settings: Settings) -> Any:
    """Return a Pipecat-compatible TTS frame processor.

    Pipecat extras must be importable when this function is called.
    """
    provider = settings.tts_provider

    if provider == "kokoro":
        url = settings.kokoro_tts_url.strip()
        if not url:
            logger.warning(
                "TTS_PROVIDER=kokoro but KOKORO_TTS_URL is not set — "
                "falling back to ElevenLabs"
            )
            return _create_elevenlabs(settings)

        if not _kokoro_reachable_sync(url):
            logger.error(
                "TTS_PROVIDER=kokoro but KOKORO_TTS_URL=%s is unreachable — "
                "falling back to ElevenLabs",
                url,
            )
            return _create_elevenlabs(settings)

        logger.info(
            "TTS provider: kokoro (url=%s, voice=%s, sample_rate=%d)",
            url,
            settings.kokoro_voice,
            settings.kokoro_sample_rate,
        )
        from src.adapters.tts.kokoro_tts_service import KokoroTTSService

        return KokoroTTSService(
            url=url,
            voice=settings.kokoro_voice,
            sample_rate=settings.kokoro_sample_rate,
        ).build()

    # Default: ElevenLabs
    return _create_elevenlabs(settings)


def _create_elevenlabs(settings: Settings) -> Any:
    logger.info("TTS provider: elevenlabs (voice_id=%s)", settings.elevenlabs_voice_id)
    from pipecat.services.elevenlabs.tts import ElevenLabsTTSService

    return ElevenLabsTTSService(
        api_key=settings.elevenlabs_api_key,
        voice_id=settings.elevenlabs_voice_id,
        output_format="pcm_24000",
    )
