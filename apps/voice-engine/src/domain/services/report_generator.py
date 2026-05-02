"""ReportGenerator — creates and persists assessment reports (Phase 6).

Dual-token model: generates separate expert and supervisor NanoIDs, constructs
role-specific review URLs, and persists both tokens via IPersistence.save_report().
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from nanoid import generate as nanoid_generate

from src.domain.models.claim import AssessmentReport, ClaimExtractionResult
from src.domain.ports.persistence import IPersistence

logger = logging.getLogger(__name__)

_NANOID_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
_NANOID_LENGTH = 21
_LINK_EXPIRY_DAYS = 30


class ReportGenerator:
    def __init__(self, persistence: IPersistence, base_url: str) -> None:
        self.persistence = persistence
        self.base_url = base_url.rstrip("/")

    async def generate(
        self,
        session_id: str,
        extraction_result: ClaimExtractionResult,
        candidate_name: str,
    ) -> AssessmentReport:
        expert_token = nanoid_generate(_NANOID_ALPHABET, _NANOID_LENGTH)
        supervisor_token = nanoid_generate(_NANOID_ALPHABET, _NANOID_LENGTH)
        expert_url = f"{self.base_url}/review/expert/{expert_token}"
        supervisor_url = f"{self.base_url}/review/supervisor/{supervisor_token}"
        now = datetime.now(UTC)
        expires_at = now + timedelta(days=_LINK_EXPIRY_DAYS)

        overall_confidence = (
            sum(c.confidence for c in extraction_result.claims) / len(extraction_result.claims)
            if extraction_result.claims
            else 0.0
        )

        report = AssessmentReport(
            session_id=session_id,
            expert_review_token=expert_token,
            supervisor_review_token=supervisor_token,
            expert_review_url=expert_url,
            supervisor_review_url=supervisor_url,
            # Deprecated single-token fields — dual-write for compat
            review_token=expert_token,
            review_url=expert_url,
            candidate_name=candidate_name,
            claims=extraction_result.claims,
            total_claims=extraction_result.total_claims,
            holistic_assessment=extraction_result.holistic_assessment,
            overall_confidence=overall_confidence,
            generated_at=now,
            status="awaiting_expert",
            expires_at=expires_at,
        )

        await self.persistence.save_report(
            session_id=session_id,
            claims=[c.model_dump() for c in extraction_result.claims],
            expert_review_token=expert_token,
            supervisor_review_token=supervisor_token,
            overall_confidence=overall_confidence,
            expires_at=expires_at,
            holistic_assessment=[h.model_dump() for h in extraction_result.holistic_assessment],
        )

        logger.info(
            "ReportGenerator: report saved for session %s — %d claims, "
            "expert_token=%s... supervisor_token=%s...",
            session_id,
            extraction_result.total_claims,
            expert_token[:8],
            supervisor_token[:8],
        )
        return report


__all__ = ["ReportGenerator"]
