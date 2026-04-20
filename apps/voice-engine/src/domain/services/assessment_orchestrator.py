"""High-level assessment orchestration (Phase 1 skeleton).

Phase 2 supersedes this class with :class:`CallManager` in
``src.domain.services.call_manager``; ``AssessmentOrchestrator`` is
kept for backwards compatibility with the Phase 1 unit tests that
demonstrated the hexagonal pattern.
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
        session_id = config.session_id or str(uuid4())
        session = AssessmentSession(
            id=session_id,
            candidate_id=config.candidate_id,
            phone_number=config.phone_number,
            status=AssessmentStatus.PENDING,
            created_at=datetime.now(UTC),
        )
        await self._persistence.save_session(session)

        # Ensure the transport sees the same session id.
        transport_config = replace(config, session_id=session_id)
        connection = await self._transport.dial(transport_config)

        started_session = replace(
            session,
            status=AssessmentStatus.DIALLING,
            daily_room_url=connection.room_url,
            started_at=datetime.now(UTC),
        )
        await self._persistence.save_session(started_session)

        return started_session
