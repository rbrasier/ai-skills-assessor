"""High-level assessment orchestration (Phase 1 skeleton).

This service composes the persistence and voice-transport ports and exposes a
single ``trigger`` entry point. Phase 1 only provides the ``AssessmentOrchestrator``
shape; richer state-machine behaviour (retries, recording, analysis hand-off)
is added by later phases.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

from src.domain.models.assessment import (
    AssessmentSession,
    AssessmentStatus,
    CallConfig,
)
from src.domain.ports.persistence import IPersistence
from src.domain.ports.voice_transport import IVoiceTransport


class AssessmentOrchestrator:
    """Coordinates persistence + transport to start an assessment call."""

    def __init__(
        self,
        persistence: IPersistence,
        transport: IVoiceTransport,
    ) -> None:
        self._persistence = persistence
        self._transport = transport

    async def trigger(self, config: CallConfig) -> AssessmentSession:
        session = AssessmentSession(
            id=str(uuid4()),
            candidate_id=config.candidate_id,
            phone_number=config.phone_number,
            status=AssessmentStatus.PENDING,
        )
        await self._persistence.save_session(session)

        connection = await self._transport.dial(config)

        started_session = replace(
            session,
            status=AssessmentStatus.DIALLING,
            daily_room_url=connection.room_url,
            started_at=datetime.now(UTC),
        )
        await self._persistence.save_session(started_session)

        return started_session
