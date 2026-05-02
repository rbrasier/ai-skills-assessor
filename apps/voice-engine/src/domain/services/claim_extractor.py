"""ClaimExtractor — post-call claim extraction pipeline (Phase 6).

Pure domain service with no infrastructure imports. Orchestrates the two-pass
LLM pipeline: raw extraction from formatted transcript text, then RAG-enriched
SFIA skill mapping for each claim.
"""

from __future__ import annotations

import logging

from src.domain.models.claim import Claim, ClaimExtractionResult
from src.domain.ports.claim_llm_provider import IClaimLLMProvider
from src.domain.ports.knowledge_base import IKnowledgeBase

logger = logging.getLogger(__name__)


class ClaimExtractor:
    def __init__(
        self,
        llm_provider: IClaimLLMProvider,
        knowledge_base: IKnowledgeBase,
        max_holistic_skills: int = 6,
    ) -> None:
        self.llm = llm_provider
        self.kb = knowledge_base
        self.max_holistic_skills = max_holistic_skills

    async def process_transcript(
        self,
        session_id: str,
        transcript_json: dict,
        framework_type: str = "sfia-9",
    ) -> ClaimExtractionResult:
        """Full extraction pipeline.

        1. Format transcript JSON into readable "[MM:SS] SPEAKER: text" lines.
        2. Extract raw claims (with evidence_segments) from formatted text.
        3. For each claim, query RAG for top-3 relevant SFIA skill definitions.
        4. Map each claim to a skill code, level, and confidence score.
        """
        transcript_text = self._format_transcript(transcript_json)
        raw_claims = await self.llm.extract_claims(transcript_text)

        enriched: list[Claim] = []
        for claim in raw_claims:
            try:
                skill_defs = await self.kb.query(
                    text=claim.interpreted_claim,
                    framework_type=framework_type,
                    top_k=3,
                )
                mapped = await self.llm.map_claim_to_skill(claim, skill_defs)
                mapped = mapped.model_copy(update={"framework_type": framework_type})
                enriched.append(mapped)
            except Exception:
                logger.exception(
                    "ClaimExtractor: failed to map claim for session %s — skipping",
                    session_id,
                )

        holistic = []
        try:
            holistic = await self.llm.analyse_transcript_holistically(
                transcript_text,
                max_skills=self.max_holistic_skills,
            )
        except Exception:
            logger.exception(
                "ClaimExtractor: holistic analysis failed for session %s — skipping",
                session_id,
            )

        logger.info(
            "ClaimExtractor: extracted %d claims, %d holistic profiles for session %s",
            len(enriched),
            len(holistic),
            session_id,
        )
        return ClaimExtractionResult(
            session_id=session_id,
            claims=enriched,
            total_claims=len(enriched),
            holistic_assessment=holistic,
        )

    def _format_transcript(self, transcript_json: dict) -> str:
        """Format transcript turns into '[MM:SS] SPEAKER: text' lines.

        Timestamps are Unix epoch values stored by TranscriptRecorder. Elapsed
        seconds from the first turn are converted to MM:SS display format.
        Evidence segments in LLM output reference these elapsed-seconds values.
        """
        turns = transcript_json.get("turns", [])
        if not turns:
            return ""

        start_time = turns[0]["timestamp"]
        lines = []
        for turn in turns:
            elapsed = turn["timestamp"] - start_time
            mm, ss = int(elapsed // 60), int(elapsed % 60)
            speaker = "NOA" if turn.get("speaker") == "bot" else "CANDIDATE"
            lines.append(f"[{mm:02d}:{ss:02d}] {speaker}: {turn['text']}")

        return "\n".join(lines)


__all__ = ["ClaimExtractor"]
