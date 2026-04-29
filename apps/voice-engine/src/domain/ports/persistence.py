"""``IPersistence`` port — write/read access to durable storage.

Phase 2 extends the Phase 1 port with candidate CRUD, status updates,
and admin querying. All methods are async so concrete adapters can use
``asyncpg`` (or similar) without blocking the event loop.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from src.domain.models.assessment import (
    AssessmentSession,
    AssessmentStatus,
    Candidate,
)
from src.domain.models.transcript import Transcript


class IPersistence(ABC):
    # ─── Liveness ────────────────────────────────────────────────────

    @abstractmethod
    async def ping(self) -> bool:
        """Probe the backing store. Returns ``True`` when reachable.

        Added in Phase 3 / v0.4.0 so the ``/health`` endpoint can tell
        Railway that a deploy is unhealthy when the DB is unreachable.
        Adapters should swallow expected connection errors and return
        ``False`` — they must never raise.
        """
        ...

    # ─── Candidate ───────────────────────────────────────────────────

    @abstractmethod
    async def get_or_create_candidate(
        self,
        email: str,
        first_name: str,
        last_name: str,
        employee_id: str,
    ) -> Candidate:
        """Return the candidate row for ``email``, creating if absent."""
        ...

    # ─── Session ─────────────────────────────────────────────────────

    @abstractmethod
    async def create_session(self, session: AssessmentSession) -> AssessmentSession:
        """Insert a new assessment session and return it."""
        ...

    @abstractmethod
    async def save_session(self, session: AssessmentSession) -> None:
        """Upsert an assessment session."""
        ...

    @abstractmethod
    async def get_session(self, session_id: str) -> AssessmentSession | None:
        """Retrieve a session by id, or ``None`` if it does not exist."""
        ...

    @abstractmethod
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
        """Update status / timestamps / metadata and return the row.

        ``metadata``, when provided, is **merged** into the existing
        metadata dict rather than replacing it.
        """
        ...

    @abstractmethod
    async def query_sessions(
        self,
        status: str | None = None,
        candidate_email: str | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AssessmentSession]:
        """Admin list query — returns sessions newest-first."""
        ...

    # ─── Transcript ──────────────────────────────────────────────────

    @abstractmethod
    async def save_transcript(self, transcript: Transcript) -> None:
        """Persist a transcript and its segments.

        Phase 2 does not generate transcripts yet; adapters may stub
        this method, but the port shape is preserved for Phase 3+.
        """
        ...

    @abstractmethod
    async def merge_session_metadata(
        self,
        session_id: str,
        metadata: dict[str, Any],
    ) -> None:
        """Merge additional metadata into a session without changing its status.

        Phase 4 uses this to store transcript_json, identified_skills, and
        recording_duration_seconds in the JSONB metadata column without
        overwriting the session's current status.
        """
        ...
