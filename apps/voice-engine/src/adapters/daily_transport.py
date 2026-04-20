"""Daily transport adapter (Phase 2 stub).

Implements :class:`IVoiceTransport` by talking to Daily's REST API
(``/v1/rooms`` and ``/v1/meeting-tokens``). The *actual* Pipecat
pipeline — PSTN dial-out, STT/TTS/LLM wiring, event handlers — is
explicitly deferred to Phase 3 per the phase document (§1.3).

For Phase 2 the adapter:

* Normalises the candidate phone number to E.164 before dialling.
* Creates a Daily room in the configured region with cloud recording
  enabled.
* Creates a meeting token for the bot "Noa".
* Returns a :class:`CallConnection` so ``CallManager`` can persist
  the room URL.
* Tracks per-session ``started_at`` / ``ended_at`` so
  ``get_call_duration`` can report live progress to the candidate UI.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx

from src.domain.models.assessment import CallConfig, CallConnection
from src.domain.ports.voice_transport import IVoiceTransport
from src.domain.utils.phone import normalise_phone_number


@dataclass
class _ActiveCall:
    connection: CallConnection
    room_name: str
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
    ) -> None:
        self._api_key = api_key
        self._daily_domain = daily_domain
        self._api_url = api_url.rstrip("/")
        self._room_ttl_seconds = room_ttl_seconds
        self._bot_name = bot_name
        self._http_client = http_client
        self._owns_client = http_client is None
        self._active: dict[str, _ActiveCall] = {}
        self._lock = asyncio.Lock()

    async def _client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=10.0,
            )
        return self._http_client

    async def close(self) -> None:
        if self._owns_client and self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    # ─── IVoiceTransport ─────────────────────────────────────────────

    async def dial(self, config: CallConfig) -> CallConnection:
        normalised = normalise_phone_number(config.phone_number)

        room = await self._create_room(region=config.region)
        await self._create_meeting_token(room["name"])

        connection = CallConnection(
            session_id=config.session_id,
            connection_id=str(uuid4()),
            room_url=room["url"],
            is_active=True,
            started_at=datetime.now(UTC),
        )

        async with self._lock:
            self._active[config.session_id] = _ActiveCall(
                connection=connection,
                room_name=room["name"],
            )

        # Phase 2 stub: we create the room + token so the audit trail is
        # visible in Daily's dashboard, but do NOT yet invoke the
        # Pipecat pipeline / PSTN dial-out. Phase 3 will replace this
        # block with a real Pipecat ``DailyTransport`` + outbound SIP
        # invite using ``normalised``.
        _ = normalised

        return connection

    async def hangup(self, connection: CallConnection) -> None:
        async with self._lock:
            active = self._active.get(connection.session_id)
            if active is None:
                return
            active.connection.is_active = False
            active.connection.ended_at = datetime.now(UTC)

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

    # ─── Daily REST helpers ──────────────────────────────────────────

    async def _create_room(self, *, region: str) -> dict[str, Any]:
        client = await self._client()
        payload = {
            "properties": {
                "enable_recording": "cloud",
                "geo": region,
                "exp": int(datetime.now(UTC).timestamp()) + self._room_ttl_seconds,
                "max_participants": 2,
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
