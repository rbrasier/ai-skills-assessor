"""Runtime configuration for the voice engine.

Loaded from environment variables (via Pydantic Settings) at startup. Adapter
implementations should accept a ``Settings`` instance via constructor injection
rather than reading ``os.environ`` directly.
"""

from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

DialingMethod = Literal["daily", "browser"]
SttProvider = Literal["deepgram", "whisper"]
TtsProvider = Literal["elevenlabs", "kokoro"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = "postgresql://user:password@localhost:5432/ai_skills_assessor"

    # ─── Transport selection ───────────────────────────────────────
    # ``daily`` — Pipecat DailyTransport with PSTN dial-out (default).
    # ``browser`` — self-hosted LiveKit; candidate joins from the browser
    # (no Daily API keys required).
    dialing_method: DialingMethod = "daily"

    # ─── Daily (required when dialing_method == daily) ─────────────
    daily_api_key: str = ""
    daily_domain: str = ""
    # Daily SFU region. Phase 3 / ADR-006 deploys to Railway Singapore,
    # so the default is co-located with Daily’s `ap-southeast-1` SFU.
    # Override to `ap-southeast-2` when the voice engine runs in
    # AWS Sydney.
    daily_geo: str = "ap-southeast-1"
    # Optional Daily phone-number ID to use as the outbound caller ID
    # on PSTN dial-out. When empty, Daily rotates through a random
    # number from the workspace’s pool.
    daily_caller_id: str = ""

    # ─── LiveKit (required when dialing_method == browser) ────────
    # WebSocket URL of your LiveKit server, e.g. wss://livekit.example.com
    livekit_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: str = ""
    # Public page used to open a browser call. Default is LiveKit’s hosted
    # "custom server" join UI; self-host a meet app and point this at it if needed.
    livekit_meet_url: str = "https://meet.livekit.io/custom"
    # Token TTL (seconds) for both bot and browser participant.
    livekit_token_ttl_seconds: int = 3600

    # ─── AI providers ─────────────────────────────────────────────
    # All are optional at boot — missing keys cause a 503 at
    # `/api/v1/assessment/trigger` with a loud log warning so local
    # dev / tests remain painless.
    anthropic_api_key: str = ""
    # Real-time in-call model — low latency, used by Pipecat pipeline.
    anthropic_in_call_model: str = "claude-haiku-4-5"
    # Post-call model — higher quality, used for claim extraction (Phase 6).
    anthropic_post_call_model: str = "claude-sonnet-4-6"
    openai_api_key: str = ""  # required for embedding ingestion scripts
    deepgram_api_key: str = ""
    deepgram_model: str = "nova-2-phonecall"
    elevenlabs_api_key: str = ""
    # "Rachel" — ElevenLabs’ default female voice; override per-tenant
    # in production via the Railway env panel.
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"

    # ─── STT provider selection (Phase 3 Revision 3) ──────────────
    # ``deepgram`` — Deepgram cloud STT (default, requires DEEPGRAM_API_KEY).
    # ``whisper``  — Self-hosted faster-whisper via WebSocket (requires
    #                WHISPER_STT_URL). Falls back to deepgram if URL is unset
    #                or the service is unreachable at pipeline start.
    stt_provider: SttProvider = "deepgram"
    # WebSocket URL of your self-hosted Whisper STT service.
    # Example: wss://whisper-stt.up.railway.app/ws/transcribe
    whisper_stt_url: str = ""

    # ─── TTS provider selection (Phase 3 Revision 3) ──────────────
    # ``elevenlabs`` — ElevenLabs cloud TTS (default, requires ELEVENLABS_API_KEY).
    # ``kokoro``     — Self-hosted Kokoro-FastAPI via HTTP (requires
    #                  KOKORO_TTS_URL). Falls back to elevenlabs if URL is
    #                  unset or the service is unreachable at pipeline start.
    tts_provider: TtsProvider = "elevenlabs"
    # Base HTTP URL of your self-hosted Kokoro TTS service.
    # Example: https://kokoro-tts.up.railway.app
    kokoro_tts_url: str = ""
    # Kokoro voice identifier. af_bella is the default female voice.
    kokoro_voice: str = "af_bella"
    # Output sample rate for Kokoro PCM audio (24000 matches ElevenLabs default).
    kokoro_sample_rate: int = 24000

    # ─── Bot identity ─────────────────────────────────────────────
    bot_name: str = "Noa"
    bot_org_name: str = "Resonant"

    # ─── Phase 4: SFIA flow ───────────────────────────────────────
    # Set to true to use the 5-state SFIAFlowController instead of the
    # Phase 3 basic scripted conversation. Requires ANTHROPIC_API_KEY.
    enable_sfia_flow: bool = False

    # ─── Runtime knobs ────────────────────────────────────────────
    log_level: str = "INFO"
    # Railway injects `PORT` at runtime; local dev + tests use 8000.
    port: int = 8000


def get_settings() -> Settings:
    """Return the process-wide settings instance.

    Wrapping the constructor lets tests override settings via dependency
    overrides without mutating module-level state.
    """

    return Settings()
