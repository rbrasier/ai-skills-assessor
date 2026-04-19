"""``IPersistence`` port — write/read access to durable storage."""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.models.assessment import AssessmentSession
from src.domain.models.transcript import Transcript


class IPersistence(ABC):
    @abstractmethod
    async def save_session(self, session: AssessmentSession) -> None:
        """Persist (insert or update) an assessment session."""
        ...

    @abstractmethod
    async def save_transcript(self, transcript: Transcript) -> None:
        """Persist a transcript and its segments."""
        ...

    @abstractmethod
    async def get_session(self, session_id: str) -> AssessmentSession | None:
        """Retrieve a session by id, or ``None`` if it does not exist."""
        ...
