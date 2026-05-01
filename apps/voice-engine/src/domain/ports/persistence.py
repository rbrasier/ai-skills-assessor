"""``IPersistence`` port — write/read access to durable storage.

Phase 2 extends the Phase 1 port with candidate CRUD, status updates,
and admin querying. All methods are async so concrete adapters can use
``asyncpg`` (or similar) without blocking the event loop.

Phase 6 adds transcript and report persistence methods that write to
dedicated columns on ``assessment_sessions`` (promoted from JSONB metadata).
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
    async def save_transcript(
        self,
        session_id: str,
        transcript_json: dict[str, Any],
    ) -> None:
        """Write transcript JSON to assessment_sessions.transcript_json.

        Phase 6 replacement for the Phase 4 merge_session_metadata() approach.
        TranscriptRecorder.finalize() calls this method from Phase 6 onwards.
        """
        ...

    @abstractmethod
    async def get_transcript(
        self,
        session_id: str,
    ) -> dict[str, Any] | None:
        """Read transcript_json for a session. Returns None if not yet persisted."""
        ...

    # ─── Report ──────────────────────────────────────────────────────

    @abstractmethod
    async def save_report(
        self,
        session_id: str,
        claims: list[dict[str, Any]],
        review_token: str,
        overall_confidence: float,
        expires_at: datetime,
    ) -> None:
        """Write claims_json and report metadata to assessment_sessions.

        Sets: claims_json, review_token, overall_confidence,
        report_status='generated', report_generated_at=now(), expires_at.
        """
        ...

    @abstractmethod
    async def get_report(
        self,
        session_id: str,
    ) -> dict[str, Any] | None:
        """Read report metadata and claims_json for a session.

        Returns a dict with keys: session_id, claims_json, review_token,
        report_status, overall_confidence, report_generated_at,
        sme_reviewed_at, expires_at. Returns None if no report exists.
        """
        ...

    @abstractmethod
    async def get_report_by_token(
        self,
        review_token: str,
    ) -> dict[str, Any] | None:
        """Read session and report data by NanoID review token.

        Used by the public SME review endpoint. Returns None if token not
        found or expired.
        """
        ...

    @abstractmethod
    async def merge_session_metadata(
        self,
        session_id: str,
        metadata: dict[str, Any],
    ) -> None:
        """Merge additional metadata into a session without changing its status.

        Used for identified_skills and recording_duration_seconds. Transcript
        data is written via save_transcript() from Phase 6 onwards.
        """
        ...
