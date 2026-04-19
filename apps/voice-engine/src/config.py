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
    daily_api_key: str = ""
    daily_domain: str = ""
    anthropic_api_key: str = ""
    log_level: str = "INFO"


def get_settings() -> Settings:
    """Return the process-wide settings instance.

    Wrapping the constructor lets tests override settings via dependency
    overrides without mutating module-level state.
    """

    return Settings()
