"""Smoke tests for the Phase 1 FastAPI surface."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_assessment_trigger_returns_pending_session(client: TestClient) -> None:
    response = client.post(
        "/api/v1/assessment/trigger",
        json={
            "phone_number": "+61412345678",
            "candidate_id": "11111111-1111-1111-1111-111111111111",
        },
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    assert "session_id" in body
    assert "created_at" in body


def test_assessment_trigger_validates_payload(client: TestClient) -> None:
    response = client.post("/api/v1/assessment/trigger", json={})
    assert response.status_code == 422
