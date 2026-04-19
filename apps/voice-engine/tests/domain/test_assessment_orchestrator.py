"""Unit tests for ``AssessmentOrchestrator`` using in-memory adapters.

Demonstrates the hexagonal pattern: business logic is exercised end-to-end
without spinning up Postgres or Daily.
"""

from __future__ import annotations

from src.domain.models.assessment import (
    AssessmentSession,
    AssessmentStatus,
    CallConfig,
    CallConnection,
)
from src.domain.models.transcript import Transcript
from src.domain.ports.persistence import IPersistence
from src.domain.ports.voice_transport import IVoiceTransport
from src.domain.services.assessment_orchestrator import AssessmentOrchestrator


class InMemoryPersistence(IPersistence):
    def __init__(self) -> None:
        self.sessions: dict[str, AssessmentSession] = {}
        self.transcripts: dict[str, Transcript] = {}

    async def save_session(self, session: AssessmentSession) -> None:
        self.sessions[session.id] = session

    async def save_transcript(self, transcript: Transcript) -> None:
        self.transcripts[transcript.id] = transcript

    async def get_session(self, session_id: str) -> AssessmentSession | None:
        return self.sessions.get(session_id)


class FakeVoiceTransport(IVoiceTransport):
    async def dial(self, config: CallConfig) -> CallConnection:
        return CallConnection(
            connection_id="conn-1",
            room_url=f"https://daily.example/{config.candidate_id}",
            is_active=True,
        )

    async def hangup(self, connection: CallConnection) -> None:
        return None


async def test_trigger_persists_session_and_dials() -> None:
    persistence = InMemoryPersistence()
    transport = FakeVoiceTransport()
    orchestrator = AssessmentOrchestrator(persistence, transport)

    config = CallConfig(phone_number="+61412345678", candidate_id="cand-1")
    session = await orchestrator.trigger(config)

    assert session.status == AssessmentStatus.DIALLING
    assert session.daily_room_url == "https://daily.example/cand-1"
    assert session.started_at is not None
    assert persistence.sessions[session.id] == session
