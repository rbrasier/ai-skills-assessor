"""End-to-end tests for the Phase 2 assessment API routes.

Exercises every route through the FastAPI ``TestClient`` backed by an
``InMemoryPersistence`` + fake transport. No Postgres, no Daily.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _create_candidate(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/assessment/candidate",
        json={
            "work_email": "amara@helixrobotics.com",
            "first_name": "Amara",
            "last_name": "Okafor",
            "employee_id": "HLX-00481",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_create_candidate_is_idempotent(client: TestClient) -> None:
    first = _create_candidate(client)
    second = _create_candidate(client)
    assert first == second
    assert first["candidate_id"] == "amara@helixrobotics.com"
    assert first["work_email"] == "amara@helixrobotics.com"


def test_create_candidate_rejects_invalid_email(client: TestClient) -> None:
    response = client.post(
        "/api/v1/assessment/candidate",
        json={
            "work_email": "not-an-email",
            "first_name": "A",
            "last_name": "B",
            "employee_id": "E1",
        },
    )
    assert response.status_code == 422


def test_trigger_creates_session_and_returns_pending(client: TestClient) -> None:
    _create_candidate(client)

    response = client.post(
        "/api/v1/assessment/trigger",
        json={
            "candidate_id": "amara@helixrobotics.com",
            "phone_number": "+44 7700 900118",
        },
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "pending"
    assert body["session_id"]


def test_trigger_rejects_bad_phone_number(client: TestClient) -> None:
    _create_candidate(client)
    response = client.post(
        "/api/v1/assessment/trigger",
        json={"candidate_id": "amara@helixrobotics.com", "phone_number": "abc"},
    )
    assert response.status_code == 400
    assert "Invalid form data" in response.json()["detail"]


def test_status_transitions_after_trigger(client: TestClient) -> None:
    _create_candidate(client)
    trigger = client.post(
        "/api/v1/assessment/trigger",
        json={
            "candidate_id": "amara@helixrobotics.com",
            "phone_number": "+44 7700 900118",
        },
    ).json()
    session_id = trigger["session_id"]

    # Drain the background dial task so the session reaches `dialling`.
    app = client.app
    import asyncio

    manager = app.state.call_manager  # type: ignore[attr-defined]
    asyncio.new_event_loop().run_until_complete(manager.drain())

    response = client.get(f"/api/v1/assessment/{session_id}/status")
    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == session_id
    assert body["status"] in {"pending", "dialling"}
    assert body["duration_seconds"] == 1.25


def test_status_404_for_unknown_session(client: TestClient) -> None:
    response = client.get("/api/v1/assessment/does-not-exist/status")
    assert response.status_code == 404


def test_cancel_transitions_to_cancelled(client: TestClient) -> None:
    _create_candidate(client)
    trigger = client.post(
        "/api/v1/assessment/trigger",
        json={
            "candidate_id": "amara@helixrobotics.com",
            "phone_number": "+44 7700 900118",
        },
    ).json()

    cancel = client.post(f"/api/v1/assessment/{trigger['session_id']}/cancel")
    assert cancel.status_code == 200, cancel.text
    assert cancel.json()["status"] == "cancelled"


def test_admin_sessions_lists_created_sessions(client: TestClient) -> None:
    _create_candidate(client)
    client.post(
        "/api/v1/assessment/trigger",
        json={
            "candidate_id": "amara@helixrobotics.com",
            "phone_number": "+44 7700 900118",
        },
    )

    response = client.get("/api/v1/admin/sessions")
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert items[0]["candidate_email"] == "amara@helixrobotics.com"
    assert items[0]["phone_number"] == "+447700900118"


def test_admin_sessions_filters_by_status(client: TestClient) -> None:
    _create_candidate(client)
    client.post(
        "/api/v1/assessment/trigger",
        json={
            "candidate_id": "amara@helixrobotics.com",
            "phone_number": "+44 7700 900118",
        },
    )

    response = client.get("/api/v1/admin/sessions?status=completed")
    assert response.status_code == 200
    assert response.json() == []
