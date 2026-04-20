"""``CallManager`` — orchestrates candidate self-service assessment calls.

Phase 2 boundary: domain service composes persistence + voice-transport
ports to create a session, kick off an asynchronous dial, and expose a
status polling entry point for the candidate UI.

No platform dependencies: ``CallManager`` accepts ``IPersistence`` and
``IVoiceTransport`` via constructor injection, which satisfies ADR-001.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from src.domain.models.assessment import (
    AssessmentSession,
    AssessmentStatus,
    CallConfig,
    Candidate,
)
from src.domain.ports.persistence import IPersistence
from src.domain.ports.voice_transport import IVoiceTransport
from src.domain.utils.phone import InvalidPhoneNumberError, normalise_phone_number

logger = logging.getLogger(__name__)


class CallManagerError(Exception):
    """Base class for ``CallManager`` failures surfaced to callers."""


class CandidateNotFoundError(CallManagerError):
    """Raised when a trigger references an unknown candidate email."""


class SessionNotFoundError(CallManagerError):
    """Raised when a status / cancel lookup hits an unknown session id."""


class CallManager:
    def __init__(
        self,
        persistence: IPersistence,
        voice_transport: IVoiceTransport,
        *,
        region: str = "ap-southeast-2",
    ) -> None:
        self._persistence = persistence
        self._voice_transport = voice_transport
        self._region = region
        # Background dial tasks — kept around so tests can ``await`` them
        # deterministically and so the event loop holds a reference.
        self._tasks: set[asyncio.Task[None]] = set()

    # ─── Candidate intake (Step 01) ──────────────────────────────────

    async def get_or_create_candidate(
        self,
        email: str,
        first_name: str,
        last_name: str,
        employee_id: str,
    ) -> Candidate:
        return await self._persistence.get_or_create_candidate(
            email=email,
            first_name=first_name,
            last_name=last_name,
            employee_id=employee_id,
        )

    # ─── Trigger a call (Step 02 start) ──────────────────────────────

    async def trigger_call(
        self,
        candidate_email: str,
        phone_number: str,
    ) -> AssessmentSession:
        """Create a pending session and fire off an async dial.

        Returns the freshly-created session (status ``pending``). The
        actual dial runs in a background task so the HTTP caller gets
        an immediate ``session_id`` for status polling.

        Raises :class:`InvalidPhoneNumberError` if the number cannot be
        normalised, and :class:`CandidateNotFoundError` if the email
        does not match an existing candidate.
        """

        normalised = normalise_phone_number(phone_number)

        candidate = await self._persistence.get_or_create_candidate(
            email=candidate_email,
            first_name="",
            last_name="",
            employee_id="",
        )
        if candidate is None:  # pragma: no cover — defensive
            raise CandidateNotFoundError(candidate_email)

        session = AssessmentSession(
            id=str(uuid4()),
            candidate_id=candidate.email,
            phone_number=normalised,
            status=AssessmentStatus.PENDING,
            created_at=datetime.now(UTC),
        )
        created = await self._persistence.create_session(session)

        task = asyncio.create_task(self._place_call(created.id, normalised))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

        return created

    async def _place_call(self, session_id: str, phone_number: str) -> None:
        """Background worker — dial the candidate and update status."""

        try:
            await self._persistence.update_session_status(
                session_id,
                AssessmentStatus.DIALLING,
                started_at=datetime.now(UTC),
            )

            config = CallConfig(
                session_id=session_id,
                phone_number=phone_number,
                candidate_id=session_id,  # opaque correlation id for transport
                region=self._region,
            )
            connection = await self._voice_transport.dial(config)

            # The transport will (eventually) update the session via its
            # own event handlers. For the Phase 2 stub transport we
            # record the room URL immediately so the status endpoint
            # can expose it if needed.
            await self._persistence.update_session_status(
                session_id,
                AssessmentStatus.DIALLING,
                daily_room_url=connection.room_url,
            )
        except Exception as exc:  # pragma: no cover — adapter failures
            logger.exception("CallManager._place_call failed for %s", session_id)
            await self._persistence.update_session_status(
                session_id,
                AssessmentStatus.FAILED,
                metadata={"failureReason": str(exc)},
                ended_at=datetime.now(UTC),
            )

    # ─── Status polling (Step 02) ────────────────────────────────────

    async def get_call_status(self, session_id: str) -> dict[str, Any]:
        session = await self._persistence.get_session(session_id)
        if session is None:
            raise SessionNotFoundError(session_id)

        duration = await self._voice_transport.get_call_duration(session_id)

        return {
            "session_id": session.id,
            "status": session.status.value
            if isinstance(session.status, AssessmentStatus)
            else session.status,
            "duration_seconds": duration,
            "started_at": session.started_at.isoformat() if session.started_at else None,
            "ended_at": session.ended_at.isoformat() if session.ended_at else None,
            "failure_reason": session.metadata.get("failureReason") if session.metadata else None,
        }

    # ─── Candidate-initiated cancel ──────────────────────────────────

    async def cancel_call(self, session_id: str) -> AssessmentSession:
        session = await self._persistence.get_session(session_id)
        if session is None:
            raise SessionNotFoundError(session_id)

        updated = await self._persistence.update_session_status(
            session_id,
            AssessmentStatus.CANCELLED,
            metadata={"cancelledAt": datetime.now(UTC).isoformat()},
            ended_at=datetime.now(UTC),
        )
        return updated or session

    # ─── Admin listing ───────────────────────────────────────────────

    async def list_sessions(
        self,
        *,
        status: str | None = None,
        candidate_email: str | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        sessions = await self._persistence.query_sessions(
            status=status,
            candidate_email=candidate_email,
            created_after=created_after,
            created_before=created_before,
            limit=limit,
            offset=offset,
        )

        summaries: list[dict[str, Any]] = []
        for session in sessions:
            duration = await self._voice_transport.get_call_duration(session.id)
            summaries.append(
                {
                    "session_id": session.id,
                    "candidate_email": session.candidate_id,
                    "phone_number": session.phone_number,
                    "status": session.status.value
                    if isinstance(session.status, AssessmentStatus)
                    else session.status,
                    "duration_seconds": duration,
                    "created_at": session.created_at.isoformat()
                    if session.created_at
                    else "",
                    "started_at": session.started_at.isoformat()
                    if session.started_at
                    else None,
                    "ended_at": session.ended_at.isoformat()
                    if session.ended_at
                    else None,
                }
            )

        return summaries

    # ─── Lifecycle helpers ───────────────────────────────────────────

    async def drain(self) -> None:
        """Await all in-flight dial tasks. Useful for tests + shutdown."""

        if not self._tasks:
            return
        await asyncio.gather(*list(self._tasks), return_exceptions=True)


__all__ = [
    "CallManager",
    "CallManagerError",
    "CandidateNotFoundError",
    "InvalidPhoneNumberError",
    "SessionNotFoundError",
]
