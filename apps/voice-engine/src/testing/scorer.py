"""MockInterviewScorer — evaluates how accurately the pipeline assessed the candidate.

Compares each extracted claim's sfia_level against the candidate's configured
sfia_level and produces an accuracy score.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.domain.models.claim import AssessmentReport, HolisticSkillProfile
from src.testing.candidate_bot import CandidatePersona


@dataclass
class PerSkillScore:
    skill_code: str
    skill_name: str
    claim_count: int
    configured_level: int
    mean_assessed_level: float
    mean_delta: float
    mean_accuracy_pct: float
    mean_confidence: float


@dataclass
class ScoreResult:
    configured_level: int
    mean_assessed_level: float
    mean_level_delta: float
    mean_accuracy_pct: float
    mean_confidence: float
    total_claims: int
    per_skill: list[PerSkillScore] = field(default_factory=list)
    holistic_profiles: list[HolisticSkillProfile] = field(default_factory=list)


def score(persona: CandidatePersona, report: AssessmentReport) -> ScoreResult:
    """Score the assessment report against the configured candidate profile.

    Accuracy formula per claim:
        accuracy = 1.0 - (abs(assessed_level - configured_level) / 6)

    A perfect match scores 1.0 (100%); a maximum delta of 6 scores 0.0 (0%).
    """
    claims = report.claims
    if not claims:
        return ScoreResult(
            configured_level=persona.sfia_level,
            mean_assessed_level=0.0,
            mean_level_delta=0.0,
            mean_accuracy_pct=0.0,
            mean_confidence=0.0,
            total_claims=0,
            holistic_profiles=report.holistic_assessment,
        )

    configured = persona.sfia_level
    deltas = [abs(c.sfia_level - configured) for c in claims]
    accuracies = [1.0 - (d / 6) for d in deltas]
    confidences = [c.confidence for c in claims]
    assessed_levels = [c.sfia_level for c in claims]

    # Per-skill breakdown
    skill_map: dict[str, list] = {}
    for claim in claims:
        skill_map.setdefault(claim.sfia_skill_code, []).append(claim)

    per_skill: list[PerSkillScore] = []
    for code, skill_claims in sorted(skill_map.items()):
        s_deltas = [abs(c.sfia_level - configured) for c in skill_claims]
        s_acc = [1.0 - (d / 6) for d in s_deltas]
        per_skill.append(
            PerSkillScore(
                skill_code=code,
                skill_name=skill_claims[0].sfia_skill_name,
                claim_count=len(skill_claims),
                configured_level=configured,
                mean_assessed_level=sum(c.sfia_level for c in skill_claims) / len(skill_claims),
                mean_delta=sum(s_deltas) / len(s_deltas),
                mean_accuracy_pct=round(sum(s_acc) / len(s_acc) * 100, 1),
                mean_confidence=sum(c.confidence for c in skill_claims) / len(skill_claims),
            )
        )

    return ScoreResult(
        configured_level=configured,
        mean_assessed_level=round(sum(assessed_levels) / len(assessed_levels), 2),
        mean_level_delta=round(sum(deltas) / len(deltas), 2),
        mean_accuracy_pct=round(sum(accuracies) / len(accuracies) * 100, 1),
        mean_confidence=round(sum(confidences) / len(confidences), 3),
        total_claims=len(claims),
        per_skill=per_skill,
        holistic_profiles=report.holistic_assessment,
    )


__all__ = ["PerSkillScore", "ScoreResult", "score"]
