"""Runtime configuration for the voice engine.

Loaded from environment variables (via Pydantic Settings) at startup. Adapter
implementations should accept a ``Settings`` instance via constructor injection
rather than reading ``os.environ`` directly.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = "postgresql://user:password@localhost:5432/ai_skills_assessor"

    # ─── Daily ─────────────────────────────────────────────────────
    daily_api_key: str = ""
    daily_domain: str = ""
    # Daily SFU region. Phase 3 / ADR-006 deploys to Railway Singapore,
    # so the default is co-located with Daily's `ap-southeast-1` SFU.
    # Override to `ap-southeast-2` when the voice engine runs in
    # AWS Sydney.
    daily_geo: str = "ap-southeast-1"
    # Optional Daily phone-number ID to use as the outbound caller ID
    # on PSTN dial-out. When empty, Daily rotates through a random
    # number from the workspace's pool.
    daily_caller_id: str = ""

    # ─── AI providers (Phase 3 Revision 1) ────────────────────────
    # All three are optional at boot — missing keys cause a 503 at
    # `/api/v1/assessment/trigger` with a loud log warning so local
    # dev / tests remain painless.
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-haiku-latest"
    deepgram_api_key: str = ""
    deepgram_model: str = "nova-2-phonecall"
    elevenlabs_api_key: str = ""
    # "Rachel" — ElevenLabs' default female voice; override per-tenant
    # in production via the Railway env panel.
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"

    # ─── Bot identity ─────────────────────────────────────────────
    bot_name: str = "Noa"
    bot_org_name: str = "Resonant"

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
