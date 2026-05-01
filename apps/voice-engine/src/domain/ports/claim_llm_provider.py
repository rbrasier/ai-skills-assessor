"""``IClaimLLMProvider`` port — LLM abstraction for post-call claim extraction.

Separate from the in-call ``ILLMProvider`` (which has ``complete()``) to keep
interface segregation: voice transports don't need extraction methods, and the
post-call pipeline doesn't need conversational completion.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.models.claim import Claim
from src.domain.ports.knowledge_base import SkillDefinition


class IClaimLLMProvider(ABC):

    @abstractmethod
    async def extract_claims(self, transcript_text: str) -> list[Claim]:
        """Extract discrete verifiable work claims from formatted transcript text.

        Args:
            transcript_text: Transcript formatted as "[MM:SS] SPEAKER: text" lines.

        Returns:
            Claims with verbatim_quote, interpreted_claim, and evidence_segments
            populated. sfia_* fields are empty strings / defaults at this stage.
        """
        ...

    @abstractmethod
    async def map_claim_to_skill(
        self,
        claim: Claim,
        skill_definitions: list[SkillDefinition],
    ) -> Claim:
        """Enrich a claim with SFIA skill code, level, confidence, and reasoning.

        Args:
            claim: Claim from extract_claims() with evidence_segments populated.
            skill_definitions: Candidate SFIA definitions from IKnowledgeBase.query().

        Returns:
            Enriched Claim with sfia_skill_code, sfia_skill_name, sfia_level,
            confidence, and reasoning filled in.
        """
        ...


__all__ = ["IClaimLLMProvider"]
