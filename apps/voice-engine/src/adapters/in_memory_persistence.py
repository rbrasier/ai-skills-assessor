"""In-memory ``IPersistence`` adapter.

Used by the domain tests and the FastAPI test client so Phase 2
integration tests don't require a running Postgres. Production wiring
in ``apps/voice-engine/src/main.py`` should prefer
:class:`PostgresPersistence`.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from src.domain.models.assessment import (
    AssessmentSession,
    AssessmentStatus,
    Candidate,
)
from src.domain.models.transcript import Transcript
from src.domain.ports.persistence import IPersistence


class InMemoryPersistence(IPersistence):
    def __init__(self) -> None:
        self._candidates: dict[str, Candidate] = {}
        self._sessions: dict[str, AssessmentSession] = {}
        self._transcripts: dict[str, Transcript] = {}
        self._lock = asyncio.Lock()

    async def get_or_create_candidate(
        self,
        email: str,
        first_name: str,
        last_name: str,
        employee_id: str,
    ) -> Candidate:
        async with self._lock:
            existing = self._candidates.get(email)
            if existing is not None:
                return existing

            candidate = Candidate(
                email=email,
                first_name=first_name,
                last_name=last_name,
                metadata={"employee_id": employee_id} if employee_id else {},
                created_at=datetime.now(UTC),
            )
            self._candidates[email] = candidate
            return candidate

    async def create_session(self, session: AssessmentSession) -> AssessmentSession:
        async with self._lock:
            stored = replace(session)
            if stored.created_at is None:
                stored = replace(stored, created_at=datetime.now(UTC))
            self._sessions[stored.id] = stored
            return stored

    async def save_session(self, session: AssessmentSession) -> None:
        async with self._lock:
            self._sessions[session.id] = session

    async def get_session(self, session_id: str) -> AssessmentSession | None:
        async with self._lock:
            return self._sessions.get(session_id)

    async def update_session_status(
        self,
        session_id: str,
        status: AssessmentStatus | str,
        metadata: dict[str, Any] | None = None,
        started_at: datetime | None = None,
        ended_at: datetime | None = None,
        daily_room_url: str | None = None,
        recording_url: str | None = None,
    ) -> AssessmentSession | None:
        async with self._lock:
            current = self._sessions.get(session_id)
            if current is None:
                return None

            merged = dict(current.metadata or {})
            if metadata:
                merged.update(metadata)

            new_status = (
                status
                if isinstance(status, AssessmentStatus)
                else AssessmentStatus(status)
            )

            updated = replace(
                current,
                status=new_status,
                metadata=merged,
                started_at=started_at if started_at is not None else current.started_at,
                ended_at=ended_at if ended_at is not None else current.ended_at,
                daily_room_url=daily_room_url
                if daily_room_url is not None
                else current.daily_room_url,
                recording_url=recording_url
                if recording_url is not None
                else current.recording_url,
            )
            self._sessions[session_id] = updated
            return updated

    async def query_sessions(
        self,
        status: str | None = None,
        candidate_email: str | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AssessmentSession]:
        async with self._lock:
            items = list(self._sessions.values())

        def _status_val(s: AssessmentSession) -> str:
            return (
                s.status.value
                if isinstance(s.status, AssessmentStatus)
                else str(s.status)
            )

        if status is not None:
            items = [s for s in items if _status_val(s) == status]
        if candidate_email is not None:
            items = [s for s in items if s.candidate_id == candidate_email]
        if created_after is not None:
            items = [s for s in items if s.created_at and s.created_at >= created_after]
        if created_before is not None:
            items = [
                s for s in items if s.created_at and s.created_at <= created_before
            ]

        items.sort(
            key=lambda s: s.created_at or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )
        return items[offset : offset + limit]

    async def save_transcript(self, transcript: Transcript) -> None:
        async with self._lock:
            self._transcripts[transcript.id] = transcript


__all__ = ["InMemoryPersistence"]
