"""Shared pytest fixtures for the voice engine."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from src.adapters.in_memory_persistence import InMemoryPersistence
from src.domain.models.assessment import CallConfig, CallConnection
from src.domain.ports.voice_transport import IVoiceTransport
from src.domain.services.call_manager import CallManager


def pytest_addoption(parser: pytest.Parser) -> None:
    # Phase 3 / v0.4.0 — gate the production smoke test behind an
    # explicit flag so ``pytest`` from the repo root doesn't try to
    # reach a live Railway URL during local dev or CI.
    parser.addoption(
        "--run-smoke",
        action="store_true",
        default=False,
        help="Run the production smoke test against SMOKE_TEST_URL.",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "smoke: post-deploy smoke tests (require --run-smoke + SMOKE_TEST_URL)",
    )


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    if config.getoption("--run-smoke"):
        return
    skip_smoke = pytest.mark.skip(reason="smoke test — pass --run-smoke to enable")
    for item in items:
        if "smoke" in item.keywords:
            item.add_marker(skip_smoke)


class _FakeVoiceTransport(IVoiceTransport):
    """Test-only transport. Records calls and exposes deterministic timing."""

    def __init__(self) -> None:
        self.dialled: list[CallConfig] = []
        self.hungup: list[CallConnection] = []

    async def dial(self, config: CallConfig) -> CallConnection:
        self.dialled.append(config)
        return CallConnection(
            session_id=config.session_id,
            connection_id=f"conn-{config.session_id}",
            room_url=f"https://daily.example/{config.session_id}",
            is_active=True,
        )

    async def hangup(self, connection: CallConnection) -> None:
        self.hungup.append(connection)

    async def get_call_duration(self, session_id: str) -> float:
        return 1.25

    async def get_recording_url(self, session_id: str) -> str | None:
        return None


@pytest.fixture()
def fake_transport() -> _FakeVoiceTransport:
    return _FakeVoiceTransport()


@pytest.fixture()
def persistence() -> InMemoryPersistence:
    return InMemoryPersistence()


@pytest.fixture()
def call_manager(
    persistence: InMemoryPersistence,
    fake_transport: _FakeVoiceTransport,
) -> CallManager:
    return CallManager(persistence=persistence, voice_transport=fake_transport)


@pytest.fixture()
def client(
    persistence: InMemoryPersistence,
    fake_transport: _FakeVoiceTransport,
    call_manager: CallManager,
) -> Iterator[TestClient]:
    os.environ["USE_IN_MEMORY_ADAPTERS"] = "1"
    from src.main import create_app

    app = create_app()
    with TestClient(app) as test_client:
        # Replace the lifespan-created manager with the test fixture so
        # test state is deterministic.
        app.state.persistence = persistence
        app.state.voice_transport = fake_transport
        app.state.call_manager = call_manager
        yield test_client
