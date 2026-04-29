"""FastAPI application entry point for the voice engine.

Phase 3 Revision 1 wiring:

  Settings
     │
     ├─► PostgresPersistence / InMemoryPersistence  (IPersistence)
     ├─► AnthropicLLMProvider                       (ILLMProvider — optional)
     ├─► DailyVoiceTransport                        (IVoiceTransport)
     └─► CallManager (IPersistence + IVoiceTransport)
            │
            └── implements ICallLifecycleListener
                  (injected back into DailyVoiceTransport so Daily
                   event handlers drive status transitions without
                   importing the domain service)

Adapter choice is driven by :class:`src.config.Settings`:

* If ``DATABASE_URL`` points at a reachable Postgres and the ``[voice]``
  extras are installed, :class:`PostgresPersistence` is used.
* Otherwise — or when ``USE_IN_MEMORY_ADAPTERS=1`` — we fall back to
  :class:`InMemoryPersistence`.

Provider API keys (Deepgram, ElevenLabs, Anthropic) are *soft-required*
for the basic-call pipeline: if any are missing the service still boots
and candidate intake / admin listing endpoints work, but triggering a
call transitions the session to ``failed`` with
``metadata.failureReason = "missing_provider_credentials"``.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.adapters.anthropic_llm_provider import AnthropicLLMProvider
from src.adapters.daily_transport import DailyVoiceTransport
from src.adapters.in_memory_persistence import InMemoryPersistence
from src.api.routes import router
from src.config import Settings, get_settings
from src.domain.ports.llm_provider import ILLMProvider
from src.domain.ports.persistence import IPersistence
from src.domain.ports.voice_transport import IVoiceTransport
from src.domain.services.call_manager import CallManager

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    """Configure Python logging level from the LOG_LEVEL environment variable.

    INFO (default): external service connections, all bot dialog (TTS sent,
    STT received, LLM responses), call lifecycle events.
    DEBUG: full Pipecat frame traces — very verbose.

    Uvicorn only adds handlers to its own loggers (uvicorn.*), leaving the
    root logger with no handler.  Messages from src.* would be silently
    dropped by Python's "last resort" handler (WARNING+ only).  We add an
    explicit StreamHandler to the src logger so our INFO messages appear.
    """
    level_str = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_str, logging.INFO)

    src_logger = logging.getLogger("src")
    src_logger.setLevel(level)

    # Add a handler if one hasn't been attached yet (guard against double-add
    # on uvicorn --reload which re-imports the module in the worker process).
    if not src_logger.handlers:
        handler = logging.StreamHandler()
        handler.setLevel(logging.DEBUG)  # logger level does the filtering
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)-8s %(name)s - %(message)s",
                datefmt="%H:%M:%S",
            )
        )
        src_logger.addHandler(handler)
        src_logger.propagate = False  # don't double-emit via root

    # Pipecat uses loguru, not stdlib logging, so setLevel has no effect on
    # its output.  We note the desired level here for completeness but the
    # only way to silence Pipecat's DEBUG output is via loguru configuration
    # (e.g. LOGURU_LEVEL env var or loguru.logger.remove() + re-add).
    # We suppress it unless the caller explicitly asked for --debug.
    if level > logging.DEBUG:
        try:
            from loguru import logger as _loguru_logger  # noqa: PLC0415

            _loguru_logger.remove()
            _loguru_logger.add(
                __import__("sys").stderr,
                level="INFO",
                format="<green>{time:HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
            )
        except Exception:
            pass  # loguru not installed or already configured — ignore


def _build_persistence(settings: Settings) -> IPersistence:
    if os.environ.get("USE_IN_MEMORY_ADAPTERS") == "1":
        logger.info("Using InMemoryPersistence (USE_IN_MEMORY_ADAPTERS=1)")
        return InMemoryPersistence()

    try:
        from src.adapters.postgres_persistence import PostgresPersistence

        return PostgresPersistence(database_url=settings.database_url)
    except Exception as exc:  # pragma: no cover — dev convenience
        logger.warning(
            "PostgresPersistence unavailable (%s); falling back to InMemoryPersistence",
            exc,
        )
        return InMemoryPersistence()


def _build_llm_provider(settings: Settings) -> ILLMProvider | None:
    if not settings.anthropic_api_key:
        logger.warning(
            "ANTHROPIC_API_KEY is not set — the basic-call bot will use "
            "its hard-coded fallback acknowledgement. Set the key to "
            "enable Claude-generated acks."
        )
        return None
    return AnthropicLLMProvider(
        api_key=settings.anthropic_api_key,
        default_model=settings.anthropic_model,
    )


def _validate_dialing_env(settings: Settings) -> None:
    """Enforce that the selected transport has the env vars it needs to run."""
    if settings.dialing_method == "browser":
        if not (settings.livekit_url and settings.livekit_api_key and settings.livekit_api_secret):
            raise ValueError(
                "DIALING_METHOD=browser requires LIVEKIT_URL, LIVEKIT_API_KEY, "
                "and LIVEKIT_API_SECRET."
            )
    else:
        if not (settings.daily_api_key and settings.daily_domain):
            raise ValueError(
                "DIALING_METHOD=daily requires DAILY_API_KEY and DAILY_DOMAIN."
            )


def _warn_on_missing_provider_keys(settings: Settings) -> None:
    stt_tts: list[str] = []
    if not settings.deepgram_api_key:
        stt_tts.append("DEEPGRAM_API_KEY")
    if not settings.elevenlabs_api_key:
        stt_tts.append("ELEVENLABS_API_KEY")
    if settings.dialing_method == "daily" and not settings.daily_api_key:
        stt_tts.append("DAILY_API_KEY")
    if stt_tts:
        where = "Daily" if settings.dialing_method == "daily" else "LiveKit"
        logger.warning(
            "Missing provider credentials %s — /api/v1/assessment/trigger "
            "(%s) will be skipped and the session will fail with "
            "metadata.failureReason='missing_provider_credentials'.",
            stt_tts,
            where,
        )


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    _validate_dialing_env(settings)
    _warn_on_missing_provider_keys(settings)

    persistence = _build_persistence(settings)
    llm_provider = _build_llm_provider(settings)

    if settings.dialing_method == "browser":
        from src.adapters.livekit_transport import LiveKitVoiceTransport

        transport: IVoiceTransport = LiveKitVoiceTransport(
            settings=settings,
            llm_provider=llm_provider,
        )
    else:
        transport = DailyVoiceTransport(
            api_key=settings.daily_api_key,
            daily_domain=settings.daily_domain,
            bot_name=settings.bot_name,
            settings=settings,
            llm_provider=llm_provider,
        )

    call_manager = CallManager(
        persistence=persistence,
        voice_transport=transport,
        region=settings.daily_geo,
    )

    # Circular dependency resolved via setter injection: the transport
    # notifies the CallManager of transport events, while the
    # CallManager needs the transport to place the call.
    transport.set_listener(call_manager)

    app.state.settings = settings
    app.state.persistence = persistence
    app.state.voice_transport = transport
    app.state.llm_provider = llm_provider
    app.state.call_manager = call_manager

    try:
        yield
    finally:
        await call_manager.drain()
        close = getattr(persistence, "close", None)
        if callable(close):
            await close()
        close_transport = getattr(transport, "close", None)
        if callable(close_transport):
            await close_transport()


def create_app() -> FastAPI:
    _configure_logging()
    app = FastAPI(
        title="AI Skills Assessor — Voice Engine",
        version="0.4.2",
        description=(
            "Phase 3 Revision 2: basic live call via Daily (telephone) or "
            "self-hosted LiveKit (browser) — greeting, one question, "
            "LLM ack, hangup."
        ),
        lifespan=_lifespan,
    )
    app.include_router(router)
    return app


app = create_app()
