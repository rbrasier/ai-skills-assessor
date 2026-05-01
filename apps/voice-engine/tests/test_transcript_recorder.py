"""Unit tests for TranscriptRecorder.

All tests run in the lean CI install (no Pipecat [voice] extras needed).
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock

import pytest

from src.domain.services.transcript_recorder import TranscriptRecorder

pytestmark = pytest.mark.asyncio


# ─── Phase tracking ───────────────────────────────────────────────────────────


def test_initial_phase_is_introduction() -> None:
    recorder = TranscriptRecorder()
    assert recorder.current_phase == "introduction"


def test_set_phase_updates_phase() -> None:
    recorder = TranscriptRecorder()
    recorder.set_phase("skill_discovery")
    assert recorder.current_phase == "skill_discovery"


def test_subsequent_turns_use_updated_phase() -> None:
    recorder = TranscriptRecorder()
    recorder.record_turn(speaker="bot", text="Hello.")
    recorder.set_phase("skill_discovery")
    recorder.record_turn(speaker="candidate", text="I do cloud work.")

    turns = recorder.to_dict()["turns"]
    assert turns[0]["phase"] == "introduction"
    assert turns[1]["phase"] == "skill_discovery"


# ─── Turn accumulation ────────────────────────────────────────────────────────


def test_record_turn_appends_with_correct_fields() -> None:
    recorder = TranscriptRecorder()
    before = time.time()
    recorder.record_turn(speaker="bot", text="Hi, I'm Noa.", vad_confidence=None)
    after = time.time()

    assert recorder.turn_count == 1
    turns = recorder.to_dict()["turns"]
    t = turns[0]
    assert t["speaker"] == "bot"
    assert t["text"] == "Hi, I'm Noa."
    assert t["phase"] == "introduction"
    assert t["vad_confidence"] is None
    assert before <= t["timestamp"] <= after


def test_blank_text_is_not_recorded() -> None:
    recorder = TranscriptRecorder()
    recorder.record_turn(speaker="candidate", text="   ")
    assert recorder.turn_count == 0


def test_vad_confidence_is_stored() -> None:
    recorder = TranscriptRecorder()
    recorder.record_turn(speaker="candidate", text="Yes I agree.", vad_confidence=0.93)
    turns = recorder.to_dict()["turns"]
    assert turns[0]["vad_confidence"] == pytest.approx(0.93)


def test_multiple_turns_accumulate_in_order() -> None:
    recorder = TranscriptRecorder()
    recorder.record_turn(speaker="bot", text="Hello.")
    recorder.record_turn(speaker="candidate", text="Hi there.")
    recorder.record_turn(speaker="bot", text="Great, let's begin.")

    turns = recorder.to_dict()["turns"]
    assert len(turns) == 3
    assert [t["speaker"] for t in turns] == ["bot", "candidate", "bot"]


# ─── Serialisation ────────────────────────────────────────────────────────────


def test_to_dict_structure() -> None:
    recorder = TranscriptRecorder()
    recorder.record_turn(speaker="bot", text="Hello.")
    result = recorder.to_dict()

    assert "turns" in result
    assert isinstance(result["turns"], list)
    assert len(result["turns"]) == 1


def test_snippet_is_truncated_at_500_chars() -> None:
    recorder = TranscriptRecorder()
    long_text = "A" * 600
    recorder.record_turn(speaker="bot", text=long_text)
    assert len(recorder.snippet()) == 500


def test_snippet_empty_when_no_turns() -> None:
    recorder = TranscriptRecorder()
    assert recorder.snippet() == ""


# ─── Finalize ────────────────────────────────────────────────────────────────


async def test_finalize_calls_save_transcript() -> None:
    """Phase 6: finalize() writes to transcript_json column via save_transcript()."""
    recorder = TranscriptRecorder()
    recorder.record_turn(speaker="bot", text="Hello.")

    persistence = AsyncMock()
    await recorder.finalize(
        session_id="sess-123",
        persistence=persistence,
        identified_skills=[{"skill_code": "PROG", "skill_name": "Programming"}],
        recording_duration_seconds=120,
    )

    # save_transcript must be called with the transcript dict
    persistence.save_transcript.assert_awaited_once_with(
        "sess-123",
        {"turns": [{"timestamp": persistence.save_transcript.call_args[0][1]["turns"][0]["timestamp"],
                    "speaker": "bot", "text": "Hello.", "phase": "introduction",
                    "vad_confidence": None}]},
    )

    # merge_session_metadata must be called for identified_skills + duration
    persistence.merge_session_metadata.assert_awaited_once()
    call_args = persistence.merge_session_metadata.call_args
    assert call_args[0][0] == "sess-123"
    metadata = call_args[0][1]
    assert metadata["identified_skills"] == [{"skill_code": "PROG", "skill_name": "Programming"}]
    assert metadata["recording_duration_seconds"] == 120
    # transcript_json must NOT be in the metadata dict (it's saved separately)
    assert "transcript_json" not in metadata


async def test_finalize_without_optional_fields() -> None:
    recorder = TranscriptRecorder()
    recorder.record_turn(speaker="bot", text="Hi.")

    persistence = AsyncMock()
    await recorder.finalize("sess-456", persistence)

    # save_transcript called
    persistence.save_transcript.assert_awaited_once()
    # merge_session_metadata NOT called — no optional fields
    persistence.merge_session_metadata.assert_not_awaited()


async def test_finalize_swallows_save_transcript_errors() -> None:
    recorder = TranscriptRecorder()
    recorder.record_turn(speaker="bot", text="Hi.")

    persistence = AsyncMock()
    persistence.save_transcript.side_effect = RuntimeError("DB down")

    # Should not raise
    await recorder.finalize("sess-789", persistence)


async def test_finalize_swallows_merge_metadata_errors() -> None:
    recorder = TranscriptRecorder()
    recorder.record_turn(speaker="bot", text="Hi.")

    persistence = AsyncMock()
    persistence.merge_session_metadata.side_effect = RuntimeError("DB down")

    # Should not raise — identified_skills triggers the merge call
    await recorder.finalize("sess-789", persistence, identified_skills=[])
