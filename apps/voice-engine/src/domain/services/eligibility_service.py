"""``AssessmentEligibilityService`` — pre-call eligibility gate.

Wraps ``IPersistence.check_assessment_eligibility`` and exposes a clean
domain-level interface so ``CallManager`` can enforce the cooldown policy
without coupling directly to persistence details.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.domain.ports.persistence import IPersistence


@dataclass
class EligibilityResult:
    eligible: bool
    reason: str | None
    next_eligible_at: datetime | None
    cooldown_days: int


class AssessmentEligibilityService:
    def __init__(self, persistence: IPersistence) -> None:
        self._persistence = persistence

    async def check(self, candidate_id: str) -> EligibilityResult:
        """Return eligibility for ``candidate_id``."""
        data = await self._persistence.check_assessment_eligibility(candidate_id)
        next_at: datetime | None = None
        raw = data.get("next_eligible_at")
        if raw is not None:
            try:
                next_at = datetime.fromisoformat(str(raw))
            except ValueError:
                next_at = None
        return EligibilityResult(
            eligible=bool(data.get("eligible", True)),
            reason=data.get("reason"),
            next_eligible_at=next_at,
            cooldown_days=int(data.get("cooldown_days", 90)),
        )


__all__ = ["AssessmentEligibilityService", "EligibilityResult"]
