"""Unit tests for ``CallManager`` — Phase 2 domain orchestration."""

from __future__ import annotations

import pytest

from src.adapters.in_memory_persistence import InMemoryPersistence
from src.domain.models.assessment import AssessmentStatus
from src.domain.services.call_manager import CallManager, SessionNotFoundError
from src.domain.utils.phone import InvalidPhoneNumberError
from tests.conftest import _FakeVoiceTransport


async def test_get_or_create_candidate_is_idempotent() -> None:
    persistence = InMemoryPersistence()
    manager = CallManager(persistence=persistence, voice_transport=_FakeVoiceTransport())

    c1 = await manager.get_or_create_candidate(
        email="amara@helixrobotics.com",
        first_name="Amara",
        last_name="Okafor",
        employee_id="HLX-00481",
    )
    c2 = await manager.get_or_create_candidate(
        email="amara@helixrobotics.com",
        first_name="IGNORED",
        last_name="IGNORED",
        employee_id="IGNORED",
    )
    assert c1.email == c2.email
    assert c2.first_name == "Amara"
    assert c2.metadata["employee_id"] == "HLX-00481"


async def test_trigger_call_creates_pending_session_and_normalises_phone() -> None:
    persistence = InMemoryPersistence()
    transport = _FakeVoiceTransport()
    manager = CallManager(persistence=persistence, voice_transport=transport)

    await manager.get_or_create_candidate(
        email="amara@helixrobotics.com",
        first_name="Amara",
        last_name="Okafor",
        employee_id="HLX-00481",
    )

    session = await manager.trigger_call(
        candidate_email="amara@helixrobotics.com",
        phone_number="44 7700 900118",
    )
    assert session.status == AssessmentStatus.PENDING
    assert session.phone_number == "+447700900118"

    await manager.drain()

    stored = await persistence.get_session(session.id)
    assert stored is not None
    assert stored.status == AssessmentStatus.DIALLING
    assert stored.daily_room_url is not None
    assert transport.dialled[0].phone_number == "+447700900118"


async def test_trigger_call_rejects_invalid_phone() -> None:
    persistence = InMemoryPersistence()
    transport = _FakeVoiceTransport()
    manager = CallManager(persistence=persistence, voice_transport=transport)

    await manager.get_or_create_candidate(
        email="a@b.com", first_name="A", last_name="B", employee_id="E1"
    )

    with pytest.raises(InvalidPhoneNumberError):
        await manager.trigger_call(candidate_email="a@b.com", phone_number="abc")


async def test_get_call_status_returns_duration_from_transport() -> None:
    persistence = InMemoryPersistence()
    transport = _FakeVoiceTransport()
    manager = CallManager(persistence=persistence, voice_transport=transport)

    await manager.get_or_create_candidate(
        email="a@b.com", first_name="A", last_name="B", employee_id="E1"
    )
    session = await manager.trigger_call(
        candidate_email="a@b.com", phone_number="+61412345678"
    )
    await manager.drain()

    status = await manager.get_call_status(session.id)
    assert status["session_id"] == session.id
    assert status["duration_seconds"] == 1.25
    assert status["status"] in {"pending", "dialling"}


async def test_get_call_status_raises_for_unknown_session() -> None:
    manager = CallManager(
        persistence=InMemoryPersistence(),
        voice_transport=_FakeVoiceTransport(),
    )
    with pytest.raises(SessionNotFoundError):
        await manager.get_call_status("nope")


async def test_cancel_call_updates_status_and_metadata() -> None:
    persistence = InMemoryPersistence()
    manager = CallManager(persistence=persistence, voice_transport=_FakeVoiceTransport())

    await manager.get_or_create_candidate(
        email="a@b.com", first_name="A", last_name="B", employee_id="E1"
    )
    session = await manager.trigger_call(
        candidate_email="a@b.com", phone_number="+61412345678"
    )
    await manager.drain()

    cancelled = await manager.cancel_call(session.id)
    assert cancelled.status == AssessmentStatus.CANCELLED
    assert "cancelledAt" in cancelled.metadata


async def test_list_sessions_filters_by_email_and_status() -> None:
    persistence = InMemoryPersistence()
    manager = CallManager(persistence=persistence, voice_transport=_FakeVoiceTransport())

    for email in ("a@b.com", "c@d.com"):
        await manager.get_or_create_candidate(
            email=email, first_name="F", last_name="L", employee_id="E"
        )
        await manager.trigger_call(candidate_email=email, phone_number="+61412345678")
    await manager.drain()

    all_sessions = await manager.list_sessions()
    assert len(all_sessions) == 2

    by_email = await manager.list_sessions(candidate_email="a@b.com")
    assert len(by_email) == 1
    assert by_email[0]["candidate_email"] == "a@b.com"

    completed = await manager.list_sessions(status="completed")
    assert completed == []
