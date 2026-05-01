"""Claim and report domain models for Phase 6 post-call extraction pipeline.

All models use Pydantic for serialisation consistency with the JSON stored in
assessment_sessions.claims_json. SkillSummary is computed at read time and
never persisted.

Dual-token review model (phase-6-revision-dual-review-tokens):
- expert_review_token / supervisor_review_token replace the single review_token
- Claim uses expert_level + supervisor_decision + supervisor_comment
- Legacy sme_* fields retained for backward compatibility only
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field


class EvidenceSegment(BaseModel):
    """Timestamp range in the call recording that supports a claim."""

    start_time: float
    end_time: float


class Claim(BaseModel):
    """A discrete, verifiable work claim extracted and enriched from a transcript."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    verbatim_quote: str
    interpreted_claim: str
    sfia_skill_code: str
    sfia_skill_name: str
    sfia_level: int = Field(ge=1, le=7)
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    framework_type: str = "sfia-9"
    evidence_segments: list[EvidenceSegment] = Field(default_factory=list)

    # Dual reviewer fields (phase-6-revision-dual-review-tokens)
    expert_level: int | None = Field(default=None, ge=1, le=7)
    supervisor_decision: str = "pending"   # pending | verified | rejected
    supervisor_comment: str | None = None

    # Deprecated legacy fields — retained for backward compatibility
    sme_status: str = "pending"
    sme_adjusted_level: int | None = None
    sme_notes: str | None = None


class ClaimExtractionResult(BaseModel):
    session_id: str
    claims: list[Claim]
    total_claims: int
    extracted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AssessmentReport(BaseModel):
    """In-memory representation of the full report — not a separate DB table.

    Dual-token model: expert_review_token + supervisor_review_token replace the
    single review_token. Legacy review_token/review_url retained for compat.
    """

    session_id: str
    # Dual tokens (canonical)
    expert_review_token: str
    supervisor_review_token: str
    expert_review_url: str
    supervisor_review_url: str
    # Deprecated single-token fields
    review_token: str = ""
    review_url: str = ""
    candidate_name: str
    claims: list[Claim]
    total_claims: int
    overall_confidence: float
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = "awaiting_expert"
    expires_at: datetime
    # Expert review audit (set on PUT /review/expert/{token})
    expert_submitted_at: datetime | None = None
    expert_reviewer_full_name: str | None = None
    expert_reviewer_email: str | None = None
    # Supervisor review audit (set on PUT /review/supervisor/{token})
    supervisor_submitted_at: datetime | None = None
    supervisor_reviewer_full_name: str | None = None
    supervisor_reviewer_email: str | None = None
    reviews_completed_at: datetime | None = None


class SkillSummary(BaseModel):
    """Computed on read from claims — never persisted."""

    skill_code: str
    skill_name: str
    claim_count: int
    suggested_level: int
    average_confidence: float
    claims: list[Claim]


__all__ = [
    "AssessmentReport",
    "Claim",
    "ClaimExtractionResult",
    "EvidenceSegment",
    "SkillSummary",
]
