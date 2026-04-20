"""``ICallLifecycleListener`` port — receives call state transitions.

Phase 3 Revision 1 wires the Pipecat pipeline's Daily event handlers to
this port so the voice transport never has to import the domain
orchestration service. Adapters (e.g. :class:`DailyVoiceTransport`) own
the event handlers; ``CallManager`` implements this interface and gets
injected into the transport. This satisfies ADR-001:

    transport  ──► listener port ──► CallManager (domain)
       │                                    │
       └── knows Daily/Pipecat              └── knows IPersistence only

All three methods are *fire-and-forget*: the caller must not block the
pipeline on domain side-effects, and the implementation must swallow
expected errors so a flaky DB does not take down the voice pipeline.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class ICallLifecycleListener(ABC):
    @abstractmethod
    async def on_call_connected(self, session_id: str) -> None:
        """Candidate picked up the phone; pipeline is live.

        Transitions ``status`` from ``dialling`` → ``in_progress`` and
        stamps ``started_at`` if it isn't already set.
        """
        ...

    @abstractmethod
    async def on_call_ended(self, session_id: str) -> None:
        """Bot or candidate hung up normally.

        Transitions ``status`` → ``completed`` and stamps ``ended_at``.
        Idempotent — safe to call even if the session is already
        terminal.
        """
        ...

    @abstractmethod
    async def on_call_failed(
        self,
        session_id: str,
        *,
        reason: str,
    ) -> None:
        """Daily returned a dial-out error, or the pipeline crashed.

        Transitions ``status`` → ``failed``, stamps ``ended_at``, and
        records ``metadata.failureReason``.
        """
        ...
