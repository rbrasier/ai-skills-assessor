"""MockInterviewRunner — orchestrates a complete mock assessment interview.

Wires together:
  CandidateBot → MockFlowDriver → SfiaFlowController → TranscriptRecorder
  → PostCallPipeline (ClaimExtractor + ReportGenerator) → MockInterviewResult
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass

from src.adapters.anthropic_claim_llm_provider import AnthropicClaimLLMProvider
from src.adapters.in_memory_persistence import InMemoryPersistence
from src.domain.models.assessment import AssessmentSession, AssessmentStatus
from src.domain.models.claim import AssessmentReport
from src.domain.ports.persistence import IPersistence
from src.domain.services.claim_extractor import ClaimExtractor
from src.domain.services.post_call_pipeline import PostCallPipeline
from src.domain.services.report_generator import ReportGenerator
from src.domain.services.transcript_recorder import TranscriptRecorder
from src.flows.sfia_flow_controller import _FALLBACK_SYSTEM_PROMPT, SfiaFlowController
from src.testing.candidate_bot import CandidateBot, CandidatePersona
from src.testing.mock_flow_driver import MockFlowDriver, StubKnowledgeBase

logger = logging.getLogger(__name__)


@dataclass
class MockInterviewResult:
    session_id: str
    persona: CandidatePersona
    transcript: dict
    report: AssessmentReport
    turn_count: int
    elapsed_seconds: float


async def run_mock_interview(
    persona: CandidatePersona,
    api_key: str,
    noa_model: str | None = None,
    post_call_model: str = "claude-sonnet-4-6",
    max_turns: int = 40,
    print_dialog: bool = False,
    persistence: IPersistence | None = None,
    base_url: str = "http://localhost",
) -> MockInterviewResult:
    """Run a complete mock interview and return the result.

    Args:
        persona: Candidate configuration (role, sfia_level, honesty, model).
        api_key: Anthropic API key.
        noa_model: Model for the Noa interviewer. Defaults to persona.model.
        post_call_model: Model for claim extraction.
        max_turns: Safety cap on conversation turns.
        persistence: Persistence adapter. Defaults to InMemoryPersistence.
            Pass a PostgresPersistence instance to write mock runs to the
            real database so they appear in the admin dashboard.
        base_url: Base URL used when building review links in the report.
    """
    if noa_model is None:
        noa_model = persona.model

    session_id = str(uuid.uuid4())
    if persistence is None:
        persistence = InMemoryPersistence()
    kb = StubKnowledgeBase()

    # Ensure a candidate row exists before creating the session (required by
    # the foreign-key constraint in Postgres; a no-op for InMemoryPersistence).
    await persistence.get_or_create_candidate(
        email="mock@test.local",
        first_name="Mock",
        last_name="Candidate",
        employee_id="MOCK-001",
    )

    # Seed a minimal session record so PostCallPipeline.process() can find it.
    await persistence.create_session(
        AssessmentSession(
            id=session_id,
            candidate_id="mock@test.local",
            phone_number="",
            status=AssessmentStatus.IN_PROGRESS,
            candidate_name="Mock Candidate",
        )
    )

    recorder = TranscriptRecorder()
    candidate_bot = CandidateBot(persona=persona, api_key=api_key)

    controller = SfiaFlowController(
        recorder=recorder,
        on_call_ended=lambda: None,
        system_prompt=_FALLBACK_SYSTEM_PROMPT,
        knowledge_base=kb,
        session_id=session_id,
        post_call_pipeline=None,  # driven manually below
    )

    driver = MockFlowDriver(
        noa_model=noa_model,
        candidate_bot=candidate_bot,
        api_key=api_key,
        max_turns=max_turns,
        print_dialog=print_dialog,
    )

    start = time.monotonic()
    logger.info(
        "MockInterviewRunner: starting session %s (role=%r sfia=%d honesty=%d)",
        session_id,
        persona.role,
        persona.sfia_level,
        persona.honesty,
    )

    await driver.run(controller, recorder, persistence=persistence, session_id=session_id)
    elapsed = time.monotonic() - start
    turn_count = recorder.turn_count

    await recorder.finalize(
        session_id,
        persistence,
        identified_skills=controller.identified_skills,
    )

    pipeline = PostCallPipeline(
        claim_extractor=ClaimExtractor(
            llm_provider=AnthropicClaimLLMProvider(
                api_key=api_key,
                model=post_call_model,
            ),
            knowledge_base=kb,
        ),
        report_generator=ReportGenerator(
            persistence=persistence,
            base_url=base_url,
        ),
        persistence=persistence,
    )

    logger.info("MockInterviewRunner: running PostCallPipeline for session %s", session_id)
    report = await pipeline.process(session_id)

    logger.info(
        "MockInterviewRunner: done — %d turns, %.1fs, %d claims",
        turn_count,
        elapsed,
        report.total_claims,
    )

    return MockInterviewResult(
        session_id=session_id,
        persona=persona,
        transcript=recorder.to_dict(),
        report=report,
        turn_count=turn_count,
        elapsed_seconds=elapsed,
    )


__all__ = ["MockInterviewResult", "run_mock_interview"]
