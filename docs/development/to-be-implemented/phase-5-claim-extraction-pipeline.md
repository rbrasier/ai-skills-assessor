# Phase 5: Claim Extraction Pipeline (Post-Call LLM Processing)

## Status
To Be Implemented

## Date
2026-04-18

## References
- PRD-002: Assessment Interview Workflow
- ADR-005: RAG & Vector Store Strategy
- Phase 2: Basic Voice Engine (produces transcripts)
- Phase 3: Assessment Workflow (produces assessment data)
- Phase 4: RAG Knowledge Base (skill definitions for mapping)

## Objective

Build the post-call processing pipeline that takes a completed assessment transcript, uses Claude 3.5 Sonnet to extract discrete verifiable claims, maps each claim to SFIA skill codes and responsibility levels, assigns confidence scores, generates a structured assessment report, and creates a unique NanoID-based review link for SME access.

---

## 1. Deliverables

### 1.1 Claim Extraction Service

**File:** `apps/voice-engine/src/domain/services/claim_extractor.py`

Domain service that orchestrates the extraction pipeline. This is pure business logic — no infrastructure dependencies.

```python
from domain.ports.llm_provider import LLMProvider
from domain.ports.knowledge_base import KnowledgeBase
from domain.ports.persistence import Persistence
from domain.models.claim import Claim, ClaimExtractionResult
from domain.models.transcript import Transcript

class ClaimExtractor:
    def __init__(
        self,
        llm_provider: LLMProvider,
        knowledge_base: KnowledgeBase,
        persistence: Persistence,
    ):
        self.llm = llm_provider
        self.kb = knowledge_base
        self.persistence = persistence

    async def process_transcript(
        self,
        session_id: str,
        transcript: Transcript,
    ) -> ClaimExtractionResult:
        """
        Full extraction pipeline:
        1. Extract raw claims from transcript
        2. Map each claim to SFIA skill codes and levels
        3. Enrich with skill definitions from RAG
        4. Assign confidence scores
        5. Persist results
        """
        # Step 1: Extract raw claims
        raw_claims = await self.llm.extract_claims(transcript.full_text)
        
        # Step 2-3: Map and enrich each claim
        enriched_claims = []
        for claim in raw_claims:
            skill_defs = await self.kb.query(
                text=claim.interpreted_claim,
                top_k=3,
            )
            
            mapped_claim = await self.llm.map_claim_to_skill(
                claim=claim,
                skill_definitions=skill_defs,
            )
            enriched_claims.append(mapped_claim)
        
        # Step 4: Persist
        await self.persistence.save_claims(session_id, enriched_claims)
        
        return ClaimExtractionResult(
            session_id=session_id,
            claims=enriched_claims,
            total_claims=len(enriched_claims),
        )
```

### 1.2 Anthropic LLM Provider Adapter

**File:** `apps/voice-engine/src/adapters/anthropic_llm_provider.py`

Implements the `LLMProvider` port using Claude 3.5 Sonnet.

```python
from anthropic import AsyncAnthropic
from domain.ports.llm_provider import LLMProvider
from domain.models.claim import Claim
from domain.models.skill import SkillDefinition

class AnthropicLLMProvider(LLMProvider):
    MODEL = "claude-sonnet-4-20250514"

    def __init__(self, api_key: str):
        self.client = AsyncAnthropic(api_key=api_key)

    async def extract_claims(self, transcript: str) -> list[Claim]:
        """
        Extract discrete, verifiable work claims from a transcript.
        Uses structured output to ensure consistent JSON format.
        """
        response = await self.client.messages.create(
            model=self.MODEL,
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": self._build_extraction_prompt(transcript),
                }
            ],
        )
        
        return self._parse_claims(response.content[0].text)

    async def map_claim_to_skill(
        self,
        claim: Claim,
        skill_definitions: list[SkillDefinition],
    ) -> Claim:
        """
        Given a claim and candidate SFIA skill definitions,
        map the claim to the most appropriate skill code and level.
        """
        context = "\n\n".join(
            f"--- {sd.skill_name} ({sd.skill_code}) Level {sd.level} ---\n{sd.content}"
            for sd in skill_definitions
        )
        
        response = await self.client.messages.create(
            model=self.MODEL,
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": self._build_mapping_prompt(claim, context),
                }
            ],
        )
        
        mapping = self._parse_mapping(response.content[0].text)
        
        return Claim(
            verbatim_quote=claim.verbatim_quote,
            interpreted_claim=claim.interpreted_claim,
            sfia_skill_code=mapping["skill_code"],
            sfia_level=mapping["level"],
            confidence=mapping["confidence"],
            reasoning=mapping["reasoning"],
        )

    def _build_extraction_prompt(self, transcript: str) -> str:
        return f"""Analyse the following skills assessment transcript and extract all discrete, 
verifiable work claims made by the candidate.

A "work claim" is a specific statement about something the candidate has done, managed, 
led, or achieved in their professional career. General statements of opinion or aspiration 
are NOT claims.

For each claim, provide:
1. verbatim_quote: The exact words from the transcript
2. interpreted_claim: A clear, concise interpretation of what the candidate is claiming

Return your response as a JSON array:
[
  {{
    "verbatim_quote": "exact quote from transcript",
    "interpreted_claim": "clear interpretation of the claim"
  }}
]

TRANSCRIPT:
---
{transcript}
---

Extract all verifiable work claims. Return ONLY the JSON array, no other text."""

    def _build_mapping_prompt(self, claim: Claim, skill_context: str) -> str:
        return f"""Map the following work claim to the most appropriate SFIA skill code and 
responsibility level (1-7).

CLAIM:
Verbatim: "{claim.verbatim_quote}"
Interpreted: "{claim.interpreted_claim}"

CANDIDATE SFIA SKILL DEFINITIONS:
{skill_context}

Analyse the claim against the SFIA skill definitions provided. Consider:
- Which skill best matches the type of work described?
- What level of autonomy, influence, complexity, and knowledge does the claim demonstrate?

Return your response as JSON:
{{
  "skill_code": "XXXX",
  "skill_name": "Full Skill Name",
  "level": 4,
  "confidence": 0.85,
  "reasoning": "Brief explanation of why this skill and level were chosen"
}}

Return ONLY the JSON object, no other text."""
```

### 1.3 Report Generator

**File:** `apps/voice-engine/src/domain/services/report_generator.py`

Generates the structured assessment report and the NanoID review link.

```python
from nanoid import generate as nanoid
from domain.models.claim import Claim, ClaimExtractionResult
from domain.models.report import AssessmentReport, SkillSummary

class ReportGenerator:
    NANOID_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    NANOID_LENGTH = 21

    def __init__(self, persistence: Persistence, base_url: str):
        self.persistence = persistence
        self.base_url = base_url

    async def generate(
        self,
        session_id: str,
        extraction_result: ClaimExtractionResult,
        candidate_name: str,
    ) -> AssessmentReport:
        """Generate a structured report with a unique review link."""
        
        review_token = nanoid(self.NANOID_ALPHABET, self.NANOID_LENGTH)
        review_url = f"{self.base_url}/review/{review_token}"
        
        skill_summaries = self._aggregate_by_skill(extraction_result.claims)
        
        report = AssessmentReport(
            session_id=session_id,
            review_token=review_token,
            review_url=review_url,
            candidate_name=candidate_name,
            skill_summaries=skill_summaries,
            total_claims=extraction_result.total_claims,
            overall_confidence=self._calculate_overall_confidence(extraction_result.claims),
        )
        
        await self.persistence.save_report(report)
        
        return report

    def _aggregate_by_skill(self, claims: list[Claim]) -> list[SkillSummary]:
        """Group claims by skill code and compute per-skill summaries."""
        skills: dict[str, list[Claim]] = {}
        for claim in claims:
            skills.setdefault(claim.sfia_skill_code, []).append(claim)
        
        summaries = []
        for skill_code, skill_claims in skills.items():
            levels = [c.sfia_level for c in skill_claims]
            confidences = [c.confidence for c in skill_claims]
            
            summaries.append(SkillSummary(
                skill_code=skill_code,
                skill_name=skill_claims[0].sfia_skill_name if hasattr(skill_claims[0], 'sfia_skill_name') else skill_code,
                claim_count=len(skill_claims),
                suggested_level=max(levels),
                average_confidence=sum(confidences) / len(confidences),
                claims=skill_claims,
            ))
        
        return sorted(summaries, key=lambda s: s.average_confidence, reverse=True)

    def _calculate_overall_confidence(self, claims: list[Claim]) -> float:
        if not claims:
            return 0.0
        return sum(c.confidence for c in claims) / len(claims)
```

### 1.4 Post-Call Pipeline Orchestration

**File:** `apps/voice-engine/src/domain/services/post_call_pipeline.py`

Wires the extraction and report generation together, triggered when a call ends.

```python
class PostCallPipeline:
    def __init__(
        self,
        claim_extractor: ClaimExtractor,
        report_generator: ReportGenerator,
        persistence: Persistence,
        notification_sender: NotificationSender | None = None,
    ):
        self.claim_extractor = claim_extractor
        self.report_generator = report_generator
        self.persistence = persistence
        self.notification_sender = notification_sender

    async def process(self, session_id: str) -> AssessmentReport:
        """
        Full post-call pipeline:
        1. Retrieve transcript
        2. Extract claims
        3. Generate report with review link
        4. Update session status
        5. (Optional) Notify SME
        """
        session = await self.persistence.get_session(session_id)
        transcript = await self.persistence.get_transcript(session_id)
        
        extraction_result = await self.claim_extractor.process_transcript(
            session_id=session_id,
            transcript=transcript,
        )
        
        report = await self.report_generator.generate(
            session_id=session_id,
            extraction_result=extraction_result,
            candidate_name=session.candidate_name,
        )
        
        await self.persistence.update_session_status(session_id, "processed")
        
        if self.notification_sender and session.sme_email:
            await self.notification_sender.send_review_link(
                sme_email=session.sme_email,
                review_url=report.review_url,
                candidate_name=session.candidate_name,
            )
        
        return report
```

### 1.5 Domain Models

**File:** `apps/voice-engine/src/domain/models/claim.py`

```python
from pydantic import BaseModel, Field
from datetime import datetime

class Claim(BaseModel):
    verbatim_quote: str
    interpreted_claim: str
    sfia_skill_code: str = ""
    sfia_skill_name: str = ""
    sfia_level: int = 0
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reasoning: str = ""
    sme_status: str = "pending"  # pending | approved | adjusted | rejected
    sme_adjusted_level: int | None = None
    sme_notes: str | None = None

class ClaimExtractionResult(BaseModel):
    session_id: str
    claims: list[Claim]
    total_claims: int
    extracted_at: datetime = Field(default_factory=datetime.utcnow)
```

**File:** `apps/voice-engine/src/domain/models/report.py`

```python
from pydantic import BaseModel, Field
from datetime import datetime

class SkillSummary(BaseModel):
    skill_code: str
    skill_name: str
    claim_count: int
    suggested_level: int
    average_confidence: float
    claims: list["Claim"]

class AssessmentReport(BaseModel):
    session_id: str
    review_token: str
    review_url: str
    candidate_name: str
    skill_summaries: list[SkillSummary]
    total_claims: int
    overall_confidence: float
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = "generated"  # generated | sent | in_review | completed
```

### 1.6 FastAPI Endpoint for Post-Call Trigger

**File:** `apps/voice-engine/src/api/routes.py` (additions)

```python
@router.post("/assessment/{session_id}/process")
async def process_assessment(session_id: str):
    """Trigger post-call processing for a completed assessment."""
    report = await post_call_pipeline.process(session_id)
    return {
        "session_id": session_id,
        "review_url": report.review_url,
        "total_claims": report.total_claims,
        "overall_confidence": report.overall_confidence,
        "status": "processed",
    }

@router.get("/assessment/{session_id}/report")
async def get_assessment_report(session_id: str):
    """Retrieve the assessment report for a session."""
    report = await persistence.get_report(session_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report

@router.get("/review/{review_token}")
async def get_review_by_token(review_token: str):
    """Public endpoint for SME review access via NanoID token."""
    report = await persistence.get_report_by_token(review_token)
    if not report:
        raise HTTPException(status_code=404, detail="Review not found or expired")
    return report
```

---

## 2. LLM Prompt Engineering

### Extraction Prompt Strategy

The claim extraction prompt must:
1. Distinguish between **verifiable claims** (specific actions, metrics, outcomes) and **general statements** (opinions, aspirations).
2. Preserve the **verbatim quote** exactly as spoken.
3. Provide a **clear interpretation** that removes conversational filler.

**Examples of valid claims:**
- "I managed a team of 12 developers across three time zones" → Team management claim
- "I designed the migration strategy from on-prem to AWS, which saved $200k annually" → Architecture + cost management claim
- "I conducted security audits for SOC 2 compliance" → Security assessment claim

**Examples of non-claims (should be excluded):**
- "I think DevOps is really important" → Opinion
- "I'd like to move into more leadership roles" → Aspiration
- "Yeah, I've been in IT for about 15 years" → Background context (not a specific claim)

### Mapping Prompt Strategy

The SFIA mapping prompt:
1. Receives the claim and relevant SFIA skill definitions (from RAG).
2. Must consider all four SFIA level attributes: Autonomy, Influence, Complexity, Knowledge.
3. Returns a confidence score reflecting how clearly the claim maps.
4. Provides reasoning that the SME can review.

**Confidence Calibration:**
- **0.9-1.0**: Claim explicitly matches skill definition and level descriptors.
- **0.7-0.89**: Claim strongly implies the skill and level.
- **0.5-0.69**: Claim is relevant but level is ambiguous.
- **< 0.5**: Weak match; flag for SME attention.

---

## 3. Acceptance Criteria

- [ ] `ClaimExtractor.process_transcript()` produces structured claims from a sample transcript.
- [ ] `AnthropicLLMProvider.extract_claims()` returns valid JSON with verbatim quotes and interpretations.
- [ ] `AnthropicLLMProvider.map_claim_to_skill()` returns skill code, level, confidence, and reasoning.
- [ ] Claims are correctly persisted to the `claims` table.
- [ ] `ReportGenerator` creates a report with a valid NanoID review token.
- [ ] Review URL format is `{base_url}/review/{nanoid}`.
- [ ] NanoID is 21 characters, URL-safe.
- [ ] Report aggregates claims by skill code.
- [ ] Overall confidence is correctly calculated.
- [ ] `PostCallPipeline.process()` runs the full pipeline end-to-end.
- [ ] `/api/v1/assessment/{session_id}/process` triggers processing and returns review URL.
- [ ] `/api/v1/review/{review_token}` returns the report for valid tokens.
- [ ] `/api/v1/review/{review_token}` returns 404 for invalid/expired tokens.
- [ ] Unit tests for claim extraction with mocked LLM responses.
- [ ] Unit tests for report generation with known claim sets.
- [ ] Integration test for full pipeline with a sample transcript.

## 4. Dependencies

- **Phase 1**: Database schema (claims and reports tables), port interfaces.
- **Phase 2**: Transcript persistence (produces the input for this pipeline).
- **Phase 3**: RAG knowledge base (for claim-to-skill mapping context).
- **External**: Anthropic API key.

## 5. Risks

| Risk | Mitigation |
|------|------------|
| Claude hallucinating skill codes | Validate extracted codes against known SFIA code list |
| Inconsistent JSON output from LLM | Use Claude's structured output mode; implement retry with validation |
| Long transcripts exceeding context window | Chunk transcript into segments; aggregate claims across chunks |
| Confidence scores not well-calibrated | Test with SME-validated sample set; adjust prompt if needed |
| Post-call processing failure (no report) | Implement retry queue; alert on failure; manual trigger endpoint |
