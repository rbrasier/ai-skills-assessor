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

_DEFAULT_COOLDOWN_DAYS = 90
_FOCUS_SUSPICIOUS_MAX_EVENTS = 5
_FOCUS_SUSPICIOUS_MAX_AWAY_MS = 60_000

# Statuses that count toward the cooldown window
_COUNTABLE_STATUSES = {"completed", "processed", "user_ended"}


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
        # Monitoring state
        self._restriction_audits: list[dict[str, Any]] = []
        self._admin_settings: dict[str, Any] = {
            "cooldown_days": _DEFAULT_COOLDOWN_DAYS,
            "updated_at": None,
            "updated_by": None,
        }
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
        holistic_assessment: list[dict[str, Any]] | None = None,
    ) -> None:
        async with self._lock:
            now = datetime.now(UTC)
            report = {
                "session_id": session_id,
                "claims_json": claims,
                "holistic_assessment_json": holistic_assessment or [],
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

    # ─── Phase 7: Enriched admin listing ────────────────────────────

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
        async with self._lock:
            sessions = list(self._sessions.values())

        if status is not None:
            sessions = [s for s in sessions if (
                s.status.value if isinstance(s.status, AssessmentStatus) else s.status
            ) == status]
        if candidate_email is not None:
            sessions = [s for s in sessions if s.candidate_id == candidate_email]
        if search is not None:
            q = search.lower()
            sessions = [s for s in sessions if (
                q in s.candidate_id.lower()
                or (s.candidate_name and q in s.candidate_name.lower())
            )]
        if created_after is not None:
            sessions = [s for s in sessions if s.created_at and s.created_at >= created_after]
        if created_before is not None:
            sessions = [s for s in sessions if s.created_at and s.created_at <= created_before]

        sessions = sorted(sessions, key=lambda s: s.created_at or datetime.min, reverse=True)
        page = sessions[offset: offset + limit]

        summaries = []
        for s in page:
            report = self._reports.get(s.id, {})
            claims = report.get("claims_json") or []
            max_level: int | None = None
            top_codes: list[str] = []
            if claims:
                levels = [c.get("level") for c in claims if c.get("level")]
                if levels:
                    max_level = max(levels)
                seen: dict[str, int] = {}
                for c in claims:
                    code = c.get("skill_code") or c.get("skillCode")
                    if code:
                        seen[code] = seen.get(code, 0) + 1
                top_codes = [k for k, _ in sorted(seen.items(), key=lambda x: -x[1])][:5]

            duration = 0.0
            if s.started_at and s.ended_at:
                duration = (s.ended_at - s.started_at).total_seconds()

            summaries.append({
                "session_id": s.id,
                "candidate_email": s.candidate_id,
                "phone_number": s.phone_number or "",
                "status": s.status.value if isinstance(s.status, AssessmentStatus) else s.status,
                "duration_seconds": duration,
                "created_at": s.created_at.isoformat() if s.created_at else "",
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "ended_at": s.ended_at.isoformat() if s.ended_at else None,
                "candidate_name": s.candidate_name,
                "report_status": report.get("report_status"),
                "expert_review_token": report.get("expert_review_token"),
                "supervisor_review_token": report.get("supervisor_review_token"),
                "max_sfia_level": max_level,
                "overall_confidence": report.get("overall_confidence"),
                "top_skill_codes": top_codes,
                "termination_reason": s.termination_reason,
                "focus_suspicious": s.focus_suspicious,
                "total_focus_away_ms": s.total_focus_away_ms,
            })
        return summaries

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

    # ─── Monitoring: focus events ────────────────────────────────────

    async def append_focus_event(
        self,
        session_id: str,
        event: dict[str, Any],
    ) -> None:
        async with self._lock:
            current = self._sessions.get(session_id)
            if current is None:
                return
            events: list[dict[str, Any]] = list(current.focus_events_json or [])
            events.append(event)
            total_ms = current.total_focus_away_ms + int(event.get("durationMs", 0))
            suspicious = (
                len(events) >= _FOCUS_SUSPICIOUS_MAX_EVENTS
                or total_ms >= _FOCUS_SUSPICIOUS_MAX_AWAY_MS
                or current.focus_suspicious
            )
            self._sessions[session_id] = replace(
                current,
                focus_events_json=events,
                total_focus_away_ms=total_ms,
                focus_suspicious=suspicious,
            )

    # ─── Monitoring: progressive transcript ──────────────────────────

    async def save_transcript_turn(
        self,
        session_id: str,
        turn: dict[str, Any],
    ) -> None:
        async with self._lock:
            existing = self._transcript_jsons.get(session_id, {"turns": []})
            turns = list(existing.get("turns", []))
            turns.append(turn)
            self._transcript_jsons[session_id] = {**existing, "turns": turns}
            current = self._sessions.get(session_id)
            if current is not None:
                self._sessions[session_id] = replace(
                    current, last_turn_saved_at=datetime.now(UTC)
                )

    # ─── Monitoring: structured termination ──────────────────────────

    async def set_termination(
        self,
        session_id: str,
        termination_reason: str,
        error_details: dict[str, Any] | None = None,
    ) -> None:
        async with self._lock:
            current = self._sessions.get(session_id)
            if current is None:
                return
            self._sessions[session_id] = replace(
                current,
                termination_reason=termination_reason,
                error_details=error_details,
            )

    # ─── Monitoring: candidate restrictions ──────────────────────────

    async def get_candidate_restrictions(
        self,
        candidate_id: str,
    ) -> dict[str, Any]:
        async with self._lock:
            candidate = self._candidates.get(candidate_id)
            audit = [a for a in self._restriction_audits if a["candidate_id"] == candidate_id]
        return {
            "no_restrictions": getattr(candidate, "metadata", {}).get("no_restrictions", False)
            if candidate else False,
            "cooldown_override_granted_at": getattr(candidate, "metadata", {}).get(
                "cooldown_override_granted_at"
            ) if candidate else None,
            "cooldown_override_expires_at": getattr(candidate, "metadata", {}).get(
                "cooldown_override_expires_at"
            ) if candidate else None,
            "audit_log": audit,
        }

    async def grant_cooldown_override(
        self,
        candidate_id: str,
        granted_by: str,
        expires_at: datetime,
        reason: str | None = None,
    ) -> None:
        async with self._lock:
            candidate = self._candidates.get(candidate_id)
            if candidate is None:
                return
            meta = dict(candidate.metadata or {})
            meta["cooldown_override_granted_at"] = datetime.now(UTC).isoformat()
            meta["cooldown_override_expires_at"] = expires_at.isoformat()
            self._candidates[candidate_id] = replace(candidate, metadata=meta)
            self._restriction_audits.append({
                "id": str(len(self._restriction_audits) + 1),
                "candidate_id": candidate_id,
                "action": "grant_override",
                "granted_by": granted_by,
                "expires_at": expires_at.isoformat(),
                "reason": reason,
                "created_at": datetime.now(UTC).isoformat(),
            })

    async def revoke_cooldown_override(
        self,
        candidate_id: str,
        revoked_by: str,
    ) -> None:
        async with self._lock:
            candidate = self._candidates.get(candidate_id)
            if candidate is None:
                return
            meta = dict(candidate.metadata or {})
            meta.pop("cooldown_override_granted_at", None)
            meta.pop("cooldown_override_expires_at", None)
            self._candidates[candidate_id] = replace(candidate, metadata=meta)
            self._restriction_audits.append({
                "id": str(len(self._restriction_audits) + 1),
                "candidate_id": candidate_id,
                "action": "revoke_override",
                "granted_by": revoked_by,
                "expires_at": None,
                "reason": None,
                "created_at": datetime.now(UTC).isoformat(),
            })

    async def set_no_restrictions(
        self,
        candidate_id: str,
        enabled: bool,
        updated_by: str,
    ) -> None:
        async with self._lock:
            candidate = self._candidates.get(candidate_id)
            if candidate is None:
                return
            meta = dict(candidate.metadata or {})
            meta["no_restrictions"] = enabled
            self._candidates[candidate_id] = replace(candidate, metadata=meta)
            action = "set_no_restrictions" if enabled else "unset_no_restrictions"
            self._restriction_audits.append({
                "id": str(len(self._restriction_audits) + 1),
                "candidate_id": candidate_id,
                "action": action,
                "granted_by": updated_by,
                "expires_at": None,
                "reason": None,
                "created_at": datetime.now(UTC).isoformat(),
            })

    # ─── Monitoring: admin settings ──────────────────────────────────

    async def get_admin_settings(self) -> dict[str, Any]:
        async with self._lock:
            return dict(self._admin_settings)

    async def save_admin_settings(
        self,
        cooldown_days: int,
        updated_by: str | None = None,
    ) -> None:
        async with self._lock:
            self._admin_settings = {
                "cooldown_days": cooldown_days,
                "updated_at": datetime.now(UTC).isoformat(),
                "updated_by": updated_by,
            }

    # ─── Monitoring: eligibility ──────────────────────────────────────

    async def check_assessment_eligibility(
        self,
        candidate_id: str,
    ) -> dict[str, Any]:
        async with self._lock:
            candidate = self._candidates.get(candidate_id)
            cooldown_days: int = self._admin_settings["cooldown_days"]
            now = datetime.now(UTC)

            if candidate is not None:
                meta = candidate.metadata or {}
                if meta.get("no_restrictions"):
                    return {
                        "eligible": True,
                        "reason": None,
                        "next_eligible_at": None,
                        "cooldown_days": cooldown_days,
                    }
                override_expires_raw = meta.get("cooldown_override_expires_at")
                if override_expires_raw:
                    try:
                        override_expires = datetime.fromisoformat(str(override_expires_raw))
                        if override_expires.tzinfo is None:
                            override_expires = override_expires.replace(tzinfo=UTC)
                        if override_expires > now:
                            return {
                                "eligible": True,
                                "reason": None,
                                "next_eligible_at": None,
                                "cooldown_days": cooldown_days,
                            }
                    except ValueError:
                        pass

            from datetime import timedelta
            cutoff = now - timedelta(days=cooldown_days)
            blocking_session: AssessmentSession | None = None
            for s in self._sessions.values():
                if s.candidate_id != candidate_id:
                    continue
                status_val = s.status.value if isinstance(s.status, AssessmentStatus) else s.status
                if status_val not in _COUNTABLE_STATUSES:
                    continue
                if s.ended_at is None:
                    continue
                ended = s.ended_at
                if ended.tzinfo is None:
                    ended = ended.replace(tzinfo=UTC)
                if ended >= cutoff:
                    if blocking_session is None or ended > (
                        blocking_session.ended_at or datetime.min.replace(tzinfo=UTC)
                    ):
                        blocking_session = s

            if blocking_session is None:
                return {
                    "eligible": True,
                    "reason": None,
                    "next_eligible_at": None,
                    "cooldown_days": cooldown_days,
                }

            from datetime import timedelta
            ended_at = blocking_session.ended_at
            if ended_at is not None and ended_at.tzinfo is None:
                ended_at = ended_at.replace(tzinfo=UTC)
            next_eligible = (ended_at or now) + timedelta(days=cooldown_days)
            return {
                "eligible": False,
                "reason": f"A completed assessment exists within the {cooldown_days}-day cooldown period.",
                "next_eligible_at": next_eligible.isoformat(),
                "cooldown_days": cooldown_days,
            }


__all__ = ["InMemoryPersistence"]
