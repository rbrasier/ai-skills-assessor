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
from src.domain.services.call_manager import CallManager

logger = logging.getLogger(__name__)


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


def _warn_on_missing_provider_keys(settings: Settings) -> None:
    missing = [
        name
        for name, value in (
            ("DAILY_API_KEY", settings.daily_api_key),
            ("DEEPGRAM_API_KEY", settings.deepgram_api_key),
            ("ELEVENLABS_API_KEY", settings.elevenlabs_api_key),
        )
        if not value
    ]
    if missing:
        logger.warning(
            "Missing provider credentials %s — /api/v1/assessment/trigger "
            "calls will create a Daily room but the Pipecat bot pipeline "
            "will be skipped and the session will fail with "
            "metadata.failureReason='missing_provider_credentials'.",
            missing,
        )


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()

    _warn_on_missing_provider_keys(settings)

    persistence = _build_persistence(settings)
    llm_provider = _build_llm_provider(settings)

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
    # needs to notify the CallManager of Daily events, but the
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
    app = FastAPI(
        title="AI Skills Assessor — Voice Engine",
        version="0.4.1",
        description=(
            "Phase 3 Revision 1: basic live call (greeting → one question → "
            "LLM ack → hangup) on top of the Railway (Singapore) deployment."
        ),
        lifespan=_lifespan,
    )
    app.include_router(router)
    return app


app = create_app()
