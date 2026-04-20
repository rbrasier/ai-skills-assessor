"""Unit tests for ``CallManager`` as an ``ICallLifecycleListener``.

These verify the status transitions a live Daily event handler will
drive in Phase 3 Revision 1. They use ``InMemoryPersistence`` + the
fake transport from ``conftest.py`` so no network or Pipecat is
required.
"""

from __future__ import annotations

import pytest

from src.adapters.in_memory_persistence import InMemoryPersistence
from src.domain.models.assessment import AssessmentSession, AssessmentStatus
from src.domain.services.call_manager import CallManager

pytestmark = pytest.mark.asyncio


async def _seed_session(
    persistence: InMemoryPersistence,
    *,
    status: AssessmentStatus = AssessmentStatus.DIALLING,
) -> AssessmentSession:
    await persistence.get_or_create_candidate(
        email="kai@example.com",
        first_name="Kai",
        last_name="Tester",
        employee_id="KAI-1",
    )
    session = AssessmentSession(
        id="sess-1",
        candidate_id="kai@example.com",
        phone_number="+447700900118",
        status=status,
    )
    return await persistence.create_session(session)


async def test_on_call_connected_transitions_dialling_to_in_progress(
    persistence: InMemoryPersistence,
    call_manager: CallManager,
) -> None:
    session = await _seed_session(persistence)
    await call_manager.on_call_connected(session.id)

    updated = await persistence.get_session(session.id)
    assert updated is not None
    assert updated.status == AssessmentStatus.IN_PROGRESS
    assert updated.started_at is not None


async def test_on_call_ended_transitions_to_completed(
    persistence: InMemoryPersistence,
    call_manager: CallManager,
) -> None:
    session = await _seed_session(persistence, status=AssessmentStatus.IN_PROGRESS)
    await call_manager.on_call_ended(session.id)

    updated = await persistence.get_session(session.id)
    assert updated is not None
    assert updated.status == AssessmentStatus.COMPLETED
    assert updated.ended_at is not None


async def test_on_call_ended_is_idempotent_against_terminal_statuses(
    persistence: InMemoryPersistence,
    call_manager: CallManager,
) -> None:
    session = await _seed_session(persistence, status=AssessmentStatus.CANCELLED)
    await call_manager.on_call_ended(session.id)

    updated = await persistence.get_session(session.id)
    assert updated is not None
    # Cancelled must not be overwritten to completed.
    assert updated.status == AssessmentStatus.CANCELLED


async def test_on_call_failed_records_reason_and_ends(
    persistence: InMemoryPersistence,
    call_manager: CallManager,
) -> None:
    session = await _seed_session(persistence)
    await call_manager.on_call_failed(
        session.id, reason="dialout_error: busy"
    )

    updated = await persistence.get_session(session.id)
    assert updated is not None
    assert updated.status == AssessmentStatus.FAILED
    assert updated.ended_at is not None
    assert updated.metadata.get("failureReason") == "dialout_error: busy"
