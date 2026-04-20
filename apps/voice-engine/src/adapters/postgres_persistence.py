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
from datetime import UTC, datetime
from typing import Any

from src.domain.models.assessment import (
    AssessmentSession,
    AssessmentStatus,
    Candidate,
)
from src.domain.models.transcript import Transcript
from src.domain.ports.persistence import IPersistence

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
                datetime.now(UTC),
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
                    "dailyRoomUrl", "recordingUrl", "startedAt", "endedAt", "createdAt"
                ) VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8, $9, $10)
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
                session.started_at,
                session.ended_at,
                session.created_at or datetime.now(UTC),
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
            # Merge metadata JSONB server-side so callers don't race on
            # stale reads. ``$2::jsonb`` with ``||`` preserves existing keys
            # unless overridden.
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
                started_at,
                ended_at,
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

    async def save_transcript(self, transcript: Transcript) -> None:
        # Phase 2 does not generate transcripts. The schema will gain a
        # transcripts table in a later phase.
        return None


__all__ = ["PostgresPersistence"]
