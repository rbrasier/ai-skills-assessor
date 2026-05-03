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

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, Field


class EvidenceSegment(BaseModel):
    """Timestamp range in the call recording that supports a claim."""

    start_time: float
    end_time: float


class Claim(BaseModel):
    """A discrete, verifiable work claim extracted and enriched from a transcript.

    claim_type governs which reviewer validates it:
    - "sme":        Technical HOW/WHY — technology choices, architecture, algorithms.
                    Routed to the expert (SME) reviewer.
    - "supervisor": Factual WHAT/WHERE/WHEN — job titles, projects, team sizes, durations.
                    Routed to the supervisor reviewer.

    SFIA level is NOT assessed at the individual claim level — only the holistic
    analysis produces level estimates. sfia_level defaults to 0 (unset).
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    verbatim_quote: str
    interpreted_claim: str
    summary: str = ""
    claim_type: str = "sme"  # "sme" | "supervisor"
    sfia_skill_code: str
    sfia_skill_name: str
    sfia_level: int = Field(default=0, ge=0, le=7)  # 0 = not evaluated at claim level
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reasoning: str = ""
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
    holistic_assessment: list[HolisticSkillProfile] = Field(default_factory=list)
    extracted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


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
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: str = "awaiting_expert"
    expires_at: datetime
    holistic_assessment: list[HolisticSkillProfile] = Field(default_factory=list)
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


class HolisticSkillProfile(BaseModel):
    """One skill as assessed holistically from the full transcript."""

    skill_code: str
    skill_name: str
    estimated_level: int = Field(ge=1, le=7)
    prominence: float = Field(ge=0.0, le=1.0)
    evidence_summary: str


__all__ = [
    "AssessmentReport",
    "Claim",
    "ClaimExtractionResult",
    "EvidenceSegment",
    "HolisticSkillProfile",
    "SkillSummary",
]
