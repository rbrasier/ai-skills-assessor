"""``IVoiceTransport`` port — abstraction over the telephony / WebRTC layer.

Phase 2 extends the Phase 1 contract with duration tracking and an
optional recording URL lookup so ``CallManager`` and the status
endpoint can surface progress without knowing about Daily.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.models.assessment import CallConfig, CallConnection


class IVoiceTransport(ABC):
    @abstractmethod
    async def dial(self, config: CallConfig) -> CallConnection:
        """Place an outbound call and return connection details."""
        ...

    @abstractmethod
    async def hangup(self, connection: CallConnection) -> None:
        """End an active call."""
        ...

    @abstractmethod
    async def get_call_duration(self, session_id: str) -> float:
        """Return the current call duration (seconds).

        Should return ``0.0`` for sessions that have not started yet
        and the total elapsed time for ongoing or completed calls.
        """
        ...

    @abstractmethod
    async def get_recording_url(self, session_id: str) -> str | None:
        """Return the Daily cloud recording URL, if available."""
        ...
