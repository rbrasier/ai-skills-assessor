"""Smoke tests for the voice engine's health endpoint.

Phase 3 (v0.4.0) turned ``/health`` into a deep healthcheck that also
probes the persistence backend via ``IPersistence.ping()``. Railway's
automatic rollback uses this endpoint — see
``docs/development/adr/ADR-006-deployment-platform.md``.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_returns_ok_with_version_and_db(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload == {"status": "ok", "version": "0.7.0", "database": "ok"}


def test_health_reports_degraded_when_db_unreachable(
    client: TestClient,
) -> None:
    # Swap the app's persistence with one whose ``ping`` always fails.
    class _UnreachablePersistence:
        async def ping(self) -> bool:
            return False

    original = client.app.state.persistence
    try:
        client.app.state.persistence = _UnreachablePersistence()
        response = client.get("/health")
        assert response.status_code == 503
        payload = response.json()
        assert payload["status"] == "degraded"
        assert payload["database"] == "unreachable"
        assert payload["version"] == "0.7.0"
    finally:
        client.app.state.persistence = original
