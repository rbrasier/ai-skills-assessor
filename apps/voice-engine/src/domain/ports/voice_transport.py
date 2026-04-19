"""``IVoiceTransport`` port — abstraction over the telephony / WebRTC layer."""

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
