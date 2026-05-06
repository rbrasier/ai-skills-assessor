"""MockInterviewRunner — orchestrates a complete mock assessment interview.

Wires together:
  CandidateBot → MockFlowDriver → SfiaFlowController → TranscriptRecorder
  → PostCallPipeline (ClaimExtractor + ReportGenerator) → MockInterviewResult
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from dataclasses import dataclass, field

from src.adapters.anthropic_claim_llm_provider import AnthropicClaimLLMProvider
from src.adapters.in_memory_persistence import InMemoryPersistence
from src.domain.models.assessment import AssessmentSession, AssessmentStatus
from src.domain.models.claim import AssessmentReport
from src.domain.ports.knowledge_base import IKnowledgeBase
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
    using_real_rag: bool = field(default=False)


async def _build_knowledge_base(database_url: str) -> tuple[IKnowledgeBase, object]:
    """Return (knowledge_base, pool_or_None).

    Uses PgVectorKnowledgeBase when DATABASE_URL is set and SFIA vectors
    exist in framework_skill_levels. Falls back to StubKnowledgeBase silently.
    query_by_skill_code() — the only method the flow controller needs during
    the interview — does not require an embedder.
    """
    if not database_url:
        return StubKnowledgeBase(), None

    try:
        import asyncpg

        from src.adapters.pgvector_knowledge_base import PgVectorKnowledgeBase

        pool = await asyncpg.create_pool(database_url)
        try:
            async with pool.acquire() as conn:
                count = await conn.fetchval(
                    "SELECT COUNT(*) FROM framework_skill_levels"
                    " WHERE embedding IS NOT NULL"
                )
        except Exception:
            await pool.close()
            logger.info(
                "MockInterviewRunner: framework_skill_levels not available"
                " — using StubKnowledgeBase"
            )
            return StubKnowledgeBase(), None

        if count and count > 0:
            logger.info(
                "MockInterviewRunner: using PgVectorKnowledgeBase (%d SFIA vectors)", count
            )
            return PgVectorKnowledgeBase(db_pool=pool), pool

        await pool.close()
        logger.info(
            "MockInterviewRunner: no SFIA vectors in database — using StubKnowledgeBase"
        )
        return StubKnowledgeBase(), None

    except Exception as exc:
        logger.warning(
            "MockInterviewRunner: could not connect for RAG (%s) — using StubKnowledgeBase",
            exc,
        )
        return StubKnowledgeBase(), None


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
        persona: Candidate configuration (role, sfia_level, approach, model).
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

    database_url = os.environ.get("DATABASE_URL", "")
    kb, kb_pool = await _build_knowledge_base(database_url)
    using_real_rag = kb_pool is not None

    try:
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
            "MockInterviewRunner: starting session %s (role=%r sfia=%d approach=%r rag=%s)",
            session_id,
            persona.role,
            persona.sfia_level,
            persona.approach,
            "pgvector" if using_real_rag else "stub",
        )

        await driver.run(controller, recorder, persistence=persistence, session_id=session_id)
        elapsed = time.monotonic() - start
        turn_count = recorder.turn_count

        await recorder.finalize(
            session_id,
            persistence,
            identified_skills=controller.identified_skills,
            recording_duration_seconds=int(round(elapsed)),
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

    finally:
        if kb_pool is not None:
            close = getattr(kb_pool, "close", None)
            if callable(close):
                await close()

    return MockInterviewResult(
        session_id=session_id,
        persona=persona,
        transcript=recorder.to_dict(),
        report=report,
        turn_count=turn_count,
        elapsed_seconds=elapsed,
        using_real_rag=using_real_rag,
    )


__all__ = ["MockInterviewResult", "run_mock_interview"]
