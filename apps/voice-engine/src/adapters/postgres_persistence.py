"""Postgres-backed persistence adapter — stub for Phase 1.

The real adapter will use ``asyncpg`` (or a Prisma-via-Node bridge — TBD in
the voice-engine phase) to write candidates / sessions / transcripts.
"""

from __future__ import annotations

from src.domain.models.assessment import AssessmentSession
from src.domain.models.transcript import Transcript
from src.domain.ports.persistence import IPersistence


class PostgresPersistence(IPersistence):
    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    async def save_session(self, session: AssessmentSession) -> None:
        raise NotImplementedError("PostgresPersistence.save_session is implemented in Phase 2")

    async def save_transcript(self, transcript: Transcript) -> None:
        raise NotImplementedError("PostgresPersistence.save_transcript is implemented in Phase 2")

    async def get_session(self, session_id: str) -> AssessmentSession | None:
        raise NotImplementedError("PostgresPersistence.get_session is implemented in Phase 2")
