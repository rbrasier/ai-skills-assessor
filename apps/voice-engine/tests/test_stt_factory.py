"""Unit tests for the STT provider factory (no Pipecat voice extras required).

These tests verify:
  - Default provider is Deepgram when STT_PROVIDER is unset or "deepgram"
  - Whisper provider is selected when STT_PROVIDER=whisper and URL is set
  - Graceful fallback to Deepgram when WHISPER_STT_URL is missing
  - Config model validates provider literals correctly
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import Settings

# ── Settings validation ────────────────────────────────────────────────────────


def test_default_stt_provider_is_deepgram() -> None:
    s = Settings(
        daily_api_key="x",
        daily_domain="x.daily.co",
    )
    assert s.stt_provider == "deepgram"


def test_stt_provider_whisper_accepted() -> None:
    s = Settings(
        daily_api_key="x",
        daily_domain="x.daily.co",
        stt_provider="whisper",
        whisper_stt_url="ws://localhost:8001/ws/transcribe",
    )
    assert s.stt_provider == "whisper"
    assert s.whisper_stt_url == "ws://localhost:8001/ws/transcribe"


def test_whisper_stt_url_defaults_empty() -> None:
    s = Settings(daily_api_key="x", daily_domain="x.daily.co")
    assert s.whisper_stt_url == ""


# ── Factory: Deepgram path ──────────────────────────────────────────────────


def test_factory_selects_deepgram_by_default() -> None:
    """Factory returns Deepgram service when STT_PROVIDER=deepgram."""
    settings = Settings(
        daily_api_key="x",
        daily_domain="x.daily.co",
        deepgram_api_key="dg-key",
        stt_provider="deepgram",
    )

    fake_deepgram = MagicMock(name="DeepgramSTTService")

    with (
        patch(
            "src.adapters.stt.factory._create_deepgram",
            return_value=fake_deepgram,
        ) as mock_dg,
    ):
        from src.adapters.stt.factory import create_stt_service

        result = create_stt_service(settings)

    mock_dg.assert_called_once_with(settings)
    assert result is fake_deepgram


# ── Factory: Whisper path ──────────────────────────────────────────────────


def test_factory_falls_back_when_whisper_url_missing() -> None:
    """Falls back to Deepgram when STT_PROVIDER=whisper but URL is empty."""
    settings = Settings(
        daily_api_key="x",
        daily_domain="x.daily.co",
        stt_provider="whisper",
        whisper_stt_url="",
        deepgram_api_key="dg-key",
    )

    fake_deepgram = MagicMock(name="DeepgramSTTService")

    with patch(
        "src.adapters.stt.factory._create_deepgram",
        return_value=fake_deepgram,
    ) as mock_dg:
        from src.adapters.stt.factory import create_stt_service

        result = create_stt_service(settings)

    mock_dg.assert_called_once()
    assert result is fake_deepgram


def test_factory_falls_back_when_whisper_unreachable() -> None:
    """Falls back to Deepgram when the Whisper health endpoint is unreachable."""
    settings = Settings(
        daily_api_key="x",
        daily_domain="x.daily.co",
        stt_provider="whisper",
        whisper_stt_url="ws://unreachable-host:8001/ws/transcribe",
        deepgram_api_key="dg-key",
    )

    fake_deepgram = MagicMock(name="DeepgramSTTService")

    with (
        patch("src.adapters.stt.factory._whisper_reachable", new=AsyncMock(return_value=False)),
        patch("asyncio.get_event_loop") as mock_loop,
        patch(
            "src.adapters.stt.factory._create_deepgram",
            return_value=fake_deepgram,
        ) as mock_dg,
    ):
        mock_loop.return_value.run_until_complete = lambda coro: (
            # Drain the coroutine and return False
            coro.close() or False
        )
        from src.adapters.stt.factory import create_stt_service

        result = create_stt_service(settings)

    mock_dg.assert_called_once()
    assert result is fake_deepgram


def test_factory_selects_whisper_when_reachable() -> None:
    """Returns Whisper processor when URL is set and health probe succeeds."""
    settings = Settings(
        daily_api_key="x",
        daily_domain="x.daily.co",
        stt_provider="whisper",
        whisper_stt_url="ws://localhost:8001/ws/transcribe",
    )

    fake_processor = MagicMock(name="WhisperProcessor")

    # WhisperSTTService is imported lazily inside create_stt_service via
    # `from src.adapters.stt.whisper_stt_service import WhisperSTTService`.
    # Patch the attribute on the source module so the lazy import picks it up.
    import src.adapters.stt.whisper_stt_service as _wstt_mod

    with (
        patch("asyncio.get_event_loop") as mock_loop,
        patch.object(_wstt_mod, "WhisperSTTService") as mock_cls,
    ):
        mock_loop.return_value.run_until_complete = lambda _coro: True
        mock_cls.return_value.build.return_value = fake_processor

        from src.adapters.stt.factory import create_stt_service

        result = create_stt_service(settings)

    mock_cls.assert_called_once_with(url="ws://localhost:8001/ws/transcribe")
    assert result is fake_processor


# ── Env-var driven (integration-style) ────────────────────────────────────────


@pytest.mark.parametrize("provider", ["deepgram", "whisper"])
def test_settings_loads_stt_provider_from_env(provider: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STT_PROVIDER", provider)
    monkeypatch.setenv("DAILY_API_KEY", "x")
    monkeypatch.setenv("DAILY_DOMAIN", "x.daily.co")
    s = Settings()
    assert s.stt_provider == provider
