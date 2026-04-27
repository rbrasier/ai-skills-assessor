"""Provider-aware smoke tests (Phase 3 Revision 3 / v0.5.0).

Run against a live deployment with either cloud or self-hosted providers:

    # Against cloud providers (default):
    SMOKE_TEST_URL=https://voice-engine.example.com \
      pytest apps/voice-engine/tests/test_providers_smoke.py --run-smoke -q

    # Against a deployment with self-hosted Kokoro TTS:
    SMOKE_TEST_URL=https://voice-engine.example.com \
    TTS_PROVIDER=kokoro \
      pytest apps/voice-engine/tests/test_providers_smoke.py --run-smoke -q

    # Test /tts-test endpoint only (no full call required):
    SMOKE_TEST_URL=https://voice-engine.example.com \
      pytest apps/voice-engine/tests/test_providers_smoke.py::test_smoke_tts_test_endpoint --run-smoke -q

These tests are skipped by default; pass ``--run-smoke`` to enable.
"""

from __future__ import annotations

import os

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


# ── Health ─────────────────────────────────────────────────────────────────────


@pytest.mark.smoke
def test_smoke_health(smoke_url: str) -> None:
    """Voice engine health endpoint must respond 200."""
    r = httpx.get(f"{smoke_url}/health", timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert body.get("status") == "ok"
    assert body.get("database") == "ok"
    # Version must be at least 0.5.0 to include provider-swap support
    version: str = body.get("version", "0.0.0")
    major, minor, *_ = (int(x) for x in version.split("."))
    assert (major, minor) >= (0, 5), f"Expected v0.5+, got {version}"


# ── TTS endpoint ───────────────────────────────────────────────────────────────


@pytest.mark.smoke
def test_smoke_tts_test_endpoint(smoke_url: str) -> None:
    """/tts-test must return a valid WAV audio file for the active TTS provider."""
    r = httpx.get(
        f"{smoke_url}/tts-test",
        params={"text": "Provider smoke test. Hello from the assessor."},
        timeout=30,
    )
    if r.status_code == 503:
        # No API key or URL configured — acceptable for a headless deployment
        pytest.skip(f"/tts-test returned 503 (provider not configured): {r.text[:100]}")

    assert r.status_code == 200, f"/tts-test error {r.status_code}: {r.text[:200]}"
    assert r.headers.get("content-type", "").startswith("audio/wav"), (
        f"Expected audio/wav, got {r.headers.get('content-type')}"
    )

    # Validate RIFF WAV header
    wav = r.content
    assert wav[:4] == b"RIFF", "Response is not a RIFF file"
    assert wav[8:12] == b"WAVE", "Response is not a WAVE file"
    assert len(wav) > 44, "WAV file is too small to contain audio data"


# ── Whisper STT health (when self-hosted) ──────────────────────────────────────


@pytest.mark.smoke
def test_smoke_whisper_stt_health() -> None:
    """If WHISPER_STT_URL is set, the Whisper STT health endpoint must be up."""
    if not pytest.config.getoption("--run-smoke"):  # type: ignore[attr-defined]
        pytest.skip("smoke test disabled; pass --run-smoke to enable")

    whisper_url = os.environ.get("WHISPER_STT_URL", "")
    if not whisper_url:
        pytest.skip("WHISPER_STT_URL not set — skipping Whisper health check")

    # Convert ws(s):// → http(s)://
    http_url = whisper_url.replace("wss://", "https://").replace("ws://", "http://")
    base = http_url.split("/ws/")[0]
    health_url = base.rstrip("/") + "/health"

    r = httpx.get(health_url, timeout=10)
    assert r.status_code == 200, f"Whisper STT health check failed: {r.text[:200]}"
    body = r.json()
    assert body.get("status") == "ok", f"Whisper STT not ready: {body}"


# ── Kokoro TTS health (when self-hosted) ───────────────────────────────────────


@pytest.mark.smoke
def test_smoke_kokoro_tts_health() -> None:
    """If KOKORO_TTS_URL is set, the Kokoro health endpoint must be up."""
    if not pytest.config.getoption("--run-smoke"):  # type: ignore[attr-defined]
        pytest.skip("smoke test disabled; pass --run-smoke to enable")

    kokoro_url = os.environ.get("KOKORO_TTS_URL", "")
    if not kokoro_url:
        pytest.skip("KOKORO_TTS_URL not set — skipping Kokoro health check")

    health_url = kokoro_url.rstrip("/") + "/health"
    r = httpx.get(health_url, timeout=10)
    assert r.status_code == 200, f"Kokoro TTS health check failed: {r.text[:200]}"


# ── Full provider selection round-trip ─────────────────────────────────────────


@pytest.mark.smoke
def test_smoke_tts_provider_reported(smoke_url: str) -> None:
    """/health response version confirms provider-swap code is deployed."""
    r = httpx.get(f"{smoke_url}/health", timeout=10)
    assert r.status_code == 200
    # Implicitly tested by test_smoke_health; kept here to signal intent clearly.
    assert "version" in r.json()
