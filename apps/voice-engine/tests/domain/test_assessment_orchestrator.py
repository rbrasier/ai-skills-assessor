"""Unit tests for ``AssessmentOrchestrator`` using in-memory adapters.

Demonstrates the hexagonal pattern: business logic is exercised end-to-end
without spinning up Postgres or Daily.
"""

from __future__ import annotations

from datetime import UTC, datetime

from src.domain.models.assessment import (
    AssessmentStatus,
    CallConfig,
    CallConnection,
)
from src.domain.ports.voice_transport import IVoiceTransport
from src.domain.services.assessment_orchestrator import AssessmentOrchestrator


class FakeVoiceTransport(IVoiceTransport):
    async def dial(self, config: CallConfig) -> CallConnection:
        return CallConnection(
            session_id=config.session_id,
            connection_id="conn-1",
            room_url=f"https://daily.example/{config.candidate_id}",
            is_active=True,
            started_at=datetime.now(UTC),
        )

    async def hangup(self, connection: CallConnection) -> None:
        return None

    async def get_call_duration(self, session_id: str) -> float:
        return 0.0

    async def get_recording_url(self, session_id: str) -> str | None:
        return None


async def test_trigger_persists_session_and_dials() -> None:
    from src.adapters.in_memory_persistence import InMemoryPersistence

    persistence = InMemoryPersistence()
    transport = FakeVoiceTransport()
    orchestrator = AssessmentOrchestrator(persistence, transport)

    # Seed the candidate — the orchestrator does not call
    # ``get_or_create_candidate`` itself (that's the CallManager's job).
    await persistence.get_or_create_candidate(
        email="cand-1@example.com",
        first_name="A",
        last_name="B",
        employee_id="EMP-1",
    )

    config = CallConfig(
        session_id="sess-1",
        phone_number="+61412345678",
        candidate_id="cand-1@example.com",
    )
    session = await orchestrator.trigger(config)

    assert session.status == AssessmentStatus.DIALLING
    assert session.daily_room_url == "https://daily.example/cand-1@example.com"
    assert session.started_at is not None
    stored = await persistence.get_session(session.id)
    assert stored is not None
    assert stored.status == AssessmentStatus.DIALLING
