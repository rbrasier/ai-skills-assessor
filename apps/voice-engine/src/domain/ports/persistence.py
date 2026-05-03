"""``IPersistence`` port — write/read access to durable storage.

Phase 2 extends the Phase 1 port with candidate CRUD, status updates,
and admin querying. All methods are async so concrete adapters can use
``asyncpg`` (or similar) without blocking the event loop.

Phase 6 adds transcript and report persistence methods that write to
dedicated columns on ``assessment_sessions`` (promoted from JSONB metadata).

Phase 6 Revision (dual-review-tokens) extends save_report() to take
separate expert + supervisor tokens, and adds role-specific read and
save methods for the two-stage review workflow.

Monitoring phase adds:
  - append_focus_event / save_transcript_turn / set_termination for
    real-time call telemetry
  - get/grant/revoke candidate cooldown overrides and no-restrictions flag
  - get/save admin-level settings (cooldown period)
  - check_assessment_eligibility for the pre-call gate
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


class IPersistence(ABC):
    # ─── Liveness ────────────────────────────────────────────────────

    @abstractmethod
    async def ping(self) -> bool:
        """Probe the backing store. Returns ``True`` when reachable."""
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
        """Write transcript JSON to assessment_sessions.transcript_json."""
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
        expert_review_token: str,
        supervisor_review_token: str,
        overall_confidence: float,
        expires_at: datetime,
        holistic_assessment: list[dict[str, Any]] | None = None,
    ) -> None:
        """Write claims_json, holistic_assessment_json, and dual review tokens.

        Sets: claims_json, holistic_assessment_json, expert_review_token,
        supervisor_review_token, overall_confidence,
        report_status='awaiting_expert', report_generated_at=now(), expires_at.
        Also dual-writes review_token=expert_review_token for compat.
        """
        ...

    @abstractmethod
    async def get_report(
        self,
        session_id: str,
    ) -> dict[str, Any] | None:
        """Read report metadata and claims_json for a session."""
        ...

    @abstractmethod
    async def get_report_by_expert_token(
        self,
        expert_review_token: str,
    ) -> dict[str, Any] | None:
        """Read report data by expert NanoID token. Returns None if not found."""
        ...

    @abstractmethod
    async def get_report_by_supervisor_token(
        self,
        supervisor_review_token: str,
    ) -> dict[str, Any] | None:
        """Read report data by supervisor NanoID token. Returns None if not found."""
        ...

    @abstractmethod
    async def save_expert_review(
        self,
        expert_review_token: str,
        reviewer_full_name: str,
        reviewer_email: str,
        claims_patch: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Merge expert_level per claim; set expert audit columns.

        Advances report_status to 'awaiting_supervisor'.
        Returns updated report dict (session_id, report_status, reviews_completed_at).
        Raises ValueError if token not found.
        Raises RuntimeError if expert review already submitted (for 409 response).
        """
        ...

    @abstractmethod
    async def save_supervisor_review(
        self,
        supervisor_review_token: str,
        reviewer_full_name: str,
        reviewer_email: str,
        claims_patch: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Merge supervisor_decision + supervisor_comment per claim; set audit columns.

        If expert review already submitted, also sets reviews_completed_at and
        advances report_status to 'reviews_complete'.
        Returns updated report dict.
        Raises ValueError if token not found.
        Raises RuntimeError if supervisor review already submitted.
        """
        ...

    # ─── Phase 7: Enriched admin listing ────────────────────────────

    @abstractmethod
    async def list_admin_session_summaries(
        self,
        status: str | None = None,
        candidate_email: str | None = None,
        search: str | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Return enriched session summaries for the admin dashboard.

        Each dict includes basic session fields plus report-level fields
        derived from claims_json (max_sfia_level, overall_confidence,
        top_skill_codes) and session columns (candidate_name, report_status,
        expert_review_token, supervisor_review_token).
        """
        ...

    # ─── Metadata ────────────────────────────────────────────────────

    @abstractmethod
    async def merge_session_metadata(
        self,
        session_id: str,
        metadata: dict[str, Any],
    ) -> None:
        """Merge additional metadata into a session without changing its status."""
        ...

    # ─── Monitoring: focus events ────────────────────────────────────

    @abstractmethod
    async def append_focus_event(
        self,
        session_id: str,
        event: dict[str, Any],
    ) -> None:
        """Append one focus-loss event and update focus_suspicious / total_focus_away_ms.

        ``event`` must contain: ``at`` (ISO string), ``phase`` (str),
        ``durationMs`` (int).  The adapter recomputes totals and sets
        ``focus_suspicious = True`` when either total events > 4 or
        any single absence exceeds 60 000 ms.
        """
        ...

    # ─── Monitoring: progressive transcript ──────────────────────────

    @abstractmethod
    async def save_transcript_turn(
        self,
        session_id: str,
        turn: dict[str, Any],
    ) -> None:
        """Append one transcript turn to transcript_json.turns and update last_turn_saved_at.

        If no transcript row exists yet, initialises ``{"turns": [turn]}``.
        ``turn`` shape: ``{timestamp, speaker, text, phase, vad_confidence}``.
        """
        ...

    # ─── Monitoring: structured termination ──────────────────────────

    @abstractmethod
    async def set_termination(
        self,
        session_id: str,
        termination_reason: str,
        error_details: dict[str, Any] | None = None,
    ) -> None:
        """Write termination_reason and optional error_details to the session row."""
        ...

    # ─── Monitoring: candidate restrictions ──────────────────────────

    @abstractmethod
    async def get_candidate_restrictions(
        self,
        candidate_id: str,
    ) -> dict[str, Any]:
        """Return restriction state for a candidate.

        Keys: ``no_restrictions``, ``cooldown_override_granted_at``,
        ``cooldown_override_expires_at``, ``audit_log`` (list).
        Returns defaults (all None / False) when the candidate does not exist.
        """
        ...

    @abstractmethod
    async def grant_cooldown_override(
        self,
        candidate_id: str,
        granted_by: str,
        expires_at: datetime,
        reason: str | None = None,
    ) -> None:
        """Set a time-limited cooldown bypass and write an audit row."""
        ...

    @abstractmethod
    async def revoke_cooldown_override(
        self,
        candidate_id: str,
        revoked_by: str,
    ) -> None:
        """Clear the cooldown override and write an audit row."""
        ...

    @abstractmethod
    async def set_no_restrictions(
        self,
        candidate_id: str,
        enabled: bool,
        updated_by: str,
    ) -> None:
        """Toggle the no-restrictions flag and write an audit row."""
        ...

    # ─── Monitoring: admin settings ──────────────────────────────────

    @abstractmethod
    async def get_admin_settings(self) -> dict[str, Any]:
        """Return platform-wide admin settings (singleton row).

        Keys: ``cooldown_days``, ``updated_at``, ``updated_by``.
        Returns defaults when no row has been written yet.
        """
        ...

    @abstractmethod
    async def save_admin_settings(
        self,
        cooldown_days: int,
        updated_by: str | None = None,
    ) -> None:
        """Upsert the singleton admin-settings row."""
        ...

    # ─── Monitoring: eligibility ──────────────────────────────────────

    @abstractmethod
    async def check_assessment_eligibility(
        self,
        candidate_id: str,
    ) -> dict[str, Any]:
        """Compute whether a candidate may start a new assessment.

        Returns a dict with keys:
          ``eligible`` (bool), ``reason`` (str | None),
          ``next_eligible_at`` (datetime | None), ``cooldown_days`` (int).

        A candidate is ineligible when a session with a countable status
        (``completed``, ``processed``, ``user_ended``) exists within the
        current cooldown window AND neither ``no_restrictions`` nor a
        valid (non-expired) cooldown override is active.

        Technical failures (``failed`` status) are never counted.
        """
        ...
