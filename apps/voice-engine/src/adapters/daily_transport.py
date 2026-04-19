"""DailyTransport adapter — stub for Phase 1.

Real implementation (Daily REST API + Pipecat ``DailyTransport``) lands in the
voice-engine core phase.
"""

from __future__ import annotations

from src.domain.models.assessment import CallConfig, CallConnection
from src.domain.ports.voice_transport import IVoiceTransport


class DailyVoiceTransport(IVoiceTransport):
    def __init__(self, api_key: str, daily_domain: str) -> None:
        self._api_key = api_key
        self._daily_domain = daily_domain

    async def dial(self, config: CallConfig) -> CallConnection:
        raise NotImplementedError("DailyVoiceTransport.dial is implemented in Phase 2")

    async def hangup(self, connection: CallConnection) -> None:
        raise NotImplementedError("DailyVoiceTransport.hangup is implemented in Phase 2")
