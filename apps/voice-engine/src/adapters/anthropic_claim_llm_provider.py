"""Anthropic-backed ``IClaimLLMProvider`` adapter (Phase 6).

Uses claude-sonnet-4-6 (or whatever model is injected via
``settings.anthropic_post_call_model``) for post-call claim extraction and
SFIA skill mapping. Separate from ``AnthropicLLMProvider`` which handles
in-call conversational completions.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from src.domain.models.claim import Claim, EvidenceSegment, HolisticSkillProfile
from src.domain.ports.claim_llm_provider import IClaimLLMProvider
from src.domain.ports.knowledge_base import SkillDefinition

logger = logging.getLogger(__name__)

_anthropic_module: Any
try:
    import anthropic as _anthropic_sdk
except ImportError:  # pragma: no cover — lean CI
    _anthropic_module = None
else:
    _anthropic_module = _anthropic_sdk

anthropic: Any = _anthropic_module


class AnthropicClaimLLMProvider(IClaimLLMProvider):
    """Post-call LLM provider using Claude for claim extraction and SFIA mapping."""

    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model
        self._client: Any = None

    def _get_client(self) -> Any:
        if anthropic is None:
            raise RuntimeError(
                "anthropic SDK is not installed; install voice-engine with "
                "`pip install -e .[voice]` to use AnthropicClaimLLMProvider."
            )
        if not self._api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set.")
        if self._client is None:
            self._client = anthropic.AsyncAnthropic(api_key=self._api_key)
        return self._client

    async def extract_claims(self, transcript_text: str) -> list[Claim]:
        client = self._get_client()
        response = await client.messages.create(
            model=self._model,
            max_tokens=8192,
            messages=[{"role": "user", "content": self._extraction_prompt(transcript_text)}],
        )
        raw_text = response.content[0].text
        return self._parse_extraction(raw_text)

    async def map_claim_to_skill(
        self,
        claim: Claim,
        skill_definitions: list[SkillDefinition],
    ) -> Claim:
        client = self._get_client()
        context = "\n\n".join(
            f"--- {sd.skill_name} ({sd.skill_code}) Level {sd.level} ---\n{sd.content}"
            for sd in skill_definitions
        )
        response = await client.messages.create(
            model=self._model,
            max_tokens=1024,
            messages=[{"role": "user", "content": self._mapping_prompt(claim, context)}],
        )
        raw_text = response.content[0].text
        try:
            mapping = json.loads(raw_text)
        except json.JSONDecodeError:
            # Strip markdown code fences if present and retry
            cleaned = raw_text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            mapping = json.loads(cleaned)

        return claim.model_copy(update={
            "sfia_skill_code": mapping["skill_code"],
            "sfia_skill_name": mapping["skill_name"],
            "sfia_level": int(mapping["level"]),
            "confidence": float(mapping["confidence"]),
            "reasoning": mapping["reasoning"],
        })

    def _extraction_prompt(self, transcript_text: str) -> str:
        return f"""Analyse the following skills assessment transcript and extract all discrete, \
verifiable work claims made by the candidate.

A "work claim" is a specific statement about something the candidate has done, managed, \
led, or achieved professionally. General opinions, aspirations, or vague background \
context are NOT claims.

For each claim provide:
1. verbatim_quote: The exact words from the transcript
2. interpreted_claim: A concise, clear restatement of what the candidate is claiming
3. evidence_segments: The timestamp range(s) in the transcript (seconds from call start) \
   that contain this claim. Derive start_time and end_time from the [MM:SS] timestamps \
   shown, converting to total seconds (e.g. [02:15] = 135.0 seconds).

Return ONLY a JSON array, no other text:
[
  {{
    "verbatim_quote": "exact quote",
    "interpreted_claim": "clear interpretation",
    "evidence_segments": [
      {{"start_time": 45.0, "end_time": 67.0}}
    ]
  }}
]

TRANSCRIPT:
---
{transcript_text}
---"""

    def _mapping_prompt(self, claim: Claim, skill_context: str) -> str:
        return f"""Map the following work claim to the most appropriate SFIA skill code \
and responsibility level (1–7).

CLAIM:
Verbatim: "{claim.verbatim_quote}"
Interpreted: "{claim.interpreted_claim}"

CANDIDATE SFIA SKILL DEFINITIONS:
{skill_context}

Consider all four SFIA level attributes: Autonomy, Influence, Complexity, Knowledge.

Return ONLY a JSON object, no other text:
{{
  "skill_code": "XXXX",
  "skill_name": "Full Skill Name",
  "level": 4,
  "confidence": 0.85,
  "reasoning": "Brief explanation of why this skill and level were chosen"
}}"""

    async def analyse_transcript_holistically(
        self,
        transcript_text: str,
        max_skills: int = 6,
    ) -> list[HolisticSkillProfile]:
        client = self._get_client()
        response = await client.messages.create(
            model=self._model,
            max_tokens=2048,
            messages=[{"role": "user", "content": self._holistic_prompt(transcript_text, max_skills)}],
        )
        raw_text = response.content[0].text
        return self._parse_holistic(raw_text)

    def _holistic_prompt(self, transcript_text: str, max_skills: int) -> str:
        return f"""Analyse the following skills assessment transcript holistically — \
not claim by claim, but as a whole picture of the candidate's demonstrated capability.

Identify up to {max_skills} IT skill areas that featured most prominently throughout the \
conversation. For each skill area, assess:
- Which SFIA 9 skill it maps to (use standard codes: PROG, ARCH, CLOP, DENG, SCTY, \
ITMG, PRMG, BUAN, TEST, DBAD, NTAS, HSIN, SINT, DESN, DLMG, or similar)
- The SFIA responsibility level (1–7) the candidate's overall depth of evidence suggests
- How prominent this skill was in the conversation (0.0–1.0, where 1.0 = dominated discussion)
- A 1–2 sentence summary of the evidence that informed this assessment

Return ONLY a JSON array ordered by prominence (highest first), no other text:
[
  {{
    "skill_code": "ARCH",
    "skill_name": "Solution Architecture",
    "estimated_level": 5,
    "prominence": 0.85,
    "evidence_summary": "Candidate described leading cross-functional architecture decisions..."
  }}
]

TRANSCRIPT:
---
{transcript_text}
---"""

    def _parse_holistic(self, text: str) -> list[HolisticSkillProfile]:
        try:
            raw = text.strip()
            if raw.startswith("```"):
                raw = raw.removeprefix("```json").removeprefix("```")
                raw = raw.removesuffix("```").strip()
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.exception("AnthropicClaimLLMProvider: failed to parse holistic JSON")
            return []

        profiles: list[HolisticSkillProfile] = []
        for item in data:
            try:
                profiles.append(HolisticSkillProfile(
                    skill_code=item["skill_code"],
                    skill_name=item["skill_name"],
                    estimated_level=int(item["estimated_level"]),
                    prominence=float(item["prominence"]),
                    evidence_summary=item["evidence_summary"],
                ))
            except (KeyError, ValueError):
                logger.warning("AnthropicClaimLLMProvider: skipping malformed holistic item: %s", item)
        return profiles

    def _parse_extraction(self, text: str) -> list[Claim]:
        try:
            raw = text.strip()
            # Strip markdown code fences if present
            if raw.startswith("```"):
                raw = raw.removeprefix("```json").removeprefix("```")
                raw = raw.removesuffix("```").strip()
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.exception("AnthropicClaimLLMProvider: failed to parse extraction JSON")
            return []

        claims: list[Claim] = []
        for item in data:
            segments = [
                EvidenceSegment(
                    start_time=float(s["start_time"]),
                    end_time=float(s["end_time"]),
                )
                for s in item.get("evidence_segments", [])
            ]
            claims.append(Claim(
                verbatim_quote=item["verbatim_quote"],
                interpreted_claim=item["interpreted_claim"],
                evidence_segments=segments,
                sfia_skill_code="",
                sfia_skill_name="",
                sfia_level=1,
                confidence=0.0,
                reasoning="",
            ))
        return claims


__all__ = ["AnthropicClaimLLMProvider"]
