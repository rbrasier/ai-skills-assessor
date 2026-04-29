"""Daily transport adapter.

Phase 3 Revision 1: this adapter creates Daily rooms + meeting tokens
via the REST API, launches a :class:`BasicCallBot` Pipecat pipeline as
a background task for each session, and relays Daily event handlers
back into the domain via an :class:`ICallLifecycleListener`.

The adapter is import-safe without the ``[voice]`` extras: the Pipecat
pipeline (in ``src/flows/bot_runner.py``) is imported lazily when
``dial`` actually runs. Room + token creation only requires ``httpx``,
which is in the lean CI install, so unit tests can exercise the REST
client with ``respx`` and never touch Pipecat.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx

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
    room_name: str
    bot: Any = None  # BasicCallBot — Any to avoid the Pipecat import
    recording_url: str | None = None


class DailyVoiceTransport(IVoiceTransport):
    def __init__(
        self,
        api_key: str,
        daily_domain: str = "",
        *,
        api_url: str = "https://api.daily.co/v1",
        room_ttl_seconds: int = 7200,
        bot_name: str = "Noa",
        http_client: httpx.AsyncClient | None = None,
        settings: Settings | None = None,
        listener: ICallLifecycleListener | None = None,
        llm_provider: ILLMProvider | None = None,
    ) -> None:
        self._api_key = api_key
        self._daily_domain = daily_domain
        self._api_url = api_url.rstrip("/")
        self._room_ttl_seconds = room_ttl_seconds
        self._bot_name = bot_name
        self._http_client = http_client
        self._owns_client = http_client is None
        self._settings = settings
        self._listener = listener
        self._llm_provider = llm_provider
        self._active: dict[str, _ActiveCall] = {}
        self._lock = asyncio.Lock()

    # ─── Dependency setters (wired in main.py lifespan) ──────────────

    def set_listener(self, listener: ICallLifecycleListener) -> None:
        self._listener = listener

    def set_llm_provider(self, provider: ILLMProvider | None) -> None:
        self._llm_provider = provider

    def set_settings(self, settings: Settings) -> None:
        self._settings = settings

    # ─── HTTP plumbing ───────────────────────────────────────────────

    async def _client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=10.0,
            )
        return self._http_client

    async def close(self) -> None:
        # Cancel any in-flight bots before closing the HTTP client.
        async with self._lock:
            bots = [c.bot for c in self._active.values() if c.bot is not None]
        for bot in bots:
            try:
                await bot.cancel()
            except Exception:  # pragma: no cover — defensive
                logger.exception("DailyVoiceTransport.close: bot.cancel failed")
        if self._owns_client and self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    # ─── IVoiceTransport ─────────────────────────────────────────────

    async def dial(self, config: CallConfig) -> CallConnection:
        settings = self._settings or get_settings()
        normalised = normalise_phone_number(config.phone_number)

        room = await self._create_room(region=config.region)
        token = await self._create_meeting_token(room["name"])

        connection = CallConnection(
            session_id=config.session_id,
            connection_id=str(uuid4()),
            room_url=room["url"],
            is_active=True,
            started_at=datetime.now(UTC),
        )

        bot: Any = None
        if self._listener is None:
            logger.warning(
                "DailyVoiceTransport.dial: no lifecycle listener wired — "
                "skipping Pipecat pipeline (session %s)",
                config.session_id,
            )
        elif not self._has_provider_keys(settings):
            logger.warning(
                "DailyVoiceTransport.dial: missing one of DEEPGRAM / "
                "ELEVENLABS / DAILY API keys — skipping Pipecat pipeline "
                "(session %s). The Daily room was created so the audit "
                "trail is visible, but no bot will join.",
                config.session_id,
            )
            # Surface this as a failure so the UI doesn't hang.
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
                room_url=room["url"],
                room_token=token,
                settings=settings,
                listener=self._listener,
                llm_provider=self._llm_provider,
            )
            try:
                await bot.start()
            except Exception as exc:  # pragma: no cover — runtime
                logger.exception(
                    "BasicCallBot.start failed for session %s",
                    config.session_id,
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
                room_name=room["name"],
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
            except Exception:  # pragma: no cover — defensive
                logger.exception(
                    "DailyVoiceTransport.hangup: bot.cancel failed"
                )

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
        async with self._lock:
            active = self._active.get(session_id)
        return active.recording_url if active is not None else None

    # ─── Helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _has_provider_keys(settings: Settings) -> bool:
        return bool(
            settings.daily_api_key
            and settings.deepgram_api_key
            and settings.elevenlabs_api_key
        )

    # ─── Daily REST helpers ──────────────────────────────────────────

    async def _create_room(self, *, region: str) -> dict[str, Any]:
        client = await self._client()
        payload = {
            "properties": {
                "enable_recording": "cloud",
                "geo": region,
                "exp": int(datetime.now(UTC).timestamp()) + self._room_ttl_seconds,
                "max_participants": 2,
                "start_audio_off": False,
                "start_video_off": True,
                "enable_dialout": True,
            }
        }
        response = await client.post(f"{self._api_url}/rooms", json=payload)
        response.raise_for_status()
        return dict(response.json())

    async def _create_meeting_token(self, room_name: str) -> str:
        client = await self._client()
        payload = {
            "properties": {
                "room_name": room_name,
                "is_owner": True,
                "user_name": self._bot_name,
            }
        }
        response = await client.post(
            f"{self._api_url}/meeting-tokens",
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
        return str(data.get("token", ""))


__all__ = ["DailyVoiceTransport"]
