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
from src.domain.ports.call_lifecycle_listener import ICallLifecycleListener
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


class CallManager(ICallLifecycleListener):
    def __init__(
        self,
        persistence: IPersistence,
        voice_transport: IVoiceTransport,
        *,
        region: str = "ap-southeast-1",
    ) -> None:
        self._persistence = persistence
        self._voice_transport = voice_transport
        self._region = region
        # Background dial tasks — kept around so tests can ``await`` them
        # deterministically and so the event loop holds a reference.
        self._tasks: set[asyncio.Task[None]] = set()
        # Live connections keyed by session_id — used by cancel_call to hangup.
        self._connections: dict[str, Any] = {}

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
        dialing_method: str | None = None,
    ) -> AssessmentSession:
        """Create a pending session and fire off an async dial.

        Returns the freshly-created session (status ``pending``). The
        actual dial runs in a background task so the HTTP caller gets
        an immediate ``session_id`` for status polling.

        Raises :class:`InvalidPhoneNumberError` if the number cannot be
        normalised, and :class:`CandidateNotFoundError` if the email
        does not match an existing candidate.
        """

        # For browser dialing, skip phone normalization
        if dialing_method == "browser":
            normalised = ""
        else:
            normalised = normalise_phone_number(phone_number)

        candidate = await self._persistence.get_or_create_candidate(
            email=candidate_email,
            first_name="",
            last_name="",
            employee_id="",
        )
        if candidate is None:  # pragma: no cover — defensive
            raise CandidateNotFoundError(candidate_email)

        full_name = f"{candidate.first_name} {candidate.last_name}".strip() or None
        session = AssessmentSession(
            id=str(uuid4()),
            candidate_id=candidate.email,
            phone_number=normalised,
            status=AssessmentStatus.PENDING,
            metadata={"dialing_method": dialing_method or "pstn"},
            created_at=datetime.now(UTC),
            candidate_name=full_name,
        )
        created = await self._persistence.create_session(session)

        task = asyncio.create_task(self._place_call(created.id, normalised, dialing_method))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

        return created

    async def _place_call(
        self, session_id: str, phone_number: str, dialing_method: str | None = None
    ) -> None:
        """Background worker — dial the candidate and update status.

        After ``dial`` returns, ``in_progress`` / ``completed`` /
        ``failed`` transitions are driven by the transport's own Daily
        event handlers via the :class:`ICallLifecycleListener`
        interface (this class). See ``DailyVoiceTransport`` for the
        event → listener wiring.
        """

        try:
            config = CallConfig(
                session_id=session_id,
                phone_number=phone_number,
                candidate_id=session_id,
                region=self._region,
            )
            connection = await self._voice_transport.dial(config)

            self._connections[session_id] = connection
            if connection.browser_join_url is not None:
                call_meta = {
                    "dialingMethod": "browser",
                    "browserJoinUrl": connection.browser_join_url,
                    "livekitRoomName": connection.livekit_room_name,
                    "livekitParticipantToken": connection.livekit_participant_token,
                    "livekitUrl": connection.room_url,
                }
            else:
                call_meta = {"dialingMethod": "daily"}
            await self._persistence.update_session_status(
                session_id,
                AssessmentStatus.DIALLING,
                daily_room_url=connection.room_url,
                started_at=datetime.now(UTC),
                metadata=call_meta,
            )
        except Exception as exc:
            logger.exception("CallManager._place_call failed for %s", session_id)
            await self._persistence.update_session_status(
                session_id,
                AssessmentStatus.FAILED,
                metadata={"failureReason": str(exc)},
                ended_at=datetime.now(UTC),
            )

    # ─── ICallLifecycleListener ──────────────────────────────────────

    async def on_call_connected(self, session_id: str) -> None:
        """Candidate picked up; the Pipecat pipeline is live."""
        logger.info("CallManager.on_call_connected session_id=%s", session_id)
        try:
            await self._persistence.update_session_status(
                session_id,
                AssessmentStatus.IN_PROGRESS,
                started_at=datetime.now(UTC),
            )
        except Exception:  # pragma: no cover — defensive, listener must not crash pipeline
            logger.exception(
                "on_call_connected: persistence update failed for %s",
                session_id,
            )

    async def on_call_ended(self, session_id: str) -> None:
        """Normal hangup — bot finished its script or candidate left."""
        logger.info("CallManager.on_call_ended session_id=%s", session_id)
        try:
            session = await self._persistence.get_session(session_id)
            if session is not None and session.status in (
                AssessmentStatus.FAILED,
                AssessmentStatus.CANCELLED,
                AssessmentStatus.COMPLETED,
            ):
                return  # idempotent — honour terminal statuses
            await self._persistence.update_session_status(
                session_id,
                AssessmentStatus.COMPLETED,
                ended_at=datetime.now(UTC),
            )
        except Exception:  # pragma: no cover
            logger.exception(
                "on_call_ended: persistence update failed for %s",
                session_id,
            )

    async def on_call_failed(self, session_id: str, *, reason: str) -> None:
        logger.warning(
            "CallManager.on_call_failed session_id=%s reason=%s",
            session_id,
            reason,
        )
        try:
            await self._persistence.update_session_status(
                session_id,
                AssessmentStatus.FAILED,
                metadata={"failureReason": reason},
                ended_at=datetime.now(UTC),
            )
        except Exception:  # pragma: no cover
            logger.exception(
                "on_call_failed: persistence update failed for %s",
                session_id,
            )

    # ─── Status polling (Step 02) ────────────────────────────────────

    async def get_call_status(self, session_id: str) -> dict[str, Any]:
        session = await self._persistence.get_session(session_id)
        if session is None:
            raise SessionNotFoundError(session_id)

        duration = await self._voice_transport.get_call_duration(session_id)
        meta = session.metadata or {}

        # Phase 4: transcript snippet — first 500 chars of assembled turns
        transcript_snippet: str | None = None
        transcript_data = meta.get("transcript_json")
        if transcript_data and isinstance(transcript_data, dict):
            turns = transcript_data.get("turns", [])
            if turns:
                lines = [
                    f"[{t.get('speaker','?')}/{t.get('phase','?')}] {t.get('text','')}"
                    for t in turns
                ]
                transcript_snippet = "\n".join(lines)[:500]

        # Phase 4: LiveKit recording URL — stored on session or fetched from egress API
        livekit_recording_url: str | None = session.recording_url
        if livekit_recording_url is None:
            try:
                livekit_recording_url = await self._voice_transport.get_recording_url(session_id)
            except Exception:
                pass

        return {
            "session_id": session.id,
            "status": session.status.value
            if isinstance(session.status, AssessmentStatus)
            else session.status,
            "duration_seconds": duration,
            "started_at": session.started_at.isoformat() if session.started_at else None,
            "ended_at": session.ended_at.isoformat() if session.ended_at else None,
            "failure_reason": session.metadata.get("failureReason") if session.metadata else None,
            "dialing_method": meta.get("dialingMethod", "daily"),
            "browser_join_url": meta.get("browserJoinUrl"),
            "livekit_room_name": meta.get("livekitRoomName"),
            "livekit_participant_token": meta.get("livekitParticipantToken"),
            "livekit_url": meta.get("livekitUrl"),
            "transcript_snippet": transcript_snippet,
            "livekit_recording_url": livekit_recording_url,
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

        # Hang up the bot so it leaves the LiveKit room (or ends the Daily call).
        # Without this the browser stays connected and the mic indicator stays on.
        connection = self._connections.pop(session_id, None)
        if connection is not None:
            try:
                await self._voice_transport.hangup(connection)
                logger.info("cancel_call: hung up transport for session %s", session_id)
            except Exception:
                logger.exception("cancel_call: hangup failed for session %s", session_id)

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
        # Filter to pending tasks in the current loop to avoid event loop mismatch
        pending = [t for t in self._tasks if not t.done()]
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)


__all__ = [
    "CallManager",
    "CallManagerError",
    "CandidateNotFoundError",
    "InvalidPhoneNumberError",
    "SessionNotFoundError",
]
