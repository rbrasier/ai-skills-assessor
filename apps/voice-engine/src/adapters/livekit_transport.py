"""LiveKit transport adapter (self-hosted, browser join).

Phase 3 Revision 2: creates a LiveKit room name + JWTs for the bot and the
human participant, runs the same :class:`BasicCallBot` pipeline with Pipecat's
``LiveKitTransport``, and relays room events to :class:`ICallLifecycleListener`.

The adapter is import-safe without the ``[voice]`` extras (Pipecat is loaded
lazily from :mod:`src.flows.bot_runner`).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from livekit import api

from src.config import Settings, get_settings
from src.domain.models.assessment import CallConfig, CallConnection
from src.domain.ports.call_lifecycle_listener import ICallLifecycleListener
from src.domain.ports.llm_provider import ILLMProvider
from src.domain.ports.voice_transport import IVoiceTransport
from src.domain.utils.phone import normalise_phone_number

logger = logging.getLogger(__name__)


@dataclass
class _ActiveCall:
    connection: CallConnection
    bot: Any = None  # BasicCallBot


def _strip_trailing_slash(url: str) -> str:
    return url.rstrip("/")


def _build_join_url(
    settings: Settings, room_name: str, participant_token: str
) -> str:
    """Build a link the candidate can open in the browser to join the room.

    The JWT already grants access to ``room_name``; ``room_name`` is included
    for operators who point ``LIVEKIT_MEET_URL`` at a custom app that needs it.
    """
    from urllib.parse import urlencode

    base = _strip_trailing_slash(settings.livekit_meet_url)
    q = urlencode(
        {
            "url": settings.livekit_url,
            "token": participant_token,
            "room": room_name,
        }
    )
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}{q}"


def _mint_token(
    *,
    settings: Settings,
    room_name: str,
    identity: str,
    name: str,
) -> str:
    grants = api.VideoGrants(
        room_join=True,
        room=room_name,
    )
    at = (
        api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity(identity)
        .with_name(name)
        .with_ttl(timedelta(seconds=settings.livekit_token_ttl_seconds))
        .with_grants(grants)
    )
    return at.to_jwt()


class LiveKitVoiceTransport(IVoiceTransport):
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        listener: ICallLifecycleListener | None = None,
        llm_provider: ILLMProvider | None = None,
    ) -> None:
        self._settings = settings
        self._listener = listener
        self._llm_provider = llm_provider
        self._active: dict[str, _ActiveCall] = {}
        self._lock = asyncio.Lock()

    def set_listener(self, listener: ICallLifecycleListener) -> None:
        self._listener = listener

    def set_llm_provider(self, provider: ILLMProvider | None) -> None:
        self._llm_provider = provider

    def set_settings(self, settings: Settings) -> None:
        self._settings = settings

    async def close(self) -> None:
        async with self._lock:
            bots = [c.bot for c in self._active.values() if c.bot is not None]
        for bot in bots:
            try:
                await bot.cancel()
            except Exception:  # pragma: no cover
                logger.exception("LiveKitVoiceTransport.close: bot.cancel failed")

    @staticmethod
    def _has_provider_keys(settings: Settings) -> bool:
        return bool(settings.deepgram_api_key and settings.elevenlabs_api_key)

    async def dial(self, config: CallConfig) -> CallConnection:
        settings = self._settings or get_settings()
        room_name = f"as-{config.session_id.replace('-', '')[:32]}"
        normalised = normalise_phone_number(config.phone_number)

        bot_token = _mint_token(
            settings=settings,
            room_name=room_name,
            identity=f"bot-{config.session_id[:8]}",
            name=settings.bot_name,
        )
        human_token = _mint_token(
            settings=settings,
            room_name=room_name,
            identity=f"user-{config.candidate_id[:40]}",
            name=normalised,
        )
        join_url = _build_join_url(settings, room_name, human_token)

        connection = CallConnection(
            session_id=config.session_id,
            connection_id=str(uuid4()),
            room_url=settings.livekit_url,
            is_active=True,
            started_at=datetime.now(UTC),
            livekit_room_name=room_name,
            livekit_participant_token=human_token,
            browser_join_url=join_url,
        )

        bot: Any = None
        if self._listener is None:
            logger.warning(
                "LiveKitVoiceTransport.dial: no lifecycle listener — skipping "
                "Pipecat pipeline (session %s)",
                config.session_id,
            )
        elif not self._has_provider_keys(settings):
            logger.warning(
                "LiveKitVoiceTransport.dial: missing DEEPGRAM / ELEVENLABS "
                "keys — skipping pipeline (session %s)",
                config.session_id,
            )
            asyncio.create_task(
                self._listener.on_call_failed(
                    config.session_id,
                    reason="missing_provider_credentials",
                )
            )
        else:
            from src.flows.bot_runner import BasicCallBot

            bot = BasicCallBot(
                session_id=config.session_id,
                phone_number=normalised,
                room_url=settings.livekit_url,
                room_token=bot_token,
                room_name=room_name,
                settings=settings,
                listener=self._listener,
                llm_provider=self._llm_provider,
                transport_mode="livekit",
            )
            try:
                await bot.start()
            except Exception as exc:  # pragma: no cover
                logger.exception(
                    "BasicCallBot.start failed for session %s", config.session_id
                )
                asyncio.create_task(
                    self._listener.on_call_failed(
                        config.session_id,
                        reason=f"bot_start_failed: {exc}",
                    )
                )
                bot = None

        async with self._lock:
            self._active[config.session_id] = _ActiveCall(
                connection=connection,
                bot=bot,
            )

        return connection

    async def hangup(self, connection: CallConnection) -> None:
        async with self._lock:
            active = self._active.get(connection.session_id)
            if active is None:
                return
            active.connection.is_active = False
            active.connection.ended_at = datetime.now(UTC)
            bot = active.bot
        if bot is not None:
            try:
                await bot.cancel()
            except Exception:  # pragma: no cover
                logger.exception("LiveKitVoiceTransport.hangup: bot.cancel failed")

    async def get_call_duration(self, session_id: str) -> float:
        async with self._lock:
            active = self._active.get(session_id)
        if active is None:
            return 0.0
        started = active.connection.started_at
        if started is None:
            return 0.0
        ended = active.connection.ended_at or datetime.now(UTC)
        return max(0.0, (ended - started).total_seconds())

    async def get_recording_url(self, session_id: str) -> str | None:
        return None


__all__ = ["LiveKitVoiceTransport", "_build_join_url"]
