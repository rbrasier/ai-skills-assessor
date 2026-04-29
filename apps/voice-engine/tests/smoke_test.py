"""Production smoke test (Phase 3 / v0.4.0).

Runs the end-to-end candidate intake → call trigger → status poll →
admin listing flow against a live deployment. The test is skipped by
default so it does not run as part of normal ``pytest`` invocations;
enable it with:

    SMOKE_TEST_URL=https://voice-engine-prod.example.com \
      pytest apps/voice-engine/tests/smoke_test.py --run-smoke -q

The post-deploy GitHub Actions job in ``.github/workflows/deploy.yml``
invokes it automatically when ``vars.SMOKE_TEST_URL`` is set.

The assertions are deliberately permissive: the test verifies HTTP
contracts are reachable and well-formed, *not* that a real PSTN call
connects — the deployment may be running without Daily credentials, in
which case the trigger will eventually transition the session to
``failed``.
"""

from __future__ import annotations

import os
import uuid

import httpx
import pytest


@pytest.fixture(scope="module")
def smoke_url(request: pytest.FixtureRequest) -> str:
    if not request.config.getoption("--run-smoke"):
        pytest.skip("smoke test disabled; pass --run-smoke to enable")
    url = os.environ.get("SMOKE_TEST_URL", "").rstrip("/")
    if not url:
        pytest.skip("SMOKE_TEST_URL env var not set")
    return url


@pytest.mark.smoke
def test_smoke_production(smoke_url: str) -> None:
    """Full intake → trigger → status → admin cycle against production."""
    unique = uuid.uuid4().hex[:8]
    email = f"smoke-{unique}@example.com"

    with httpx.Client(base_url=smoke_url, timeout=15.0) as client:
        # 1. Health — must pass before anything else.
        health = client.get("/health")
        assert health.status_code == 200, health.text
        body = health.json()
        assert body.get("status") == "ok"
        assert body.get("database") == "ok"

        # 2. Create/lookup candidate (Step 01 of intake form).
        candidate_resp = client.post(
            "/api/v1/assessment/candidate",
            json={
                "work_email": email,
                "first_name": "Smoke",
                "last_name": "Test",
                "employee_id": f"SMOKE-{unique}",
            },
        )
        assert candidate_resp.status_code == 200, candidate_resp.text
        candidate_id = candidate_resp.json()["candidate_id"]

        # 3. Trigger call (Step 02). A +44 test number keeps it out of
        #    the +61 Daily PSTN path when Daily isn't configured.
        trigger_resp = client.post(
            "/api/v1/assessment/trigger",
            json={
                "candidate_id": candidate_id,
                "phone_number": "+44 7700 900118",
            },
        )
        assert trigger_resp.status_code in (200, 202), trigger_resp.text
        session_id = trigger_resp.json()["session_id"]

        # 4. Status endpoint must respond (status may legitimately be
        #    ``failed`` on a deployment without Daily credentials).
        status_resp = client.get(f"/api/v1/assessment/{session_id}/status")
        assert status_resp.status_code == 200, status_resp.text
        status_body = status_resp.json()
        assert status_body["session_id"] == session_id
        assert "status" in status_body

        # 5. Admin listing must return our new session (or at least a
        #    well-formed list — pagination defaults to 50).
        admin_resp = client.get(
            "/api/v1/admin/sessions",
            params={"limit": 5, "email": email},
        )
        assert admin_resp.status_code == 200, admin_resp.text
        admin_body = admin_resp.json()
        assert isinstance(admin_body, list)
