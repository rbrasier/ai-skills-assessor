"""Unit tests for ``DailyVoiceTransport`` — Phase 3 Revision 1.

Covers the Daily REST flow (room + token creation) and the soft-fail
behaviour when provider API keys are missing. The Pipecat pipeline
itself is not exercised here — those tests live in
``test_basic_call_bot.py``.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from src.adapters.daily_transport import DailyVoiceTransport
from src.config import Settings
from src.domain.models.assessment import CallConfig
from src.domain.ports.call_lifecycle_listener import ICallLifecycleListener

pytestmark = pytest.mark.asyncio


class _RecordingListener(ICallLifecycleListener):
    def __init__(self) -> None:
        self.connected: list[str] = []
        self.ended: list[str] = []
        self.failed: list[tuple[str, str]] = []

    async def on_call_connected(self, session_id: str) -> None:
        self.connected.append(session_id)

    async def on_call_ended(self, session_id: str) -> None:
        self.ended.append(session_id)

    async def on_call_failed(self, session_id: str, *, reason: str) -> None:
        self.failed.append((session_id, reason))


def _daily_mock_handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    if url.endswith("/rooms"):
        return httpx.Response(
            200,
            json={
                "name": "room-abc",
                "url": "https://acme.daily.co/room-abc",
            },
        )
    if url.endswith("/meeting-tokens"):
        return httpx.Response(200, json={"token": "tok-xyz"})
    return httpx.Response(404, json={"error": "unexpected"})


def _mock_http_client() -> httpx.AsyncClient:
    transport = httpx.MockTransport(_daily_mock_handler)
    return httpx.AsyncClient(
        transport=transport,
        headers={"Authorization": "Bearer test"},
        timeout=5.0,
    )


async def test_dial_creates_room_and_token_without_provider_keys() -> None:
    listener = _RecordingListener()
    settings = Settings(
        daily_api_key="sk-daily",
        deepgram_api_key="",
        elevenlabs_api_key="",
        anthropic_api_key="",
    )
    transport = DailyVoiceTransport(
        api_key="sk-daily",
        http_client=_mock_http_client(),
        settings=settings,
        listener=listener,
    )

    connection = await transport.dial(
        CallConfig(
            session_id="sess-1",
            phone_number="+447700900118",
            candidate_id="sess-1",
            region="ap-southeast-1",
        )
    )

    assert connection.room_url == "https://acme.daily.co/room-abc"
    assert connection.is_active is True

    # Give the failure-notification task a chance to run.
    await asyncio.sleep(0)
    assert listener.failed == [("sess-1", "missing_provider_credentials")]

    await transport.close()


async def test_dial_without_listener_logs_and_skips_bot() -> None:
    settings = Settings(
        daily_api_key="sk-daily",
        deepgram_api_key="sk-dg",
        elevenlabs_api_key="sk-el",
    )
    transport = DailyVoiceTransport(
        api_key="sk-daily",
        http_client=_mock_http_client(),
        settings=settings,
        listener=None,  # not wired
    )

    connection = await transport.dial(
        CallConfig(
            session_id="sess-2",
            phone_number="+447700900118",
            candidate_id="sess-2",
        )
    )
    assert connection.is_active is True
    await transport.close()


async def test_get_call_duration_is_zero_for_unknown_session() -> None:
    transport = DailyVoiceTransport(
        api_key="", http_client=_mock_http_client(), settings=Settings()
    )
    assert await transport.get_call_duration("nope") == 0.0
    await transport.close()
