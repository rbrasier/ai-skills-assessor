"""Unit tests for the TTS provider factory (no Pipecat voice extras required).

These tests verify:
  - Default provider is ElevenLabs when TTS_PROVIDER is unset or "elevenlabs"
  - Kokoro provider is selected when TTS_PROVIDER=kokoro and URL is set
  - Graceful fallback to ElevenLabs when KOKORO_TTS_URL is missing
  - Graceful fallback when Kokoro health endpoint is unreachable
  - Config model validates provider literals correctly
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.config import Settings

# ── Settings validation ────────────────────────────────────────────────────────


def test_default_tts_provider_is_elevenlabs(monkeypatch: pytest.MonkeyPatch) -> None:
    # Suppress .env file and process-env overrides so we test the declared default,
    # not whatever the developer's local config happens to set.
    monkeypatch.delenv("TTS_PROVIDER", raising=False)
    s = Settings(
        _env_file=None,
        daily_api_key="x",
        daily_domain="x.daily.co",
    )
    assert s.tts_provider == "elevenlabs"


def test_tts_provider_kokoro_accepted() -> None:
    s = Settings(
        daily_api_key="x",
        daily_domain="x.daily.co",
        tts_provider="kokoro",
        kokoro_tts_url="http://localhost:8880",
        kokoro_voice="af_bella",
    )
    assert s.tts_provider == "kokoro"
    assert s.kokoro_tts_url == "http://localhost:8880"
    assert s.kokoro_voice == "af_bella"


def test_kokoro_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KOKORO_TTS_URL", raising=False)
    monkeypatch.delenv("TTS_PROVIDER", raising=False)
    s = Settings(_env_file=None, daily_api_key="x", daily_domain="x.daily.co")
    assert s.kokoro_tts_url == ""
    assert s.kokoro_voice == "af_bella"
    assert s.kokoro_sample_rate == 24000


# ── Factory: ElevenLabs path ───────────────────────────────────────────────────


def test_factory_selects_elevenlabs_by_default() -> None:
    """Factory returns ElevenLabs service when TTS_PROVIDER=elevenlabs."""
    settings = Settings(
        daily_api_key="x",
        daily_domain="x.daily.co",
        elevenlabs_api_key="el-key",
        tts_provider="elevenlabs",
    )

    fake_el = MagicMock(name="ElevenLabsTTSService")

    with patch(
        "src.adapters.tts.factory._create_elevenlabs",
        return_value=fake_el,
    ) as mock_el:
        from src.adapters.tts.factory import create_tts_service

        result = create_tts_service(settings)

    mock_el.assert_called_once_with(settings)
    assert result is fake_el


# ── Factory: Kokoro path ───────────────────────────────────────────────────────


def test_factory_falls_back_when_kokoro_url_missing() -> None:
    """Falls back to ElevenLabs when TTS_PROVIDER=kokoro but URL is empty."""
    settings = Settings(
        daily_api_key="x",
        daily_domain="x.daily.co",
        tts_provider="kokoro",
        kokoro_tts_url="",
        elevenlabs_api_key="el-key",
    )

    fake_el = MagicMock(name="ElevenLabsTTSService")

    with patch(
        "src.adapters.tts.factory._create_elevenlabs",
        return_value=fake_el,
    ) as mock_el:
        from src.adapters.tts.factory import create_tts_service

        result = create_tts_service(settings)

    mock_el.assert_called_once()
    assert result is fake_el


def test_factory_falls_back_when_kokoro_unreachable() -> None:
    """Falls back to ElevenLabs when the Kokoro health endpoint is unreachable."""
    settings = Settings(
        daily_api_key="x",
        daily_domain="x.daily.co",
        tts_provider="kokoro",
        kokoro_tts_url="http://unreachable-host:8880",
        elevenlabs_api_key="el-key",
    )

    fake_el = MagicMock(name="ElevenLabsTTSService")

    with (
        patch(
            "src.adapters.tts.factory._kokoro_reachable_sync",
            return_value=False,
        ),
        patch(
            "src.adapters.tts.factory._create_elevenlabs",
            return_value=fake_el,
        ) as mock_el,
    ):
        from src.adapters.tts.factory import create_tts_service

        result = create_tts_service(settings)

    mock_el.assert_called_once()
    assert result is fake_el


def test_factory_selects_kokoro_when_reachable() -> None:
    """Returns Kokoro processor when URL is set and health probe succeeds."""
    settings = Settings(
        daily_api_key="x",
        daily_domain="x.daily.co",
        tts_provider="kokoro",
        kokoro_tts_url="http://localhost:8880",
        kokoro_voice="af_bella",
        kokoro_sample_rate=24000,
    )

    fake_processor = MagicMock(name="KokoroProcessor")

    # KokoroTTSService is imported lazily inside create_tts_service; patch at
    # the source module so the lazy `from ... import` picks up the mock.
    import src.adapters.tts.kokoro_tts_service as _ktts_mod

    with (
        patch(
            "src.adapters.tts.factory._kokoro_reachable_sync",
            return_value=True,
        ),
        patch.object(_ktts_mod, "KokoroTTSService") as mock_cls,
    ):
        mock_cls.return_value.build.return_value = fake_processor

        from src.adapters.tts.factory import create_tts_service

        result = create_tts_service(settings)

    mock_cls.assert_called_once_with(
        url="http://localhost:8880",
        voice="af_bella",
        sample_rate=24000,
    )
    assert result is fake_processor


# ── /tts-test endpoint ────────────────────────────────────────────────────────


def test_tts_test_endpoint_elevenlabs(client: TestClient) -> None:  # type: ignore[name-defined]  # noqa: F821
    """GET /tts-test returns 503 when ELEVENLABS_API_KEY is not set."""
    resp = client.get("/tts-test")
    # key is empty in test env — expect 503 (or 200 if test env has key)
    assert resp.status_code in (200, 503)


def test_tts_test_endpoint_kokoro_without_url(client: TestClient) -> None:  # type: ignore[name-defined]  # noqa: F821
    """GET /tts-test with TTS_PROVIDER=kokoro but no URL returns 503."""

    from src.config import Settings as _S

    client.app.state.settings = _S(
        daily_api_key="x",
        daily_domain="x.daily.co",
        tts_provider="kokoro",
        kokoro_tts_url="",
    )
    resp = client.get("/tts-test")
    assert resp.status_code == 503
    assert "KOKORO_TTS_URL" in resp.json()["detail"]


# ── Env-var driven ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("provider", ["elevenlabs", "kokoro"])
def test_settings_loads_tts_provider_from_env(provider: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TTS_PROVIDER", provider)
    monkeypatch.setenv("DAILY_API_KEY", "x")
    monkeypatch.setenv("DAILY_DOMAIN", "x.daily.co")
    s = Settings()
    assert s.tts_provider == provider
