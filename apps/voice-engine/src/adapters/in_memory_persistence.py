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
        self._transcript_jsons: dict[str, dict[str, Any]] = {}
        self._reports: dict[str, dict[str, Any]] = {}
        # token → session_id maps for both roles
        self._expert_tokens: dict[str, str] = {}
        self._supervisor_tokens: dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def ping(self) -> bool:
        return True

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

    # ─── Transcript ──────────────────────────────────────────────────

    async def save_transcript(
        self,
        session_id: str,
        transcript_json: dict[str, Any],
    ) -> None:
        async with self._lock:
            self._transcript_jsons[session_id] = transcript_json

    async def get_transcript(
        self,
        session_id: str,
    ) -> dict[str, Any] | None:
        async with self._lock:
            return self._transcript_jsons.get(session_id)

    # ─── Report ──────────────────────────────────────────────────────

    async def save_report(
        self,
        session_id: str,
        claims: list[dict[str, Any]],
        expert_review_token: str,
        supervisor_review_token: str,
        overall_confidence: float,
        expires_at: datetime,
    ) -> None:
        async with self._lock:
            now = datetime.now(UTC)
            report = {
                "session_id": session_id,
                "claims_json": claims,
                "expert_review_token": expert_review_token,
                "supervisor_review_token": supervisor_review_token,
                # Deprecated compat field
                "review_token": expert_review_token,
                "report_status": "awaiting_expert",
                "overall_confidence": overall_confidence,
                "report_generated_at": now.isoformat(),
                "sme_reviewed_at": None,
                "expert_submitted_at": None,
                "expert_reviewer_name": None,
                "expert_reviewer_email": None,
                "supervisor_submitted_at": None,
                "supervisor_reviewer_name": None,
                "supervisor_reviewer_email": None,
                "reviews_completed_at": None,
                "expires_at": expires_at.isoformat(),
            }
            self._reports[session_id] = report
            self._expert_tokens[expert_review_token] = session_id
            self._supervisor_tokens[supervisor_review_token] = session_id

    async def get_report(
        self,
        session_id: str,
    ) -> dict[str, Any] | None:
        async with self._lock:
            return self._reports.get(session_id)

    async def get_report_by_expert_token(
        self,
        expert_review_token: str,
    ) -> dict[str, Any] | None:
        async with self._lock:
            session_id = self._expert_tokens.get(expert_review_token)
            if session_id is None:
                return None
            return self._reports.get(session_id)

    async def get_report_by_supervisor_token(
        self,
        supervisor_review_token: str,
    ) -> dict[str, Any] | None:
        async with self._lock:
            session_id = self._supervisor_tokens.get(supervisor_review_token)
            if session_id is None:
                return None
            return self._reports.get(session_id)

    async def save_expert_review(
        self,
        expert_review_token: str,
        reviewer_full_name: str,
        reviewer_email: str,
        claims_patch: list[dict[str, Any]],
    ) -> dict[str, Any]:
        async with self._lock:
            session_id = self._expert_tokens.get(expert_review_token)
            if session_id is None:
                raise ValueError(f"Expert token not found: {expert_review_token}")
            report = self._reports.get(session_id)
            if report is None:
                raise ValueError(f"Report not found for session: {session_id}")
            if report.get("expert_submitted_at") is not None:
                raise RuntimeError("Expert review already submitted")

            patch_by_id = {p["id"]: p for p in claims_patch}
            updated_claims = []
            for claim in report.get("claims_json", []):
                patch = patch_by_id.get(claim.get("id", ""))
                if patch:
                    claim = {**claim, "expert_level": patch["expert_level"]}
                updated_claims.append(claim)

            now = datetime.now(UTC).isoformat()
            report.update({
                "claims_json": updated_claims,
                "expert_submitted_at": now,
                "expert_reviewer_name": reviewer_full_name,
                "expert_reviewer_email": reviewer_email,
                "report_status": "awaiting_supervisor",
            })
            return {
                "session_id": session_id,
                "report_status": report["report_status"],
                "reviews_completed_at": report.get("reviews_completed_at"),
                "claims": updated_claims,
            }

    async def save_supervisor_review(
        self,
        supervisor_review_token: str,
        reviewer_full_name: str,
        reviewer_email: str,
        claims_patch: list[dict[str, Any]],
    ) -> dict[str, Any]:
        async with self._lock:
            session_id = self._supervisor_tokens.get(supervisor_review_token)
            if session_id is None:
                raise ValueError(f"Supervisor token not found: {supervisor_review_token}")
            report = self._reports.get(session_id)
            if report is None:
                raise ValueError(f"Report not found for session: {session_id}")
            if report.get("supervisor_submitted_at") is not None:
                raise RuntimeError("Supervisor review already submitted")

            patch_by_id = {p["id"]: p for p in claims_patch}
            updated_claims = []
            for claim in report.get("claims_json", []):
                patch = patch_by_id.get(claim.get("id", ""))
                if patch:
                    claim = {
                        **claim,
                        "supervisor_decision": patch["supervisor_decision"],
                        "supervisor_comment": patch["supervisor_comment"],
                    }
                updated_claims.append(claim)

            now = datetime.now(UTC)
            reviews_completed_at = None
            if report.get("expert_submitted_at") is not None:
                reviews_completed_at = now.isoformat()

            report.update({
                "claims_json": updated_claims,
                "supervisor_submitted_at": now.isoformat(),
                "supervisor_reviewer_name": reviewer_full_name,
                "supervisor_reviewer_email": reviewer_email,
                "report_status": "reviews_complete" if reviews_completed_at else "in_review",
                "reviews_completed_at": reviews_completed_at,
            })
            return {
                "session_id": session_id,
                "report_status": report["report_status"],
                "reviews_completed_at": reviews_completed_at,
                "claims": updated_claims,
            }

    # ─── Metadata ────────────────────────────────────────────────────

    async def merge_session_metadata(
        self,
        session_id: str,
        metadata: dict[str, Any],
    ) -> None:
        async with self._lock:
            current = self._sessions.get(session_id)
            if current is None:
                return
            merged = dict(current.metadata or {})
            merged.update(metadata)
            self._sessions[session_id] = replace(current, metadata=merged)


__all__ = ["InMemoryPersistence"]
