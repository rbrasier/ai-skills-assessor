"""MockInterviewScorer — evaluates how accurately the pipeline assessed the candidate.

Derives all accuracy metrics from the holistic skill profiles (not per-claim).
Each profile's estimated_level is compared to the candidate's configured sfia_level,
weighted by prominence, to produce a single accuracy figure.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.domain.models.claim import AssessmentReport, HolisticSkillProfile
from src.testing.candidate_bot import CandidatePersona


@dataclass
class ScoreResult:
    configured_level: int
    mean_assessed_level: float
    mean_level_delta: float
    mean_accuracy_pct: float
    mean_prominence: float
    total_claims: int
    holistic_profiles: list[HolisticSkillProfile] = field(default_factory=list)


def score(persona: CandidatePersona, report: AssessmentReport) -> ScoreResult:
    """Score the assessment report against the configured candidate profile.

    Uses holistic skill profiles as the primary signal. All metrics are
    prominence-weighted so skills that dominated the conversation count more.

    Accuracy formula per profile:
        accuracy = 1.0 - (abs(estimated_level - configured_level) / 6)

    A perfect match scores 1.0 (100%); a maximum delta of 6 scores 0.0 (0%).
    """
    holistic = report.holistic_assessment
    configured = persona.sfia_level

    if not holistic:
        return ScoreResult(
            configured_level=configured,
            mean_assessed_level=0.0,
            mean_level_delta=0.0,
            mean_accuracy_pct=0.0,
            mean_prominence=0.0,
            total_claims=len(report.claims),
            holistic_profiles=[],
        )

    total_prominence = sum(h.prominence for h in holistic) or 1.0

    mean_assessed = sum(h.estimated_level * h.prominence for h in holistic) / total_prominence
    deltas = [abs(h.estimated_level - configured) for h in holistic]
    accuracies = [1.0 - (d / 6) for d in deltas]

    mean_delta = sum(d * h.prominence for d, h in zip(deltas, holistic, strict=True)) / total_prominence
    mean_accuracy = sum(a * h.prominence for a, h in zip(accuracies, holistic, strict=True)) / total_prominence
    mean_prominence = sum(h.prominence for h in holistic) / len(holistic)

    return ScoreResult(
        configured_level=configured,
        mean_assessed_level=round(mean_assessed, 2),
        mean_level_delta=round(mean_delta, 2),
        mean_accuracy_pct=round(mean_accuracy * 100, 1),
        mean_prominence=round(mean_prominence, 3),
        total_claims=len(report.claims),
        holistic_profiles=holistic,
    )


__all__ = ["ScoreResult", "score"]
