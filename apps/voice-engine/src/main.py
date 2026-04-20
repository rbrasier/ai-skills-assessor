"""FastAPI application entry point for the voice engine.

Phase 2: instantiates the persistence + voice-transport adapters and a
singleton :class:`CallManager` at startup, then exposes the routers
from :mod:`src.api.routes`.

Adapter choice is driven by :class:`src.config.Settings`:

* If ``DATABASE_URL`` points at a reachable Postgres and the ``[voice]``
  extras are installed, :class:`PostgresPersistence` is used.
* Otherwise — or when ``USE_IN_MEMORY_ADAPTERS=1`` — we fall back to
  :class:`InMemoryPersistence`. This keeps local dev and CI frictionless
  and is also what the test suite uses.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.adapters.daily_transport import DailyVoiceTransport
from src.adapters.in_memory_persistence import InMemoryPersistence
from src.api.routes import router
from src.config import Settings, get_settings
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


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()

    persistence = _build_persistence(settings)
    transport = DailyVoiceTransport(
        api_key=settings.daily_api_key,
        daily_domain=settings.daily_domain,
    )
    call_manager = CallManager(
        persistence=persistence,
        voice_transport=transport,
    )

    app.state.settings = settings
    app.state.persistence = persistence
    app.state.voice_transport = transport
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
        version="0.4.0",
        description=(
            "Phase 3: candidate self-service assessment trigger, call tracking, "
            "and production Railway (Singapore) deployment."
        ),
        lifespan=_lifespan,
    )
    app.include_router(router)
    return app


app = create_app()
