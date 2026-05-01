"""Domain models — plain Python dataclasses with no I/O dependencies."""

from src.domain.models.assessment import (
    AssessmentSession,
    AssessmentStatus,
    CallConfig,
    CallConnection,
    Candidate,
)
from src.domain.models.claim import AssessmentReport, Claim, ClaimExtractionResult
from src.domain.models.transcript import Transcript, TranscriptSegment

__all__ = [
    "AssessmentReport",
    "AssessmentSession",
    "AssessmentStatus",
    "CallConfig",
    "CallConnection",
    "Candidate",
    "Claim",
    "ClaimExtractionResult",
    "Transcript",
    "TranscriptSegment",
]
