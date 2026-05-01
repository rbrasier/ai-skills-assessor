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
from typing import Any

from fastapi import FastAPI

from src.adapters.anthropic_claim_llm_provider import AnthropicClaimLLMProvider
from src.adapters.anthropic_llm_provider import AnthropicLLMProvider
from src.adapters.daily_transport import DailyVoiceTransport
from src.adapters.in_memory_persistence import InMemoryPersistence
from src.api.routes import router
from src.config import Settings, get_settings
from src.domain.ports.llm_provider import ILLMProvider
from src.domain.ports.persistence import IPersistence
from src.domain.ports.voice_transport import IVoiceTransport
from src.domain.services.call_manager import CallManager
from src.domain.services.claim_extractor import ClaimExtractor
from src.domain.services.post_call_pipeline import PostCallPipeline
from src.domain.services.report_generator import ReportGenerator

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
        default_model=settings.anthropic_in_call_model,
    )


def _build_post_call_pipeline(
    settings: Settings,
    persistence: IPersistence,
) -> PostCallPipeline | None:
    """Build the Phase 6 post-call pipeline if Anthropic credentials are set.

    Returns None in in-memory / test mode — the POST /process endpoint will
    return 503 when the pipeline is absent, which is expected in lean CI.
    """
    if not settings.anthropic_api_key:
        logger.warning(
            "ANTHROPIC_API_KEY not set — post-call claim extraction pipeline disabled. "
            "POST /api/v1/assessment/{session_id}/process will return 503."
        )
        return None

    claim_llm = AnthropicClaimLLMProvider(
        api_key=settings.anthropic_api_key,
        model=settings.anthropic_post_call_model,
    )

    # Build pgvector knowledge base with embedder if openai_api_key is set.
    knowledge_base: Any = None
    try:
        from src.adapters.pgvector_knowledge_base import PgVectorKnowledgeBase

        if settings.openai_api_key:
            from src.adapters.openai_embedder import OpenAIEmbeddingService

            embedder = OpenAIEmbeddingService(api_key=settings.openai_api_key)
            knowledge_base = _PgVectorKBWrapper(
                database_url=settings.database_url, embedder=embedder
            )
        else:
            logger.warning(
                "OPENAI_API_KEY not set — claim-to-SFIA RAG mapping will use empty "
                "skill context. Claims will be extracted but may lack accurate SFIA levels."
            )
    except ImportError:
        logger.warning("pgvector adapter not available — knowledge base disabled")

    claim_extractor = ClaimExtractor(
        llm_provider=claim_llm,
        knowledge_base=knowledge_base or _NullKnowledgeBase(),
    )
    report_generator = ReportGenerator(
        persistence=persistence,
        base_url=settings.base_url,
    )
    return PostCallPipeline(
        claim_extractor=claim_extractor,
        report_generator=report_generator,
        persistence=persistence,
    )


class _NullKnowledgeBase:
    """Stub knowledge base that returns no results — used when pgvector unavailable."""

    async def query(self, *args: Any, **kwargs: Any) -> list:
        return []

    async def query_by_skill_code(self, *args: Any, **kwargs: Any) -> list:
        return []


class _PgVectorKBWrapper:
    """Lazy-pool pgvector knowledge base for the post-call pipeline.

    Creates its own asyncpg pool on first use, separate from the one owned
    by PostgresPersistence. Closed on lifespan shutdown.
    """

    def __init__(self, database_url: str, embedder: Any) -> None:
        self._database_url = database_url
        self._embedder = embedder
        self._kb: Any = None
        self._pool: Any = None

    async def _get_kb(self) -> Any:
        if self._kb is None:
            import asyncpg

            from src.adapters.pgvector_knowledge_base import PgVectorKnowledgeBase

            self._pool = await asyncpg.create_pool(self._database_url)
            self._kb = PgVectorKnowledgeBase(
                db_pool=self._pool, embedder=self._embedder
            )
        return self._kb

    async def query(self, *args: Any, **kwargs: Any) -> list:
        kb = await self._get_kb()
        return await kb.query(*args, **kwargs)

    async def query_by_skill_code(self, *args: Any, **kwargs: Any) -> list:
        kb = await self._get_kb()
        return await kb.query_by_skill_code(*args, **kwargs)

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
            self._kb = None


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
    post_call_pipeline = _build_post_call_pipeline(settings, persistence)

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
    app.state.post_call_pipeline = post_call_pipeline

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
        # Close the knowledge base pool if it was opened
        if post_call_pipeline is not None:
            try:
                kb = getattr(
                    getattr(post_call_pipeline, "claim_extractor", None), "kb", None
                )
                close_kb = getattr(kb, "close", None)
                if callable(close_kb):
                    await close_kb()
            except Exception:
                pass


def create_app() -> FastAPI:
    _configure_logging()
    app = FastAPI(
        title="AI Skills Assessor — Voice Engine",
        version="0.6.0",
        description=(
            "Phase 6: SFIA assessment flow with claim extraction pipeline, "
            "dual expert/supervisor review tokens, and post-call report generation."
        ),
        lifespan=_lifespan,
    )
    app.include_router(router)
    return app


app = create_app()
