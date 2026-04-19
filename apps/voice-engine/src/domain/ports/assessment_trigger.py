"""``IAssessmentTrigger`` port — entry point for orchestrating an outbound call."""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.models.assessment import AssessmentSession, CallConfig


class IAssessmentTrigger(ABC):
    @abstractmethod
    async def trigger(self, config: CallConfig) -> AssessmentSession:
        """Initiate an assessment call and return persisted session metadata."""
        ...
