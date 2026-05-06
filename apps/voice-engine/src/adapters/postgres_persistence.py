"""Postgres-backed ``IPersistence`` adapter.

Talks to the Prisma-managed tables (see
``packages/database/prisma/schema.prisma``) using ``asyncpg`` with raw
SQL. Prisma owns the schema + migrations; this adapter only reads and
writes rows.

The pool is created lazily so unit tests can instantiate the adapter
without requiring a live database.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from src.domain.models.assessment import (
    AssessmentSession,
    AssessmentStatus,
    Candidate,
)
from src.domain.ports.persistence import IPersistence


def _dashboard_skill_metrics(
    claims: list[dict[str, Any]],
    holistic: list[dict[str, Any]],
) -> tuple[int | None, list[str]]:
    """Derive max SFIA level and top skill codes for admin tables.

    Prefer holistic ``estimated_level`` when per-claim ``sfia_level`` is unset.
    """
    max_level: int | None = None
    top_codes: list[str] = []

    claim_levels: list[int] = []
    for c in claims:
        sl = c.get("sfia_level")
        if sl is not None and int(sl) > 0:
            claim_levels.append(int(sl))
    if claim_levels:
        max_level = max(claim_levels)

    hol_levels = [
        int(h["estimated_level"])
        for h in holistic
        if h.get("estimated_level") is not None
    ]
    if hol_levels:
        hol_max = max(hol_levels)
        max_level = hol_max if max_level is None else max(max_level, hol_max)

    seen: dict[str, float] = {}
    for c in claims:
        code = c.get("sfia_skill_code") or c.get("skill_code") or c.get("skillCode")
        if code:
            seen[code] = seen.get(code, 0.0) + float(c.get("confidence") or 0.0)

    for h in holistic:
        code = h.get("skill_code")
        if code:
            prom = float(h.get("prominence") or 0.0)
            seen[code] = seen.get(code, 0.0) + prom

    top_codes = [k for k, _ in sorted(seen.items(), key=lambda x: -x[1])][:5]
    return max_level, top_codes


def _to_naive(dt: datetime | None) -> datetime | None:
    """Convert timezone-aware datetime to naive (strip timezone info)."""
    if dt is None:
        return None
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt


try:  # ``asyncpg`` is part of the ``voice`` extras and may be absent in
    # CI's lean install. We import defensively so the module still loads
    # for static analysis / unit-test stubs.
    import asyncpg as _asyncpg_module
except ImportError:  # pragma: no cover — exercised in lean CI only
    _asyncpg_module = None

asyncpg: Any = _asyncpg_module


def _row_to_candidate(row: Any) -> Candidate:
    metadata = row["metadata"]
    if isinstance(metadata, str):
        metadata = json.loads(metadata)
    return Candidate(
        email=row["email"],
        first_name=row["firstName"],
        last_name=row["lastName"],
        metadata=metadata or {},
        created_at=row["createdAt"],
    )


_DEFAULT_COOLDOWN_DAYS = 90
_FOCUS_SUSPICIOUS_MAX_EVENTS = 5
_FOCUS_SUSPICIOUS_MAX_AWAY_MS = 60_000
_COUNTABLE_STATUSES = ("completed", "processed", "user_ended")


def _row_to_session(row: Any) -> AssessmentSession:
    metadata = row["metadata"]
    if isinstance(metadata, str):
        metadata = json.loads(metadata)
    error_details = row.get("error_details")
    if isinstance(error_details, str):
        error_details = json.loads(error_details)
    focus_events = row.get("focus_events_json")
    if isinstance(focus_events, str):
        focus_events = json.loads(focus_events)
    return AssessmentSession(
        id=row["id"],
        candidate_id=row["candidateId"],
        phone_number=row["phoneNumber"],
        status=AssessmentStatus(row["status"]),
        metadata=metadata or {},
        daily_room_url=row["dailyRoomUrl"],
        recording_url=row["recordingUrl"],
        started_at=row["startedAt"],
        ended_at=row["endedAt"],
        created_at=row["createdAt"],
        candidate_name=row.get("candidate_name"),
        termination_reason=row.get("termination_reason"),
        error_details=error_details,
        last_turn_saved_at=row.get("last_turn_saved_at"),
        focus_suspicious=bool(row.get("focus_suspicious", False)),
        total_focus_away_ms=int(row.get("total_focus_away_ms") or 0),
        focus_events_json=focus_events,
    )


class PostgresPersistence(IPersistence):
    def __init__(self, database_url: str) -> None:
        # Strip Prisma-specific query parameters (e.g. ?schema=public) that
        # asyncpg doesn't understand and will reject.
        if "?schema=" in database_url:
            database_url = database_url.split("?schema=")[0]
        self._database_url = database_url
        self._pool: Any = None

    async def _get_pool(self) -> Any:
        if self._pool is None:
            if asyncpg is None:  # pragma: no cover
                raise RuntimeError(
                    "asyncpg is not installed; install voice-engine with "
                    "`pip install -e .[voice]` to use PostgresPersistence"
                )
            self._pool = await asyncpg.create_pool(self._database_url)
        return self._pool

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    # ─── Liveness ────────────────────────────────────────────────────

    async def ping(self) -> bool:
        """Run ``SELECT 1`` against the pool; swallow connection errors."""
        if asyncpg is None:  # pragma: no cover — lean CI
            return False
        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                result = await conn.fetchval("SELECT 1")
            return result == 1
        except Exception:  # pragma: no cover — exercised on real DB
            return False

    # ─── Candidate ───────────────────────────────────────────────────

    async def get_or_create_candidate(
        self,
        email: str,
        first_name: str,
        last_name: str,
        employee_id: str,
    ) -> Candidate:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT * FROM candidates WHERE "email" = $1',
                email,
            )
            if row is not None:
                return _row_to_candidate(row)

            metadata = {"employee_id": employee_id} if employee_id else {}
            row = await conn.fetchrow(
                """
                INSERT INTO candidates ("email", "firstName", "lastName", "metadata", "createdAt")
                VALUES ($1, $2, $3, $4::jsonb, $5)
                RETURNING *
                """,
                email,
                first_name,
                last_name,
                json.dumps(metadata),
                datetime.now(),
            )
            return _row_to_candidate(row)

    # ─── Session ─────────────────────────────────────────────────────

    async def create_session(self, session: AssessmentSession) -> AssessmentSession:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO assessment_sessions (
                    "id", "candidateId", "phoneNumber", "status", "metadata",
                    "dailyRoomUrl", "recordingUrl", "startedAt", "endedAt",
                    "createdAt", "candidate_name"
                ) VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8, $9, $10, $11)
                RETURNING *
                """,
                session.id,
                session.candidate_id,
                session.phone_number,
                session.status.value
                if isinstance(session.status, AssessmentStatus)
                else session.status,
                json.dumps(session.metadata or {}),
                session.daily_room_url,
                session.recording_url,
                _to_naive(session.started_at),
                _to_naive(session.ended_at),
                _to_naive(session.created_at) or datetime.now(),
                session.candidate_name,
            )
            return _row_to_session(row)

    async def save_session(self, session: AssessmentSession) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE assessment_sessions
                SET
                    "candidateId"   = $2,
                    "phoneNumber"   = $3,
                    "status"        = $4,
                    "metadata"      = $5::jsonb,
                    "dailyRoomUrl"  = $6,
                    "recordingUrl"  = $7,
                    "startedAt"     = $8,
                    "endedAt"       = $9
                WHERE "id" = $1
                """,
                session.id,
                session.candidate_id,
                session.phone_number,
                session.status.value
                if isinstance(session.status, AssessmentStatus)
                else session.status,
                json.dumps(session.metadata or {}),
                session.daily_room_url,
                session.recording_url,
                session.started_at,
                session.ended_at,
            )

    async def get_session(self, session_id: str) -> AssessmentSession | None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT * FROM assessment_sessions WHERE "id" = $1',
                session_id,
            )
            return _row_to_session(row) if row is not None else None

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
        pool = await self._get_pool()
        status_value = (
            status.value if isinstance(status, AssessmentStatus) else str(status)
        )

        async with pool.acquire() as conn:
            merge_json = json.dumps(metadata or {})
            row = await conn.fetchrow(
                """
                UPDATE assessment_sessions
                SET
                    "status"       = $2,
                    "metadata"     = "metadata" || $3::jsonb,
                    "startedAt"    = COALESCE($4, "startedAt"),
                    "endedAt"      = COALESCE($5, "endedAt"),
                    "dailyRoomUrl" = COALESCE($6, "dailyRoomUrl"),
                    "recordingUrl" = COALESCE($7, "recordingUrl")
                WHERE "id" = $1
                RETURNING *
                """,
                session_id,
                status_value,
                merge_json,
                _to_naive(started_at),
                _to_naive(ended_at),
                daily_room_url,
                recording_url,
            )
            return _row_to_session(row) if row is not None else None

    async def query_sessions(
        self,
        status: str | None = None,
        candidate_email: str | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AssessmentSession]:
        pool = await self._get_pool()
        clauses: list[str] = []
        args: list[Any] = []

        if status is not None:
            args.append(status)
            clauses.append(f'"status" = ${len(args)}')
        if candidate_email is not None:
            args.append(candidate_email)
            clauses.append(f'"candidateId" = ${len(args)}')
        if created_after is not None:
            args.append(created_after)
            clauses.append(f'"createdAt" >= ${len(args)}')
        if created_before is not None:
            args.append(created_before)
            clauses.append(f'"createdAt" <= ${len(args)}')

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        args.extend([limit, offset])
        sql = (
            "SELECT * FROM assessment_sessions "
            f"{where} "
            f'ORDER BY "createdAt" DESC '
            f"LIMIT ${len(args) - 1} OFFSET ${len(args)}"
        )

        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, *args)
            return [_row_to_session(r) for r in rows]

    # ─── Transcript ──────────────────────────────────────────────────

    async def save_transcript(
        self,
        session_id: str,
        transcript_json: dict[str, Any],
    ) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE assessment_sessions
                SET "transcript_json" = $2::jsonb
                WHERE "id" = $1
                """,
                session_id,
                json.dumps(transcript_json),
            )

    async def get_transcript(
        self,
        session_id: str,
    ) -> dict[str, Any] | None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT "transcript_json" FROM assessment_sessions WHERE "id" = $1',
                session_id,
            )
            if row is None:
                return None
            val = row["transcript_json"]
            if val is None:
                return None
            if isinstance(val, str):
                return json.loads(val)
            return val

    # ─── Report ──────────────────────────────────────────────────────

    _REPORT_COLS_COMPACT = """
        "id", "candidate_name", "claims_json", "holistic_assessment_json",
        "expert_review_token", "supervisor_review_token", "review_token",
        "report_status", "overall_confidence",
        "report_generated_at", "sme_reviewed_at", "expires_at",
        "expert_submitted_at", "expert_reviewer_name", "expert_reviewer_email",
        "supervisor_submitted_at", "supervisor_reviewer_name",
        "supervisor_reviewer_email", "reviews_completed_at"
    """

    _REPORT_COLS = """
        "id", "candidate_name", "transcript_json", "claims_json", "holistic_assessment_json",
        "expert_review_token", "supervisor_review_token", "review_token",
        "report_status", "overall_confidence",
        "report_generated_at", "sme_reviewed_at", "expires_at",
        "expert_submitted_at", "expert_reviewer_name", "expert_reviewer_email",
        "supervisor_submitted_at", "supervisor_reviewer_name",
        "supervisor_reviewer_email", "reviews_completed_at"
    """

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
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE assessment_sessions
                SET
                    "claims_json"                  = $2::jsonb,
                    "holistic_assessment_json"     = $3::jsonb,
                    "expert_review_token"          = $4,
                    "supervisor_review_token"      = $5,
                    "review_token"                 = $4,
                    "overall_confidence"           = $6,
                    "report_status"                = 'awaiting_expert',
                    "report_generated_at"          = $7,
                    "expires_at"                   = $8
                WHERE "id" = $1
                """,
                session_id,
                json.dumps(claims),
                json.dumps(holistic_assessment or []),
                expert_review_token,
                supervisor_review_token,
                overall_confidence,
                _to_naive(datetime.now(UTC)),
                _to_naive(expires_at),
            )

    async def get_report(
        self,
        session_id: str,
    ) -> dict[str, Any] | None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                SELECT {self._REPORT_COLS}
                FROM assessment_sessions
                WHERE "id" = $1
                  AND "report_status" IS NOT NULL
                """,
                session_id,
            )
            return _report_row_to_dict(row) if row is not None else None

    async def get_report_by_expert_token(
        self,
        expert_review_token: str,
    ) -> dict[str, Any] | None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                SELECT {self._REPORT_COLS_COMPACT}
                FROM assessment_sessions
                WHERE "expert_review_token" = $1
                """,
                expert_review_token,
            )
            return _report_row_to_dict(row) if row is not None else None

    async def get_report_by_supervisor_token(
        self,
        supervisor_review_token: str,
    ) -> dict[str, Any] | None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                SELECT {self._REPORT_COLS_COMPACT}
                FROM assessment_sessions
                WHERE "supervisor_review_token" = $1
                """,
                supervisor_review_token,
            )
            return _report_row_to_dict(row) if row is not None else None

    async def save_expert_review(
        self,
        expert_review_token: str,
        reviewer_full_name: str,
        reviewer_email: str,
        claims_patch: list[dict[str, Any]],
    ) -> dict[str, Any]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                SELECT {self._REPORT_COLS_COMPACT}
                FROM assessment_sessions
                WHERE "expert_review_token" = $1
                """,
                expert_review_token,
            )
            if row is None:
                raise ValueError(f"Expert token not found: {expert_review_token}")
            if row["expert_submitted_at"] is not None:
                raise RuntimeError("Expert review already submitted")

            session_id = row["id"]
            claims_json = row["claims_json"]
            if isinstance(claims_json, str):
                claims_json = json.loads(claims_json)

            patch_by_id = {p["id"]: p for p in claims_patch}
            updated_claims = []
            for claim in (claims_json or []):
                patch = patch_by_id.get(claim.get("id", ""))
                if patch:
                    claim = {**claim, "expert_level": patch["expert_level"]}
                updated_claims.append(claim)

            now = _to_naive(datetime.now(UTC))
            updated_row = await conn.fetchrow(
                """
                UPDATE assessment_sessions
                SET
                    "claims_json"           = $2::jsonb,
                    "expert_submitted_at"   = $3,
                    "expert_reviewer_name"  = $4,
                    "expert_reviewer_email" = $5,
                    "report_status"         = 'awaiting_supervisor'
                WHERE "id" = $1
                RETURNING "id", "report_status", "reviews_completed_at"
                """,
                session_id,
                json.dumps(updated_claims),
                now,
                reviewer_full_name,
                reviewer_email,
            )
            return {
                "session_id": session_id,
                "report_status": updated_row["report_status"],
                "reviews_completed_at": None,
                "claims": updated_claims,
            }

    async def save_supervisor_review(
        self,
        supervisor_review_token: str,
        reviewer_full_name: str,
        reviewer_email: str,
        claims_patch: list[dict[str, Any]],
    ) -> dict[str, Any]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                SELECT {self._REPORT_COLS_COMPACT}
                FROM assessment_sessions
                WHERE "supervisor_review_token" = $1
                """,
                supervisor_review_token,
            )
            if row is None:
                raise ValueError(f"Supervisor token not found: {supervisor_review_token}")
            if row["supervisor_submitted_at"] is not None:
                raise RuntimeError("Supervisor review already submitted")

            session_id = row["id"]
            expert_already_done = row["expert_submitted_at"] is not None
            claims_json = row["claims_json"]
            if isinstance(claims_json, str):
                claims_json = json.loads(claims_json)

            patch_by_id = {p["id"]: p for p in claims_patch}
            updated_claims = []
            for claim in (claims_json or []):
                patch = patch_by_id.get(claim.get("id", ""))
                if patch:
                    claim = {
                        **claim,
                        "supervisor_decision": patch["supervisor_decision"],
                        "supervisor_comment": patch["supervisor_comment"],
                    }
                updated_claims.append(claim)

            now = _to_naive(datetime.now(UTC))
            reviews_completed_at = now if expert_already_done else None
            new_status = "reviews_complete" if expert_already_done else "in_review"

            updated_row = await conn.fetchrow(
                """
                UPDATE assessment_sessions
                SET
                    "claims_json"                = $2::jsonb,
                    "supervisor_submitted_at"    = $3,
                    "supervisor_reviewer_name"   = $4,
                    "supervisor_reviewer_email"  = $5,
                    "report_status"              = $6,
                    "reviews_completed_at"       = $7
                WHERE "id" = $1
                RETURNING "id", "report_status", "reviews_completed_at"
                """,
                session_id,
                json.dumps(updated_claims),
                now,
                reviewer_full_name,
                reviewer_email,
                new_status,
                reviews_completed_at,
            )
            return {
                "session_id": session_id,
                "report_status": updated_row["report_status"],
                "reviews_completed_at": (
                    updated_row["reviews_completed_at"].isoformat()
                    if updated_row["reviews_completed_at"]
                    else None
                ),
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
        pool = await self._get_pool()
        clauses: list[str] = []
        args: list[Any] = []

        if status is not None:
            args.append(status)
            clauses.append(f'"status" = ${len(args)}')
        if candidate_email is not None:
            args.append(candidate_email)
            clauses.append(f'"candidateId" = ${len(args)}')
        if search is not None:
            args.append(f"%{search}%")
            n = len(args)
            clauses.append(
                f'("candidateId" ILIKE ${n} OR "candidate_name" ILIKE ${n})'
            )
        if created_after is not None:
            args.append(_to_naive(created_after))
            clauses.append(f'"createdAt" >= ${len(args)}')
        if created_before is not None:
            args.append(_to_naive(created_before))
            clauses.append(f'"createdAt" <= ${len(args)}')

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        args.extend([limit, offset])
        sql = f"""
            SELECT
                "id",
                "candidateId",
                "phoneNumber",
                "status",
                "createdAt",
                "startedAt",
                "endedAt",
                "candidate_name",
                "report_status",
                "expert_review_token",
                "supervisor_review_token",
                "claims_json",
                "holistic_assessment_json",
                "metadata",
                "overall_confidence",
                "termination_reason",
                "focus_suspicious",
                "total_focus_away_ms"
            FROM assessment_sessions
            {where}
            ORDER BY "createdAt" DESC
            LIMIT ${len(args) - 1} OFFSET ${len(args)}
        """

        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, *args)

        summaries = []
        for row in rows:
            started = row["startedAt"]
            ended = row["endedAt"]
            duration = 0.0
            if started and ended:
                duration = (
                    (ended - started).total_seconds()
                    if hasattr(ended - started, "total_seconds")
                    else 0.0
                )
            meta = row.get("metadata") or {}
            if isinstance(meta, str):
                meta = json.loads(meta)
            rec_dur = meta.get("recording_duration_seconds")
            if isinstance(rec_dur, (int, float)) and rec_dur > 0:
                duration = float(rec_dur)
            created = row["createdAt"]
            claims_raw = row["claims_json"]
            if isinstance(claims_raw, str):
                claims_raw = json.loads(claims_raw)
            claims = claims_raw or []

            holistic_raw = row.get("holistic_assessment_json")
            if isinstance(holistic_raw, str):
                holistic_raw = json.loads(holistic_raw)
            holistic = holistic_raw or []

            max_level, top_codes = _dashboard_skill_metrics(claims, holistic)

            summaries.append({
                "session_id": row["id"],
                "candidate_email": row["candidateId"],
                "phone_number": row["phoneNumber"] or "",
                "status": row["status"],
                "duration_seconds": duration,
                "created_at": created.isoformat() if created else "",
                "started_at": started.isoformat() if started else None,
                "ended_at": ended.isoformat() if ended else None,
                "candidate_name": row.get("candidate_name"),
                "report_status": row.get("report_status"),
                "expert_review_token": row.get("expert_review_token"),
                "supervisor_review_token": row.get("supervisor_review_token"),
                "max_sfia_level": max_level,
                "overall_confidence": row.get("overall_confidence"),
                "top_skill_codes": top_codes,
                "termination_reason": row.get("termination_reason"),
                "focus_suspicious": bool(row.get("focus_suspicious", False)),
                "total_focus_away_ms": int(row.get("total_focus_away_ms") or 0),
            })

        return summaries

    async def save_admin_claim_flags(
        self,
        session_id: str,
        claims_patch: list[dict[str, Any]],
        *,
        admin_actor: str,
    ) -> dict[str, Any]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT "id", "claims_json", "report_status"
                FROM assessment_sessions
                WHERE "id" = $1
                """,
                session_id,
            )
            if row is None:
                raise ValueError(f"Session not found: {session_id}")

            claims_json = row["claims_json"]
            if isinstance(claims_json, str):
                claims_json = json.loads(claims_json)

            patch_by_id = {p["id"]: p for p in claims_patch}
            now_iso = datetime.now(UTC).isoformat()
            updated_claims = []
            for claim in claims_json or []:
                patch = patch_by_id.get(claim.get("id", ""))
                if patch:
                    next_claim = {**claim}
                    if "admin_decision" in patch and patch["admin_decision"] is not None:
                        next_claim["admin_decision"] = patch["admin_decision"]
                    if "admin_comment" in patch:
                        next_claim["admin_comment"] = patch.get("admin_comment")
                    next_claim["admin_actor"] = admin_actor
                    next_claim["admin_updated_at"] = now_iso
                    claim = next_claim
                updated_claims.append(claim)

            await conn.execute(
                """
                UPDATE assessment_sessions
                SET "claims_json" = $2::jsonb
                WHERE "id" = $1
                """,
                session_id,
                json.dumps(updated_claims),
            )
            return {
                "session_id": session_id,
                "report_status": row["report_status"],
                "claims": updated_claims,
            }

    async def list_candidates_with_sessions(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT c.email,
                       c."firstName" AS first_name,
                       c."lastName" AS last_name,
                       (SELECT COUNT(*)::int FROM assessment_sessions s
                        WHERE s."candidateId" = c.email) AS total_calls,
                       (SELECT MAX("createdAt") FROM assessment_sessions s2
                        WHERE s2."candidateId" = c.email) AS last_call_at
                FROM candidates c
                WHERE EXISTS (
                    SELECT 1 FROM assessment_sessions s3
                    WHERE s3."candidateId" = c.email
                )
                ORDER BY last_call_at DESC NULLS LAST
                LIMIT $1 OFFSET $2
                """,
                limit,
                offset,
            )

        if not rows:
            return []

        emails = [r["email"] for r in rows]
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            sess_rows = await conn.fetch(
                """
                SELECT
                    "id",
                    "candidateId",
                    "phoneNumber",
                    "status",
                    "createdAt",
                    "startedAt",
                    "endedAt",
                    "candidate_name",
                    "report_status",
                    "expert_review_token",
                    "supervisor_review_token",
                    "claims_json",
                    "holistic_assessment_json",
                    "metadata",
                    "overall_confidence",
                    "termination_reason",
                    "focus_suspicious",
                    "total_focus_away_ms"
                FROM assessment_sessions
                WHERE "candidateId" = ANY($1::text[])
                ORDER BY "candidateId", "createdAt" DESC
                """,
                emails,
            )

        by_email: dict[str, list[dict[str, Any]]] = {e: [] for e in emails}
        for srow in sess_rows:
            started = srow["startedAt"]
            ended = srow["endedAt"]
            duration = 0.0
            if started and ended:
                duration = (
                    (ended - started).total_seconds()
                    if hasattr(ended - started, "total_seconds")
                    else 0.0
                )
            meta = srow.get("metadata") or {}
            if isinstance(meta, str):
                meta = json.loads(meta)
            rec_dur = meta.get("recording_duration_seconds")
            if isinstance(rec_dur, (int, float)) and rec_dur > 0:
                duration = float(rec_dur)

            claims_raw = srow["claims_json"]
            if isinstance(claims_raw, str):
                claims_raw = json.loads(claims_raw)
            claims = claims_raw or []
            holistic_raw = srow.get("holistic_assessment_json")
            if isinstance(holistic_raw, str):
                holistic_raw = json.loads(holistic_raw)
            holistic = holistic_raw or []
            max_level, top_codes = _dashboard_skill_metrics(claims, holistic)

            cid = srow["candidateId"]
            by_email.setdefault(cid, []).append({
                "session_id": srow["id"],
                "candidate_email": cid,
                "phone_number": srow["phoneNumber"] or "",
                "status": srow["status"],
                "duration_seconds": duration,
                "created_at": srow["createdAt"].isoformat() if srow["createdAt"] else "",
                "started_at": started.isoformat() if started else None,
                "ended_at": ended.isoformat() if ended else None,
                "candidate_name": srow.get("candidate_name"),
                "report_status": srow.get("report_status"),
                "expert_review_token": srow.get("expert_review_token"),
                "supervisor_review_token": srow.get("supervisor_review_token"),
                "max_sfia_level": max_level,
                "overall_confidence": srow.get("overall_confidence"),
                "top_skill_codes": top_codes,
                "termination_reason": srow.get("termination_reason"),
                "focus_suspicious": bool(srow.get("focus_suspicious", False)),
                "total_focus_away_ms": int(srow.get("total_focus_away_ms") or 0),
            })

        out: list[dict[str, Any]] = []
        for r in rows:
            email = r["email"]
            out.append({
                "email": email,
                "first_name": r["first_name"],
                "last_name": r["last_name"],
                "total_calls": int(r["total_calls"] or 0),
                "last_call_at": r["last_call_at"].isoformat() if r["last_call_at"] else None,
                "sessions": by_email.get(email, []),
            })
        return out

    async def list_frameworks(self) -> list[dict[str, Any]]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, type, version, name, rubric, is_active,
                       created_at, updated_at
                FROM frameworks
                ORDER BY type, version
                """
            )
        return [dict(r) for r in rows]

    async def upsert_framework(
        self,
        *,
        framework_id: str | None,
        type_: str,
        version: str,
        name: str,
        rubric: str,
        is_active: bool,
    ) -> dict[str, Any]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            if framework_id:
                row = await conn.fetchrow(
                    """
                    UPDATE frameworks
                    SET type = $2, version = $3, name = $4, rubric = $5, is_active = $6,
                        updated_at = now()
                    WHERE id = $1
                    RETURNING id, type, version, name, rubric, is_active
                    """,
                    framework_id,
                    type_,
                    version,
                    name,
                    rubric,
                    is_active,
                )
                if row is None:
                    raise ValueError(f"Framework not found: {framework_id}")
                return dict(row)

            row = await conn.fetchrow(
                """
                INSERT INTO frameworks (id, type, version, name, rubric, is_active)
                VALUES (gen_random_uuid(), $1, $2, $3, $4, $5)
                ON CONFLICT (type, version)
                DO UPDATE SET name = EXCLUDED.name, rubric = EXCLUDED.rubric,
                              is_active = EXCLUDED.is_active, updated_at = now()
                RETURNING id, type, version, name, rubric, is_active
                """,
                type_,
                version,
                name,
                rubric,
                is_active,
            )
            return dict(row)

    async def list_framework_skills(self, framework_id: str) -> list[dict[str, Any]]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT fs.id, fs.skill_code, fs.skill_name,
                       fs.category, fs.subcategory, fs.description, fs.guidance,
                       fs.created_at, fs.updated_at,
                       COALESCE(
                         json_agg(
                           json_build_object(
                             'id', fsl.id,
                             'level', fsl.level,
                             'content', fsl.content,
                             'created_at', fsl.created_at,
                             'has_embedding', (fsl.embedding IS NOT NULL)
                           ) ORDER BY fsl.level NULLS LAST
                         ) FILTER (WHERE fsl.id IS NOT NULL),
                         '[]'::json
                       ) AS levels
                FROM framework_skills fs
                LEFT JOIN framework_skill_levels fsl ON fsl.framework_skill_id = fs.id
                WHERE fs.framework_id = $1
                GROUP BY fs.id
                ORDER BY fs.skill_code
                """,
                framework_id,
            )
        result: list[dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            lv = d.get("levels")
            if isinstance(lv, str):
                lv = json.loads(lv)
            d["levels"] = lv or []
            result.append(d)
        return result

    async def upsert_framework_skill(
        self,
        *,
        framework_id: str,
        skill_id: str | None,
        skill_code: str,
        skill_name: str,
        category: str,
        subcategory: str | None,
        description: str,
        guidance: str | None,
    ) -> dict[str, Any]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            if skill_id:
                row = await conn.fetchrow(
                    """
                    UPDATE framework_skills
                    SET skill_code = $3, skill_name = $4, category = $5,
                        subcategory = $6, description = $7, guidance = $8,
                        updated_at = now()
                    WHERE id = $1 AND framework_id = $2
                    RETURNING id, skill_code, skill_name,
                              category, subcategory, description, guidance
                    """,
                    skill_id,
                    framework_id,
                    skill_code,
                    skill_name,
                    category,
                    subcategory,
                    description,
                    guidance,
                )
                if row is None:
                    raise ValueError("Skill not found or wrong framework")
                return dict(row)

            row = await conn.fetchrow(
                """
                INSERT INTO framework_skills
                    (id, framework_id, skill_code, skill_name, category, subcategory, description, guidance)
                VALUES (gen_random_uuid(), $1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (framework_id, skill_code)
                DO UPDATE SET
                    skill_name  = EXCLUDED.skill_name,
                    category    = EXCLUDED.category,
                    subcategory = EXCLUDED.subcategory,
                    description = EXCLUDED.description,
                    guidance    = EXCLUDED.guidance,
                    updated_at  = now()
                RETURNING id, skill_code, skill_name,
                          category, subcategory, description, guidance
                """,
                framework_id,
                skill_code,
                skill_name,
                category,
                subcategory,
                description,
                guidance,
            )
            return dict(row)

    async def upsert_framework_skill_level(
        self,
        *,
        framework_skill_id: str,
        level_id: str | None,
        level: int | None,
        content: str,
    ) -> dict[str, Any]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            if level_id:
                row = await conn.fetchrow(
                    """
                    UPDATE framework_skill_levels
                    SET level = $3, content = $4,
                        embedding = CASE WHEN content = $4 THEN embedding ELSE NULL END
                    WHERE id = $1 AND framework_skill_id = $2
                    RETURNING id, level, content, (embedding IS NOT NULL) AS has_embedding
                    """,
                    level_id,
                    framework_skill_id,
                    level,
                    content,
                )
                if row is None:
                    raise ValueError("Skill level not found")
                return dict(row)

            row = await conn.fetchrow(
                """
                INSERT INTO framework_skill_levels (id, framework_skill_id, level, content)
                VALUES (gen_random_uuid(), $1, $2, $3)
                ON CONFLICT (framework_skill_id, level)
                DO UPDATE SET
                    content   = EXCLUDED.content,
                    embedding = CASE WHEN framework_skill_levels.content = EXCLUDED.content
                                     THEN framework_skill_levels.embedding
                                     ELSE NULL END
                RETURNING id, level, content, (embedding IS NOT NULL) AS has_embedding
                """,
                framework_skill_id,
                level,
                content,
            )
            return dict(row)

    async def list_framework_attributes(self, framework_id: str) -> list[dict[str, Any]]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, attribute, level, description, created_at
                FROM framework_attributes
                WHERE framework_id = $1
                ORDER BY attribute, level
                """,
                framework_id,
            )
        return [dict(r) for r in rows]

    async def upsert_framework_attribute(
        self,
        *,
        framework_id: str,
        attribute_id: str | None,
        attribute: str,
        level: int,
        description: str,
    ) -> dict[str, Any]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            if attribute_id:
                row = await conn.fetchrow(
                    """
                    UPDATE framework_attributes
                    SET attribute = $3, level = $4, description = $5
                    WHERE id = $1 AND framework_id = $2
                    RETURNING id, attribute, level, description
                    """,
                    attribute_id,
                    framework_id,
                    attribute,
                    level,
                    description,
                )
                if row is None:
                    raise ValueError("Attribute row not found")
                return dict(row)

            row = await conn.fetchrow(
                """
                INSERT INTO framework_attributes (id, framework_id, attribute, level, description)
                VALUES (gen_random_uuid(), $1, $2, $3, $4)
                ON CONFLICT (framework_id, attribute, level)
                DO UPDATE SET description = EXCLUDED.description
                RETURNING id, attribute, level, description
                """,
                framework_id,
                attribute,
                level,
                description,
            )
            return dict(row)

    async def get_framework_sync_status(self, framework_id: str) -> dict[str, Any]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*)::int                       AS total,
                    COUNT(fsl.embedding)::int           AS embedded,
                    (COUNT(*) - COUNT(fsl.embedding))::int AS stale
                FROM framework_skill_levels fsl
                JOIN framework_skills fs ON fs.id = fsl.framework_skill_id
                WHERE fs.framework_id = $1
                """,
                framework_id,
            )
        return dict(row) if row else {"total": 0, "embedded": 0, "stale": 0}

    async def bulk_import_framework(
        self,
        *,
        type_: str,
        version: str,
        name: str,
        rubric: str,
        skills: list[dict[str, Any]],
        skill_levels: list[dict[str, Any]],
        attributes: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Upsert a complete framework in one operation.

        ``skills`` items: skill_code, skill_name, category, subcategory, description, guidance.
        ``skill_levels`` items: skill_code, level, content.
        ``attributes`` items: attribute, level, description.

        Returns summary counts.
        """
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            framework_row = await conn.fetchrow(
                """
                INSERT INTO frameworks (id, type, version, name, rubric, is_active)
                VALUES (gen_random_uuid(), $1, $2, $3, $4, true)
                ON CONFLICT (type, version)
                DO UPDATE SET name = EXCLUDED.name, rubric = EXCLUDED.rubric,
                              is_active = true, updated_at = now()
                RETURNING id
                """,
                type_,
                version,
                name,
                rubric,
            )
            framework_id: str = str(framework_row["id"])

            skill_id_map: dict[str, str] = {}
            for sk in skills:
                row = await conn.fetchrow(
                    """
                    INSERT INTO framework_skills
                        (id, framework_id, skill_code, skill_name, category,
                         subcategory, description, guidance)
                    VALUES (gen_random_uuid(), $1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT (framework_id, skill_code)
                    DO UPDATE SET
                        skill_name  = EXCLUDED.skill_name,
                        category    = EXCLUDED.category,
                        subcategory = EXCLUDED.subcategory,
                        description = EXCLUDED.description,
                        guidance    = EXCLUDED.guidance,
                        updated_at  = now()
                    RETURNING id, skill_code
                    """,
                    framework_id,
                    sk["skill_code"],
                    sk["skill_name"],
                    sk.get("category", "General"),
                    sk.get("subcategory"),
                    sk.get("description", ""),
                    sk.get("guidance"),
                )
                skill_id_map[str(row["skill_code"])] = str(row["id"])

            levels_upserted = 0
            levels_stale = 0
            for lv in skill_levels:
                skill_id = skill_id_map.get(lv["skill_code"])
                if not skill_id:
                    continue
                row = await conn.fetchrow(
                    """
                    INSERT INTO framework_skill_levels
                        (id, framework_skill_id, level, content)
                    VALUES (gen_random_uuid(), $1, $2, $3)
                    ON CONFLICT (framework_skill_id, level)
                    DO UPDATE SET
                        content   = EXCLUDED.content,
                        embedding = CASE WHEN framework_skill_levels.content = EXCLUDED.content
                                         THEN framework_skill_levels.embedding
                                         ELSE NULL END
                    RETURNING (embedding IS NULL) AS embedding_cleared
                    """,
                    skill_id,
                    lv["level"],
                    lv["content"],
                )
                levels_upserted += 1
                if row["embedding_cleared"]:
                    levels_stale += 1

            for attr in attributes:
                await conn.execute(
                    """
                    INSERT INTO framework_attributes
                        (id, framework_id, attribute, level, description)
                    VALUES (gen_random_uuid(), $1, $2, $3, $4)
                    ON CONFLICT (framework_id, attribute, level)
                    DO UPDATE SET description = EXCLUDED.description
                    """,
                    framework_id,
                    attr["attribute"],
                    attr["level"],
                    attr["description"],
                )

        return {
            "framework_id": framework_id,
            "skills_upserted": len(skill_id_map),
            "levels_upserted": levels_upserted,
            "levels_stale": levels_stale,
            "attributes_upserted": len(attributes),
        }

    # ─── Metadata ────────────────────────────────────────────────────

    async def merge_session_metadata(
        self,
        session_id: str,
        metadata: dict[str, Any],
    ) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE assessment_sessions
                SET "metadata" = "metadata" || $2::jsonb
                WHERE "id" = $1
                """,
                session_id,
                json.dumps(metadata),
            )

    # ─── Monitoring: focus events ────────────────────────────────────

    async def append_focus_event(
        self,
        session_id: str,
        event: dict[str, Any],
    ) -> None:
        pool = await self._get_pool()
        duration_ms = int(event.get("durationMs", 0))
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE assessment_sessions
                SET
                    "focus_events_json"  = COALESCE("focus_events_json", '[]'::jsonb)
                                           || $2::jsonb,
                    "total_focus_away_ms" = "total_focus_away_ms" + $3,
                    "focus_suspicious"   = CASE
                        WHEN "focus_suspicious" THEN TRUE
                        WHEN (jsonb_array_length(
                                COALESCE("focus_events_json", '[]'::jsonb)
                              ) + 1) >= $4 THEN TRUE
                        WHEN ("total_focus_away_ms" + $3) >= $5 THEN TRUE
                        ELSE FALSE
                    END
                WHERE "id" = $1
                """,
                session_id,
                json.dumps([event]),
                duration_ms,
                _FOCUS_SUSPICIOUS_MAX_EVENTS,
                _FOCUS_SUSPICIOUS_MAX_AWAY_MS,
            )

    # ─── Monitoring: progressive transcript ──────────────────────────

    async def save_transcript_turn(
        self,
        session_id: str,
        turn: dict[str, Any],
    ) -> None:
        pool = await self._get_pool()
        now = _to_naive(datetime.now(UTC))
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE assessment_sessions
                SET
                    "transcript_json" = jsonb_set(
                        COALESCE("transcript_json", '{"turns":[]}'::jsonb),
                        '{turns}',
                        COALESCE("transcript_json"->'turns', '[]'::jsonb) || $2::jsonb
                    ),
                    "last_turn_saved_at" = $3
                WHERE "id" = $1
                """,
                session_id,
                json.dumps([turn]),
                now,
            )

    # ─── Monitoring: structured termination ──────────────────────────

    async def set_termination(
        self,
        session_id: str,
        termination_reason: str,
        error_details: dict[str, Any] | None = None,
    ) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE assessment_sessions
                SET
                    "termination_reason" = $2,
                    "error_details"      = $3::jsonb
                WHERE "id" = $1
                """,
                session_id,
                termination_reason,
                json.dumps(error_details) if error_details is not None else "null",
            )

    # ─── Monitoring: candidate restrictions ──────────────────────────

    async def get_candidate_restrictions(
        self,
        candidate_id: str,
    ) -> dict[str, Any]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT "no_restrictions",
                       "cooldown_override_granted_at",
                       "cooldown_override_expires_at"
                FROM candidates WHERE "email" = $1
                """,
                candidate_id,
            )
            audit_rows = await conn.fetch(
                """
                SELECT "id", "action", "grantedBy", "expiresAt", "reason", "createdAt"
                FROM candidate_restriction_audit
                WHERE "candidateId" = $1
                ORDER BY "createdAt" DESC
                """,
                candidate_id,
            )

        if row is None:
            return {
                "no_restrictions": False,
                "cooldown_override_granted_at": None,
                "cooldown_override_expires_at": None,
                "audit_log": [],
            }

        def _iso(v: Any) -> str | None:
            if v is None:
                return None
            return v.isoformat() if isinstance(v, datetime) else str(v)

        audit = [
            {
                "id": str(r["id"]),
                "action": r["action"],
                "granted_by": r["grantedBy"],
                "expires_at": _iso(r["expiresAt"]),
                "reason": r["reason"],
                "created_at": _iso(r["createdAt"]),
            }
            for r in audit_rows
        ]
        return {
            "no_restrictions": bool(row["no_restrictions"]),
            "cooldown_override_granted_at": _iso(row["cooldown_override_granted_at"]),
            "cooldown_override_expires_at": _iso(row["cooldown_override_expires_at"]),
            "audit_log": audit,
        }

    async def grant_cooldown_override(
        self,
        candidate_id: str,
        granted_by: str,
        expires_at: datetime,
        reason: str | None = None,
    ) -> None:
        pool = await self._get_pool()
        now = _to_naive(datetime.now(UTC))
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE candidates
                SET "cooldown_override_granted_at" = $2,
                    "cooldown_override_expires_at"  = $3
                WHERE "email" = $1
                """,
                candidate_id,
                now,
                _to_naive(expires_at),
            )
            await conn.execute(
                """
                INSERT INTO candidate_restriction_audit
                    ("id", "candidateId", "action", "grantedBy", "expiresAt", "reason", "createdAt")
                VALUES (gen_random_uuid()::text, $1, 'grant_override', $2, $3, $4, $5)
                """,
                candidate_id,
                granted_by,
                _to_naive(expires_at),
                reason,
                now,
            )

    async def revoke_cooldown_override(
        self,
        candidate_id: str,
        revoked_by: str,
    ) -> None:
        pool = await self._get_pool()
        now = _to_naive(datetime.now(UTC))
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE candidates
                SET "cooldown_override_granted_at" = NULL,
                    "cooldown_override_expires_at"  = NULL
                WHERE "email" = $1
                """,
                candidate_id,
            )
            await conn.execute(
                """
                INSERT INTO candidate_restriction_audit
                    ("id", "candidateId", "action", "grantedBy", "expiresAt", "reason", "createdAt")
                VALUES (gen_random_uuid()::text, $1, 'revoke_override', $2, NULL, NULL, $3)
                """,
                candidate_id,
                revoked_by,
                now,
            )

    async def set_no_restrictions(
        self,
        candidate_id: str,
        enabled: bool,
        updated_by: str,
    ) -> None:
        pool = await self._get_pool()
        now = _to_naive(datetime.now(UTC))
        action = "set_no_restrictions" if enabled else "unset_no_restrictions"
        async with pool.acquire() as conn:
            await conn.execute(
                'UPDATE candidates SET "no_restrictions" = $2 WHERE "email" = $1',
                candidate_id,
                enabled,
            )
            await conn.execute(
                """
                INSERT INTO candidate_restriction_audit
                    ("id", "candidateId", "action", "grantedBy", "expiresAt", "reason", "createdAt")
                VALUES (gen_random_uuid()::text, $1, $2, $3, NULL, NULL, $4)
                """,
                candidate_id,
                action,
                updated_by,
                now,
            )

    # ─── Monitoring: admin settings ──────────────────────────────────

    async def get_admin_settings(self) -> dict[str, Any]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM admin_settings WHERE id = 'default'")
        if row is None:
            return {
                "cooldown_days": _DEFAULT_COOLDOWN_DAYS,
                "updated_at": None,
                "updated_by": None,
            }
        return {
            "cooldown_days": row["cooldownDays"],
            "updated_at": row["updatedAt"].isoformat() if row["updatedAt"] else None,
            "updated_by": row["updatedBy"],
        }

    async def save_admin_settings(
        self,
        cooldown_days: int,
        updated_by: str | None = None,
    ) -> None:
        pool = await self._get_pool()
        now = _to_naive(datetime.now(UTC))
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO admin_settings ("id", "cooldownDays", "updatedAt", "updatedBy")
                VALUES ('default', $1, $2, $3)
                ON CONFLICT ("id") DO UPDATE
                    SET "cooldownDays" = EXCLUDED."cooldownDays",
                        "updatedAt"    = EXCLUDED."updatedAt",
                        "updatedBy"    = EXCLUDED."updatedBy"
                """,
                cooldown_days,
                now,
                updated_by,
            )

    # ─── Monitoring: eligibility ──────────────────────────────────────

    async def check_assessment_eligibility(
        self,
        candidate_id: str,
    ) -> dict[str, Any]:

        pool = await self._get_pool()
        settings = await self.get_admin_settings()
        cooldown_days: int = settings["cooldown_days"]
        now = datetime.now(UTC)
        cutoff = _to_naive(now - timedelta(days=cooldown_days))

        async with pool.acquire() as conn:
            candidate_row = await conn.fetchrow(
                """
                SELECT "no_restrictions",
                       "cooldown_override_granted_at",
                       "cooldown_override_expires_at"
                FROM candidates WHERE "email" = $1
                """,
                candidate_id,
            )

            if candidate_row is not None:
                if candidate_row["no_restrictions"]:
                    return {
                        "eligible": True,
                        "reason": None,
                        "next_eligible_at": None,
                        "cooldown_days": cooldown_days,
                    }
                override_expires = candidate_row["cooldown_override_expires_at"]
                if override_expires is not None:
                    oe = override_expires.replace(tzinfo=UTC) if override_expires.tzinfo is None else override_expires
                    if oe > now:
                        return {
                            "eligible": True,
                            "reason": None,
                            "next_eligible_at": None,
                            "cooldown_days": cooldown_days,
                        }

            blocking = await conn.fetchrow(
                """
                SELECT "id", "endedAt"
                FROM assessment_sessions
                WHERE "candidateId" = $1
                  AND "status" = ANY($2::text[])
                  AND "endedAt" >= $3
                ORDER BY "endedAt" DESC
                LIMIT 1
                """,
                candidate_id,
                list(_COUNTABLE_STATUSES),
                cutoff,
            )

        if blocking is None:
            return {
                "eligible": True,
                "reason": None,
                "next_eligible_at": None,
                "cooldown_days": cooldown_days,
            }

        ended_at = blocking["endedAt"]
        if ended_at.tzinfo is None:
            ended_at = ended_at.replace(tzinfo=UTC)
        next_eligible = ended_at + timedelta(days=cooldown_days)
        return {
            "eligible": False,
            "reason": f"A completed assessment exists within the {cooldown_days}-day cooldown period.",
            "next_eligible_at": next_eligible.isoformat(),
            "cooldown_days": cooldown_days,
        }


def _report_row_to_dict(row: Any) -> dict[str, Any]:
    claims_json = row["claims_json"]
    if isinstance(claims_json, str):
        claims_json = json.loads(claims_json)

    holistic_json = row.get("holistic_assessment_json")
    if isinstance(holistic_json, str):
        holistic_json = json.loads(holistic_json)

    transcript_json = row.get("transcript_json")
    if isinstance(transcript_json, str):
        transcript_json = json.loads(transcript_json)

    def _iso(val: Any) -> str | None:
        if val is None:
            return None
        if isinstance(val, datetime):
            return val.isoformat()
        return str(val)

    return {
        "session_id": row["id"],
        "candidate_name": row.get("candidate_name"),
        "transcript_json": transcript_json,
        "claims_json": claims_json or [],
        "holistic_assessment_json": holistic_json or [],
        "expert_review_token": row.get("expert_review_token"),
        "supervisor_review_token": row.get("supervisor_review_token"),
        "review_token": row.get("review_token"),
        "report_status": row["report_status"],
        "overall_confidence": row.get("overall_confidence"),
        "report_generated_at": _iso(row.get("report_generated_at")),
        "sme_reviewed_at": _iso(row.get("sme_reviewed_at")),
        "expires_at": _iso(row.get("expires_at")),
        "expert_submitted_at": _iso(row.get("expert_submitted_at")),
        "expert_reviewer_name": row.get("expert_reviewer_name"),
        "expert_reviewer_email": row.get("expert_reviewer_email"),
        "supervisor_submitted_at": _iso(row.get("supervisor_submitted_at")),
        "supervisor_reviewer_name": row.get("supervisor_reviewer_name"),
        "supervisor_reviewer_email": row.get("supervisor_reviewer_email"),
        "reviews_completed_at": _iso(row.get("reviews_completed_at")),
    }


__all__ = ["PostgresPersistence"]
