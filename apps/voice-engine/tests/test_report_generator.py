"""Unit tests for ReportGenerator.

Verifies dual NanoID generation, confidence computation, expiry, and persistence call.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.domain.models.claim import Claim, ClaimExtractionResult, EvidenceSegment
from src.domain.services.report_generator import _NANOID_ALPHABET, _NANOID_LENGTH, ReportGenerator

pytestmark = pytest.mark.asyncio


def _make_claim(confidence: float = 0.8) -> Claim:
    return Claim(
        verbatim_quote="I led the migration.",
        interpreted_claim="Candidate led a cloud migration project.",
        sfia_skill_code="CLOP",
        sfia_skill_name="Cloud Operations",
        sfia_level=4,
        confidence=confidence,
        reasoning="Cloud migration maps to CLOP L4",
        evidence_segments=[EvidenceSegment(start_time=10.0, end_time=20.0)],
    )


async def test_generate_produces_dual_tokens() -> None:
    persistence = AsyncMock()
    gen = ReportGenerator(persistence=persistence, base_url="https://voice.example.com")

    claims = [_make_claim(0.8), _make_claim(0.6)]
    result_obj = ClaimExtractionResult(session_id="s1", claims=claims, total_claims=2)
    report = await gen.generate("s1", result_obj, "Alice Smith")

    assert report.expert_review_token != report.supervisor_review_token
    assert len(report.expert_review_token) == _NANOID_LENGTH
    assert len(report.supervisor_review_token) == _NANOID_LENGTH
    # Tokens use the expected alphabet only
    for ch in report.expert_review_token + report.supervisor_review_token:
        assert ch in _NANOID_ALPHABET


async def test_generate_constructs_correct_urls() -> None:
    persistence = AsyncMock()
    gen = ReportGenerator(persistence=persistence, base_url="https://voice.example.com/")

    result_obj = ClaimExtractionResult(session_id="s2", claims=[_make_claim()], total_claims=1)
    report = await gen.generate("s2", result_obj, "Bob Jones")

    assert report.expert_review_url == f"https://voice.example.com/review/expert/{report.expert_review_token}"
    assert report.supervisor_review_url == f"https://voice.example.com/review/supervisor/{report.supervisor_review_token}"


async def test_generate_computes_mean_confidence() -> None:
    persistence = AsyncMock()
    gen = ReportGenerator(persistence=persistence, base_url="https://example.com")

    claims = [_make_claim(0.8), _make_claim(0.6)]
    result_obj = ClaimExtractionResult(session_id="s3", claims=claims, total_claims=2)
    report = await gen.generate("s3", result_obj, "Carol")

    assert report.overall_confidence == pytest.approx(0.7)


async def test_generate_zero_confidence_for_no_claims() -> None:
    persistence = AsyncMock()
    gen = ReportGenerator(persistence=persistence, base_url="https://example.com")

    result_obj = ClaimExtractionResult(session_id="s4", claims=[], total_claims=0)
    report = await gen.generate("s4", result_obj, "Dave")

    assert report.overall_confidence == 0.0


async def test_generate_expiry_is_30_days() -> None:
    persistence = AsyncMock()
    gen = ReportGenerator(persistence=persistence, base_url="https://example.com")

    before = datetime.now(timezone.utc)
    result_obj = ClaimExtractionResult(session_id="s5", claims=[], total_claims=0)
    report = await gen.generate("s5", result_obj, "Eve")
    after = datetime.now(timezone.utc)

    expected_min = before + timedelta(days=29, hours=23)
    expected_max = after + timedelta(days=30, hours=1)
    assert expected_min <= report.expires_at <= expected_max


async def test_generate_calls_persistence_save_report() -> None:
    persistence = AsyncMock()
    gen = ReportGenerator(persistence=persistence, base_url="https://example.com")

    claims = [_make_claim()]
    result_obj = ClaimExtractionResult(session_id="s6", claims=claims, total_claims=1)
    await gen.generate("s6", result_obj, "Frank")

    persistence.save_report.assert_awaited_once()
    kwargs = persistence.save_report.call_args.kwargs
    assert kwargs["session_id"] == "s6"
    assert "expert_review_token" in kwargs
    assert "supervisor_review_token" in kwargs
    assert len(kwargs["claims"]) == 1


async def test_generate_sets_awaiting_expert_status() -> None:
    persistence = AsyncMock()
    gen = ReportGenerator(persistence=persistence, base_url="https://example.com")

    result_obj = ClaimExtractionResult(session_id="s7", claims=[], total_claims=0)
    report = await gen.generate("s7", result_obj, "Grace")

    assert report.status == "awaiting_expert"
