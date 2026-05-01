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
from datetime import datetime, timezone
from typing import Any

from src.domain.models.assessment import (
    AssessmentSession,
    AssessmentStatus,
    Candidate,
)
from src.domain.models.transcript import Transcript
from src.domain.ports.persistence import IPersistence


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


def _row_to_session(row: Any) -> AssessmentSession:
    metadata = row["metadata"]
    if isinstance(metadata, str):
        metadata = json.loads(metadata)
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
    )


class PostgresPersistence(IPersistence):
    def __init__(self, database_url: str) -> None:
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

    _REPORT_COLS = """
        "id", "candidate_name", "claims_json",
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
    ) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE assessment_sessions
                SET
                    "claims_json"              = $2::jsonb,
                    "expert_review_token"      = $3,
                    "supervisor_review_token"  = $4,
                    "review_token"             = $3,
                    "overall_confidence"       = $5,
                    "report_status"            = 'awaiting_expert',
                    "report_generated_at"      = $6,
                    "expires_at"               = $7
                WHERE "id" = $1
                """,
                session_id,
                json.dumps(claims),
                expert_review_token,
                supervisor_review_token,
                overall_confidence,
                _to_naive(datetime.now(timezone.utc)),
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
                SELECT {self._REPORT_COLS}
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
                SELECT {self._REPORT_COLS}
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
                SELECT {self._REPORT_COLS}
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

            now = _to_naive(datetime.now(timezone.utc))
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
                SELECT {self._REPORT_COLS}
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

            now = _to_naive(datetime.now(timezone.utc))
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
                "overall_confidence"
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
            created = row["createdAt"]
            claims_raw = row["claims_json"]
            if isinstance(claims_raw, str):
                claims_raw = json.loads(claims_raw)
            claims = claims_raw or []

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
            })

        return summaries

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


def _report_row_to_dict(row: Any) -> dict[str, Any]:
    claims_json = row["claims_json"]
    if isinstance(claims_json, str):
        claims_json = json.loads(claims_json)

    def _iso(val: Any) -> str | None:
        if val is None:
            return None
        if isinstance(val, datetime):
            return val.isoformat()
        return str(val)

    return {
        "session_id": row["id"],
        "candidate_name": row.get("candidate_name"),
        "claims_json": claims_json or [],
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
