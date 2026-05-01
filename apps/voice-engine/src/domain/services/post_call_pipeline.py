"""PostCallPipeline — orchestrates post-call claim extraction (Phase 6).

Retrieves the transcript, extracts and maps claims, generates a report,
updates the session status to 'processed', and optionally notifies the SME.

Called as an asyncio background task from SfiaFlowController.handle_end_call().
"""

from __future__ import annotations

import logging

from src.domain.models.claim import AssessmentReport
from src.domain.ports.notification_sender import INotificationSender
from src.domain.ports.persistence import IPersistence
from src.domain.services.claim_extractor import ClaimExtractor
from src.domain.services.report_generator import ReportGenerator

logger = logging.getLogger(__name__)


class PostCallPipeline:
    def __init__(
        self,
        claim_extractor: ClaimExtractor,
        report_generator: ReportGenerator,
        persistence: IPersistence,
        notification_sender: INotificationSender | None = None,
    ) -> None:
        self.claim_extractor = claim_extractor
        self.report_generator = report_generator
        self.persistence = persistence
        self.notification_sender = notification_sender

    async def process(self, session_id: str) -> AssessmentReport:
        """Full post-call pipeline.

        1. Retrieve session and transcript from assessment_sessions.
        2. Extract and enrich claims via LLM + RAG.
        3. Generate report with NanoID review token.
        4. Persist report columns to assessment_sessions.
        5. Update session status to 'processed'.
        6. Optionally notify SME (stub in Phase 6; fully wired in Phase 7).
        """
        session = await self.persistence.get_session(session_id)
        transcript_json = await self.persistence.get_transcript(session_id)

        if transcript_json is None:
            raise ValueError(f"No transcript found for session {session_id}")

        extraction_result = await self.claim_extractor.process_transcript(
            session_id=session_id,
            transcript_json=transcript_json,
        )

        candidate_name = (
            (session.candidate_name or "").strip() if session else ""
        ) or "Unknown Candidate"

        report = await self.report_generator.generate(
            session_id=session_id,
            extraction_result=extraction_result,
            candidate_name=candidate_name,
        )

        await self.persistence.update_session_status(session_id, "processed")

        if self.notification_sender and session and getattr(session, "sme_email", None):
            try:
                await self.notification_sender.send_review_link(
                    sme_email=session.sme_email,  # type: ignore[attr-defined]
                    review_url=report.review_url,
                    candidate_name=candidate_name,
                )
            except Exception:
                logger.exception(
                    "PostCallPipeline: notification failed for session %s",
                    session_id,
                )

        return report


__all__ = ["PostCallPipeline"]
