"""Unit tests for SfiaFlowController handlers.

Tests the state machine logic by calling handler methods directly —
no Pipecat or pipecat-ai-flows imports needed. The node-builder methods
(get_initial_node, _build_*_node) require pipecat-ai-flows and are skipped
in the lean CI environment.

Handler contract:
  Each handler receives (args: dict, flow_manager: Any) and returns
  (result, next_node_config | None). The test doubles use None as the
  flow_manager since handlers don't call it directly.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.ports.knowledge_base import IKnowledgeBase, SkillDefinition
from src.domain.services.transcript_recorder import TranscriptRecorder
from src.flows.sfia_flow_controller import SfiaFlowController

pytestmark = pytest.mark.asyncio

_MOCK_FM: Any = None  # flow_manager is unused in handlers; pass None

_STUB_SYSTEM_PROMPT = "You are a test assessor."


def _make_null_knowledge_base() -> IKnowledgeBase:
    """Return a knowledge base stub that always returns an empty list."""
    kb = MagicMock(spec=IKnowledgeBase)
    kb.query_by_skill_code = AsyncMock(return_value=[])
    kb.query = AsyncMock(return_value=[])
    return kb


def _make_controller(
    on_call_ended: Any = None,
    knowledge_base: IKnowledgeBase | None = None,
) -> tuple[SfiaFlowController, TranscriptRecorder]:
    recorder = TranscriptRecorder()
    if on_call_ended is None:
        on_call_ended = AsyncMock()
    if knowledge_base is None:
        knowledge_base = _make_null_knowledge_base()
    controller = SfiaFlowController(
        recorder=recorder,
        on_call_ended=on_call_ended,
        system_prompt=_STUB_SYSTEM_PROMPT,
        knowledge_base=knowledge_base,
    )
    return controller, recorder


# ─── consent_given ────────────────────────────────────────────────────────────


async def test_consent_given_transitions_phase_to_skill_discovery() -> None:
    controller, recorder = _make_controller()
    result, _next_node = await controller.handle_consent_given({}, _MOCK_FM)

    assert recorder.current_phase == "skill_discovery"
    assert result is None


# ─── consent_declined ─────────────────────────────────────────────────────────


async def test_consent_declined_transitions_phase_to_closing() -> None:
    controller, recorder = _make_controller()
    result, _next_node = await controller.handle_consent_declined({}, _MOCK_FM)

    assert recorder.current_phase == "closing"
    assert result is None


# ─── skills_identified ────────────────────────────────────────────────────────


async def test_skills_identified_stores_skills() -> None:
    controller, recorder = _make_controller()
    skills = [
        {"skill_code": "PROG", "skill_name": "Programming"},
        {"skill_code": "DENG", "skill_name": "Data Engineering"},
    ]
    await controller.handle_skills_identified({"skills": skills}, _MOCK_FM)

    assert controller.identified_skills == skills


async def test_skills_identified_transitions_phase_to_evidence_gathering() -> None:
    controller, recorder = _make_controller()
    await controller.handle_skills_identified({"skills": []}, _MOCK_FM)

    assert recorder.current_phase == "evidence_gathering"


async def test_skills_identified_with_empty_list() -> None:
    controller, recorder = _make_controller()
    result, _next_node = await controller.handle_skills_identified({"skills": []}, _MOCK_FM)

    assert controller.identified_skills == []
    assert result is None


async def test_skills_identified_missing_key_defaults_to_empty() -> None:
    controller, recorder = _make_controller()
    await controller.handle_skills_identified({}, _MOCK_FM)

    assert controller.identified_skills == []


# ─── evidence_complete ────────────────────────────────────────────────────────


async def test_evidence_complete_transitions_phase_to_summary() -> None:
    controller, recorder = _make_controller()
    result, _next_node = await controller.handle_evidence_complete({}, _MOCK_FM)

    assert recorder.current_phase == "summary"
    assert result is None


# ─── summary_complete ─────────────────────────────────────────────────────────


async def test_summary_complete_transitions_phase_to_closing() -> None:
    controller, recorder = _make_controller()
    result, _next_node = await controller.handle_summary_complete({}, _MOCK_FM)

    assert recorder.current_phase == "closing"
    assert result is None


# ─── call_ended ───────────────────────────────────────────────────────────────


async def test_call_ended_invokes_on_call_ended_callback() -> None:
    callback = AsyncMock()
    controller, _ = _make_controller(on_call_ended=callback)
    result, next_node = await controller.handle_end_call({}, _MOCK_FM)

    callback.assert_awaited_once()
    assert result is None
    assert next_node is None


async def test_call_ended_with_sync_callback() -> None:
    called: list[bool] = []

    def sync_callback() -> None:
        called.append(True)

    controller, _ = _make_controller(on_call_ended=sync_callback)
    await controller.handle_end_call({}, _MOCK_FM)

    assert called == [True]


async def test_call_ended_callback_exception_is_swallowed() -> None:
    async def boom() -> None:
        raise RuntimeError("explode")

    controller, _ = _make_controller(on_call_ended=boom)
    # Must not raise
    await controller.handle_end_call({}, _MOCK_FM)


# ─── Full state machine sequence ─────────────────────────────────────────────


async def test_full_flow_phase_sequence() -> None:
    """Walk through all 5 phases and verify phase label at each step."""
    callback = AsyncMock()
    controller, recorder = _make_controller(on_call_ended=callback)

    assert recorder.current_phase == "introduction"

    await controller.handle_consent_given({}, _MOCK_FM)
    assert recorder.current_phase == "skill_discovery"

    await controller.handle_skills_identified(
        {"skills": [{"skill_code": "PROG", "skill_name": "Programming"}]}, _MOCK_FM
    )
    assert recorder.current_phase == "evidence_gathering"

    await controller.handle_evidence_complete({}, _MOCK_FM)
    assert recorder.current_phase == "summary"

    await controller.handle_summary_complete({}, _MOCK_FM)
    assert recorder.current_phase == "closing"

    await controller.handle_end_call({}, _MOCK_FM)
    callback.assert_awaited_once()


async def test_identified_skills_are_immutable_copy() -> None:
    controller, _ = _make_controller()
    skills = [{"skill_code": "PROG", "skill_name": "Programming"}]
    await controller.handle_skills_identified({"skills": skills}, _MOCK_FM)

    # Mutating the returned property should not affect internal state
    copy = controller.identified_skills
    copy.append({"skill_code": "HACK", "skill_name": "Hacking"})
    assert len(controller.identified_skills) == 1


# ─── RAG context injection ────────────────────────────────────────────────────


async def test_skills_identified_queries_knowledge_base_per_skill() -> None:
    kb = _make_null_knowledge_base()
    controller, _ = _make_controller(knowledge_base=kb)
    skills = [
        {"skill_code": "PROG", "skill_name": "Programming"},
        {"skill_code": "DENG", "skill_name": "Data Engineering"},
    ]
    await controller.handle_skills_identified({"skills": skills}, _MOCK_FM)

    assert kb.query_by_skill_code.call_count == 2
    codes_queried = {
        call.kwargs["skill_code"] for call in kb.query_by_skill_code.call_args_list
    }
    assert codes_queried == {"PROG", "DENG"}


async def test_skills_identified_rag_context_empty_when_kb_returns_nothing() -> None:
    controller, _ = _make_controller()
    await controller.handle_skills_identified(
        {"skills": [{"skill_code": "PROG", "skill_name": "Programming"}]}, _MOCK_FM
    )
    assert controller._rag_context == ""


async def test_skills_identified_rag_context_populated_from_kb_results() -> None:
    result = SkillDefinition(
        skill_code="PROG",
        skill_name="Programming",
        category="Development",
        subcategory=None,
        level=4,
        content="Level 4 description of PROG",
        similarity=None,
        framework_type="sfia-9",
    )
    kb = _make_null_knowledge_base()
    kb.query_by_skill_code = AsyncMock(return_value=[result])

    controller, _ = _make_controller(knowledge_base=kb)
    await controller.handle_skills_identified(
        {"skills": [{"skill_code": "PROG", "skill_name": "Programming"}]}, _MOCK_FM
    )

    assert "PROG" in controller._rag_context
    assert "Programming" in controller._rag_context
    assert "Level 4 description of PROG" in controller._rag_context


async def test_skills_identified_rag_failure_is_swallowed() -> None:
    kb = _make_null_knowledge_base()
    kb.query_by_skill_code = AsyncMock(side_effect=RuntimeError("DB down"))

    controller, recorder = _make_controller(knowledge_base=kb)
    result, _ = await controller.handle_skills_identified(
        {"skills": [{"skill_code": "PROG", "skill_name": "Programming"}]}, _MOCK_FM
    )

    assert result is None
    assert controller._rag_context == ""
    assert recorder.current_phase == "evidence_gathering"
