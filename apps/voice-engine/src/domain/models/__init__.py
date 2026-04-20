"""Domain models — plain Python dataclasses with no I/O dependencies."""

from src.domain.models.assessment import (
    AssessmentSession,
    AssessmentStatus,
    CallConfig,
    CallConnection,
    Candidate,
)
from src.domain.models.claim import Claim, ClaimMapping
from src.domain.models.skill import SFIALevel, SkillDefinition
from src.domain.models.transcript import Transcript, TranscriptSegment

__all__ = [
    "AssessmentSession",
    "AssessmentStatus",
    "CallConfig",
    "CallConnection",
    "Candidate",
    "Claim",
    "ClaimMapping",
    "SFIALevel",
    "SkillDefinition",
    "Transcript",
    "TranscriptSegment",
]
