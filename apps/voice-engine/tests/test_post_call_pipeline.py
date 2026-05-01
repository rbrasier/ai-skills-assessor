"""Unit tests for PostCallPipeline.

Uses InMemoryPersistence plus mocked ClaimExtractor and ReportGenerator
to verify the pipeline orchestration without requiring LLM or DB.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from src.adapters.in_memory_persistence import InMemoryPersistence
from src.domain.models.assessment import AssessmentSession, AssessmentStatus
from src.domain.models.claim import AssessmentReport, ClaimExtractionResult
from src.domain.services.post_call_pipeline import PostCallPipeline

pytestmark = pytest.mark.asyncio

_SESSION_ID = "test-session-001"
_TRANSCRIPT_JSON = {
    "turns": [
        {"timestamp": 1000.0, "speaker": "bot", "text": "Hello.", "phase": "introduction", "vad_confidence": None},
        {"timestamp": 1010.0, "speaker": "candidate", "text": "I led migrations.", "phase": "evidence_gathering", "vad_confidence": 0.9},
    ]
}


def _make_session() -> AssessmentSession:
    return AssessmentSession(
        id=_SESSION_ID,
        candidate_id="alice@example.com",
        phone_number="+61400000001",
        status=AssessmentStatus.COMPLETED,
        candidate_name="Alice Smith",
    )


def _make_report(session_id: str = _SESSION_ID) -> AssessmentReport:
    return AssessmentReport(
        session_id=session_id,
        expert_review_token="EXPERT01234567890AB",
        supervisor_review_token="SUPER01234567890AB",
        expert_review_url="https://example.com/review/expert/EXPERT01234567890AB",
        supervisor_review_url="https://example.com/review/supervisor/SUPER01234567890AB",
        candidate_name="Alice Smith",
        claims=[],
        total_claims=0,
        overall_confidence=0.0,
        generated_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(days=30),
    )


async def test_pipeline_full_flow() -> None:
    persistence = InMemoryPersistence()
    session = _make_session()
    await persistence.create_session(session)
    await persistence.save_transcript(_SESSION_ID, _TRANSCRIPT_JSON)

    claim_extractor = AsyncMock()
    claim_extractor.process_transcript.return_value = ClaimExtractionResult(
        session_id=_SESSION_ID, claims=[], total_claims=0
    )

    report_generator = AsyncMock()
    expected_report = _make_report()
    report_generator.generate.return_value = expected_report

    pipeline = PostCallPipeline(
        claim_extractor=claim_extractor,
        report_generator=report_generator,
        persistence=persistence,
    )
    report = await pipeline.process(_SESSION_ID)

    assert report.session_id == _SESSION_ID
    claim_extractor.process_transcript.assert_awaited_once_with(
        session_id=_SESSION_ID,
        transcript_json=_TRANSCRIPT_JSON,
    )
    report_generator.generate.assert_awaited_once()

    # Status should be updated to 'processed'
    updated = await persistence.get_session(_SESSION_ID)
    assert updated is not None
    assert updated.status == AssessmentStatus.PROCESSED


async def test_pipeline_raises_on_missing_transcript() -> None:
    persistence = InMemoryPersistence()
    session = _make_session()
    await persistence.create_session(session)
    # No transcript saved

    pipeline = PostCallPipeline(
        claim_extractor=AsyncMock(),
        report_generator=AsyncMock(),
        persistence=persistence,
    )
    with pytest.raises(ValueError, match="No transcript"):
        await pipeline.process(_SESSION_ID)


async def test_pipeline_uses_candidate_name_from_session() -> None:
    persistence = InMemoryPersistence()
    session = _make_session()
    await persistence.create_session(session)
    await persistence.save_transcript(_SESSION_ID, _TRANSCRIPT_JSON)

    claim_extractor = AsyncMock()
    claim_extractor.process_transcript.return_value = ClaimExtractionResult(
        session_id=_SESSION_ID, claims=[], total_claims=0
    )

    report_generator = AsyncMock()
    report_generator.generate.return_value = _make_report()

    pipeline = PostCallPipeline(
        claim_extractor=claim_extractor,
        report_generator=report_generator,
        persistence=persistence,
    )
    await pipeline.process(_SESSION_ID)

    generate_kwargs = report_generator.generate.call_args.kwargs
    assert generate_kwargs["candidate_name"] == "Alice Smith"


async def test_pipeline_falls_back_to_unknown_candidate_name() -> None:
    persistence = InMemoryPersistence()
    session = AssessmentSession(
        id=_SESSION_ID,
        candidate_id="bob@example.com",
        phone_number="+61400000002",
        status=AssessmentStatus.COMPLETED,
        candidate_name=None,  # no name stored
    )
    await persistence.create_session(session)
    await persistence.save_transcript(_SESSION_ID, _TRANSCRIPT_JSON)

    claim_extractor = AsyncMock()
    claim_extractor.process_transcript.return_value = ClaimExtractionResult(
        session_id=_SESSION_ID, claims=[], total_claims=0
    )
    report_generator = AsyncMock()
    report_generator.generate.return_value = _make_report()

    pipeline = PostCallPipeline(
        claim_extractor=claim_extractor,
        report_generator=report_generator,
        persistence=persistence,
    )
    await pipeline.process(_SESSION_ID)

    generate_kwargs = report_generator.generate.call_args.kwargs
    assert generate_kwargs["candidate_name"] == "Unknown Candidate"
