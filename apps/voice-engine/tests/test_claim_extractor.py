"""Unit tests for ClaimExtractor.

Uses mocked IClaimLLMProvider and IKnowledgeBase — no LLM or DB required.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.models.claim import Claim, EvidenceSegment
from src.domain.services.claim_extractor import ClaimExtractor

pytestmark = pytest.mark.asyncio

_TRANSCRIPT_JSON = {
    "turns": [
        {"timestamp": 1000.0, "speaker": "bot", "text": "Tell me about your role.", "phase": "skill_discovery", "vad_confidence": None},
        {"timestamp": 1010.0, "speaker": "candidate", "text": "I lead a team of 5 engineers.", "phase": "skill_discovery", "vad_confidence": 0.9},
        {"timestamp": 1025.0, "speaker": "candidate", "text": "I built the CI/CD pipeline.", "phase": "evidence_gathering", "vad_confidence": 0.95},
    ]
}


def _make_claim(**kwargs: object) -> Claim:
    defaults = dict(
        verbatim_quote="I built the CI/CD pipeline.",
        interpreted_claim="Candidate designed and implemented a CI/CD pipeline.",
        sfia_skill_code="ITOP",
        sfia_skill_name="IT Infrastructure",
        sfia_level=4,
        confidence=0.85,
        reasoning="CI/CD maps to ITOP level 4",
        evidence_segments=[EvidenceSegment(start_time=25.0, end_time=30.0)],
    )
    defaults.update(kwargs)
    return Claim(**defaults)  # type: ignore[arg-type]


async def test_extract_returns_mapped_claims() -> None:
    raw_claim = _make_claim(sfia_skill_code="", sfia_skill_name="", sfia_level=1, confidence=0.0, reasoning="")
    mapped_claim = _make_claim()

    llm = AsyncMock()
    llm.extract_claims.return_value = [raw_claim]
    llm.map_claim_to_skill.return_value = mapped_claim

    kb = AsyncMock()
    kb.query.return_value = []

    extractor = ClaimExtractor(llm_provider=llm, knowledge_base=kb)
    result = await extractor.process_transcript("sess-1", _TRANSCRIPT_JSON)

    assert result.session_id == "sess-1"
    assert result.total_claims == 1
    assert result.claims[0].sfia_skill_code == "ITOP"
    llm.extract_claims.assert_awaited_once()
    llm.map_claim_to_skill.assert_awaited_once()
    kb.query.assert_awaited_once()


async def test_empty_transcript_returns_empty_result() -> None:
    llm = AsyncMock()
    llm.extract_claims.return_value = []
    kb = AsyncMock()

    extractor = ClaimExtractor(llm_provider=llm, knowledge_base=kb)
    result = await extractor.process_transcript("sess-2", {"turns": []})

    assert result.total_claims == 0
    assert result.claims == []
    kb.query.assert_not_awaited()


async def test_mapping_failure_skips_claim() -> None:
    raw_claim = _make_claim(sfia_skill_code="", confidence=0.0, reasoning="")
    llm = AsyncMock()
    llm.extract_claims.return_value = [raw_claim]
    llm.map_claim_to_skill.side_effect = RuntimeError("LLM error")

    kb = AsyncMock()
    kb.query.return_value = []

    extractor = ClaimExtractor(llm_provider=llm, knowledge_base=kb)
    result = await extractor.process_transcript("sess-3", _TRANSCRIPT_JSON)

    assert result.total_claims == 0


def test_format_transcript_timestamps() -> None:
    extractor = ClaimExtractor(llm_provider=MagicMock(), knowledge_base=MagicMock())
    result = extractor._format_transcript(_TRANSCRIPT_JSON)

    lines = result.split("\n")
    assert lines[0].startswith("[00:00] NOA:")
    assert lines[1].startswith("[00:10] CANDIDATE:")
    assert lines[2].startswith("[00:25] CANDIDATE:")


def test_format_empty_transcript_returns_empty_string() -> None:
    extractor = ClaimExtractor(llm_provider=MagicMock(), knowledge_base=MagicMock())
    assert extractor._format_transcript({"turns": []}) == ""
