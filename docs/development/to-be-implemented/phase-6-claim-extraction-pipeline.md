# Phase 6: Claim Extraction Pipeline (Post-Call LLM Processing)

## Status
To Be Implemented

## Date
2026-05-01

## References
- PRD-002: Assessment Interview Workflow
- ADR-005: RAG & Vector Store Strategy
- Phase 1: Foundation & Monorepo Scaffold (defines Prisma schema, base ports)
- Phase 2: Basic Voice Engine (produces call sessions)
- Phase 4: Assessment Workflow (produces transcripts, stored in session metadata JSONB)
- Phase 5: RAG Knowledge Base (implements IKnowledgeBase, ingests SFIA data, defines SkillDefinition)

---

## Prerequisites

⚠️ **Version Bump Required**: This phase adds new columns to `assessment_sessions` (a Prisma schema migration) and promotes transcript storage from session `metadata` JSONB to a dedicated column. **Before implementation begins**, run:

```bash
/bump-version
```

Choose a MINOR bump (`v0.5.x` → `v0.6.0`). Then create the migration:

```bash
cd packages/database
pnpm prisma migrate dev --name v0_6_0_add_transcript_and_report_columns
```

---

## Phase 4/5 Compatibility

### Transcript storage migration

Phase 4 stored transcript data in `assessment_sessions.metadata` JSONB to avoid a schema migration (per Phase 4 decisions log). Phase 5 section 0.7 explicitly deferred moving this to a dedicated column to Phase 6.

Phase 6 resolves this:

1. `transcript_json JSONB` is added as a **dedicated column** on `assessment_sessions`.
2. The data migration SQL (section 1.3) copies existing transcript data from `metadata->'transcript_json'` to the new column.
3. `TranscriptRecorder.finalize()` (Phase 4) **must be updated** to call `persistence.save_transcript()` (section 1.4) instead of `persistence.merge_session_metadata()`. This is an intentional breaking change — no backwards-compat shim required.

### No separate Claim or AssessmentReport tables

Claims and report metadata are stored as JSONB columns on `assessment_sessions` (not as separate rows in separate tables). Individual claim objects each carry a UUID `id` field so Phase 7 (SME review portal) can address them for approve/adjust/reject updates using PostgreSQL `jsonb_set()`.

### Config field

Phase 5 introduced `anthropic_post_call_model: str = "claude-sonnet-4-6"` in `config.py`. Phase 6 reads this field — no hardcoded model IDs.

### SkillDefinition import

Phase 5 deleted `domain/models/skill.py` and moved `SkillDefinition` to `domain/ports/knowledge_base.py`. All Phase 6 code imports from there.

---

## Objective

Build the post-call processing pipeline that takes a completed assessment transcript, uses Claude (model configured via `anthropic_post_call_model`) to extract discrete verifiable claims with evidence timestamps, maps each claim to SFIA skill codes and responsibility levels via RAG, assigns confidence scores, and writes a structured report back onto the `assessment_sessions` row. Generates a NanoID-based review token for secure SME access.

---

## 1. Deliverables

### 1.1 Domain Models

**File:** `apps/voice-engine/src/domain/models/claim.py`

Single source of truth for all claim and report types. Uses Pydantic (consistent with Phase 5 models).

```python
from __future__ import annotations
from uuid import uuid4
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class EvidenceSegment(BaseModel):
    """A timestamp range in the call recording that supports a claim."""
    start_time: float   # seconds from call start
    end_time: float     # seconds from call start


class Claim(BaseModel):
    """A discrete, verifiable work claim extracted and enriched from a transcript."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    verbatim_quote: str
    interpreted_claim: str
    sfia_skill_code: str
    sfia_skill_name: str
    sfia_level: int = Field(ge=1, le=7)
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    framework_type: str = "sfia-9"
    evidence_segments: list[EvidenceSegment] = Field(default_factory=list)
    sme_status: str = "pending"         # pending | approved | adjusted | rejected
    sme_adjusted_level: int | None = None
    sme_notes: str | None = None


class ClaimExtractionResult(BaseModel):
    session_id: str
    claims: list[Claim]
    total_claims: int
    extracted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AssessmentReport(BaseModel):
    """In-memory representation of the full report — not a separate DB table."""
    session_id: str
    review_token: str           # NanoID, 21 chars
    review_url: str
    candidate_name: str
    claims: list[Claim]
    total_claims: int
    overall_confidence: float
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = "generated"   # generated | sent | in_review | completed
    expires_at: datetime


class SkillSummary(BaseModel):
    """Computed on read from claims — not persisted separately."""
    skill_code: str
    skill_name: str
    claim_count: int
    suggested_level: int        # max level across claims for this skill
    average_confidence: float
    claims: list[Claim]
```

**Note:** `SkillSummary` is computed at read time (e.g., in the FastAPI response layer) by grouping `claims` from the stored `claims_json`. It is never persisted.

---

### 1.2 ILLMProvider Port

**File:** `apps/voice-engine/src/domain/ports/llm_provider.py`

```python
from abc import ABC, abstractmethod
from domain.models.claim import Claim
from domain.ports.knowledge_base import SkillDefinition   # Phase 5 location


class ILLMProvider(ABC):

    @abstractmethod
    async def extract_claims(self, transcript_text: str) -> list[Claim]:
        """
        Extract discrete verifiable work claims from formatted transcript text.

        Args:
            transcript_text: Transcript formatted as "[MM:SS] SPEAKER: text" lines.

        Returns:
            List of Claim objects with verbatim_quote, interpreted_claim, and
            evidence_segments populated. sfia_* fields are empty at this stage.
        """
        ...

    @abstractmethod
    async def map_claim_to_skill(
        self,
        claim: Claim,
        skill_definitions: list[SkillDefinition],
    ) -> Claim:
        """
        Enrich a claim with SFIA skill code, level, confidence, and reasoning.

        Args:
            claim: Claim from extract_claims() with evidence_segments populated.
            skill_definitions: Candidate SFIA definitions from IKnowledgeBase.query().

        Returns:
            Enriched Claim with sfia_skill_code, sfia_skill_name, sfia_level,
            confidence, and reasoning filled in.
        """
        ...
```

---

### 1.3 Database Schema — assessment_sessions Column Additions

**Update Prisma schema:** `packages/database/prisma/schema.prisma`

Add the following columns to the existing `AssessmentSession` model:

```prisma
model AssessmentSession {
  // ... existing fields (id, candidateId, status, recordingUrl, etc.) ...

  // Phase 6 additions
  transcriptJson      Json?     @map("transcript_json")
  claimsJson          Json?     @map("claims_json")
  reviewToken         String?   @unique @db.VarChar(21) @map("review_token")
  reportStatus        String?   @db.VarChar(20) @map("report_status")
  overallConfidence   Float?    @map("overall_confidence")
  reportGeneratedAt   DateTime? @map("report_generated_at")
  smeReviewedAt       DateTime? @map("sme_reviewed_at")
  expiresAt           DateTime? @map("expires_at")
}
```

**Column reference:**

| Column | Type | Purpose |
|--------|------|---------|
| `transcript_json` | JSONB | Full call transcript (promoted from `metadata->'transcript_json'`) |
| `claims_json` | JSONB | Array of serialised `Claim` objects, each with a UUID `id` for Phase 7 updates |
| `review_token` | VARCHAR(21) UNIQUE | NanoID for secure SME access |
| `report_status` | VARCHAR(20) | `generated` / `sent` / `in_review` / `completed` — dedicated column for efficient filtering |
| `overall_confidence` | FLOAT | Pre-computed mean confidence across all claims |
| `report_generated_at` | TIMESTAMPTZ | When post-call pipeline completed |
| `sme_reviewed_at` | TIMESTAMPTZ | When SME submitted final review |
| `expires_at` | TIMESTAMPTZ | When review link expires (default: 30 days after generation) |

**Post-migration SQL** (run once after `prisma migrate dev`):

```sql
-- Promote existing transcript data from metadata JSONB to dedicated column
UPDATE assessment_sessions
SET transcript_json = (metadata->>'transcript_json')::jsonb
WHERE metadata ? 'transcript_json'
  AND transcript_json IS NULL;

-- Efficient lookup by review token
CREATE INDEX IF NOT EXISTS idx_assessment_sessions_review_token
    ON assessment_sessions (review_token)
    WHERE review_token IS NOT NULL;

-- Efficient report status filtering
CREATE INDEX IF NOT EXISTS idx_assessment_sessions_report_status
    ON assessment_sessions (report_status)
    WHERE report_status IS NOT NULL;
```

---

### 1.4 IPersistence Port Extensions

**File:** `apps/voice-engine/src/domain/ports/persistence.py`

Extend the existing `IPersistence` ABC with transcript and report methods:

```python
from datetime import datetime

# Add these abstract methods to the IPersistence ABC:

@abstractmethod
async def save_transcript(
    self,
    session_id: str,
    transcript_json: dict,
) -> None:
    """
    Write transcript JSON to assessment_sessions.transcript_json.

    Replaces the Phase 4 merge_session_metadata() approach for transcript data.
    TranscriptRecorder.finalize() must call this method from Phase 6 onwards.
    """
    ...

@abstractmethod
async def get_transcript(
    self,
    session_id: str,
) -> dict | None:
    """Read transcript_json for a session. Returns None if not yet persisted."""
    ...

@abstractmethod
async def save_report(
    self,
    session_id: str,
    claims: list[dict],
    review_token: str,
    overall_confidence: float,
    expires_at: datetime,
) -> None:
    """
    Write claims_json and report metadata columns to assessment_sessions.

    Sets: claims_json, review_token, overall_confidence, report_status='generated',
    report_generated_at=now(), expires_at.
    """
    ...

@abstractmethod
async def get_report(
    self,
    session_id: str,
) -> dict | None:
    """
    Read report metadata and claims_json for a session.

    Returns a dict with keys: session_id, claims_json, review_token, report_status,
    overall_confidence, report_generated_at, sme_reviewed_at, expires_at.
    Returns None if no report exists yet.
    """
    ...

@abstractmethod
async def get_report_by_token(
    self,
    review_token: str,
) -> dict | None:
    """
    Read session and report data by NanoID review token.

    Used by the public SME review endpoint. Returns None if token not found or expired.
    """
    ...
```

**Both `InMemoryPersistence` (tests) and `PostgresPersistence` (production) must implement all five methods.**

---

### 1.5 Claim Extraction Service

**File:** `apps/voice-engine/src/domain/services/claim_extractor.py`

Pure domain service — no infrastructure imports.

```python
from domain.ports.llm_provider import ILLMProvider
from domain.ports.knowledge_base import IKnowledgeBase
from domain.models.claim import Claim, ClaimExtractionResult


class ClaimExtractor:
    def __init__(
        self,
        llm_provider: ILLMProvider,
        knowledge_base: IKnowledgeBase,
    ):
        self.llm = llm_provider
        self.kb = knowledge_base

    async def process_transcript(
        self,
        session_id: str,
        transcript_json: dict,
        framework_type: str = "sfia-9",
    ) -> ClaimExtractionResult:
        """
        Full extraction pipeline:
        1. Format transcript JSON into readable text with timestamps
        2. Extract raw claims (with evidence_segments) from formatted text
        3. For each claim, query RAG for relevant SFIA skill definitions
        4. Map each claim to a skill code, level, and confidence score
        """
        transcript_text = self._format_transcript(transcript_json)
        raw_claims = await self.llm.extract_claims(transcript_text)

        enriched: list[Claim] = []
        for claim in raw_claims:
            skill_defs = await self.kb.query(
                text=claim.interpreted_claim,
                framework_type=framework_type,
                top_k=3,
            )
            mapped = await self.llm.map_claim_to_skill(claim, skill_defs)
            mapped.framework_type = framework_type
            enriched.append(mapped)

        return ClaimExtractionResult(
            session_id=session_id,
            claims=enriched,
            total_claims=len(enriched),
        )

    def _format_transcript(self, transcript_json: dict) -> str:
        """
        Format transcript turns into "[MM:SS] SPEAKER: text" lines.

        Timestamps are derived from the Unix epoch values stored by TranscriptRecorder;
        elapsed seconds from the first turn are converted to MM:SS display format.
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
            speaker = "NOA" if turn["speaker"] == "bot" else "CANDIDATE"
            lines.append(f"[{mm:02d}:{ss:02d}] {speaker}: {turn['text']}")

        return "\n".join(lines)
```

---

### 1.6 Anthropic LLM Provider Adapter

**File:** `apps/voice-engine/src/adapters/anthropic_llm_provider.py`

```python
import json
from anthropic import AsyncAnthropic
from domain.ports.llm_provider import ILLMProvider
from domain.ports.knowledge_base import SkillDefinition
from domain.models.claim import Claim, EvidenceSegment


class AnthropicLLMProvider(ILLMProvider):
    """Implements ILLMProvider using Claude (model from config.anthropic_post_call_model)."""

    def __init__(self, api_key: str, model: str):
        self.client = AsyncAnthropic(api_key=api_key)
        self.model = model   # injected from settings.anthropic_post_call_model at startup

    async def extract_claims(self, transcript_text: str) -> list[Claim]:
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            messages=[{"role": "user", "content": self._extraction_prompt(transcript_text)}],
        )
        return self._parse_extraction(response.content[0].text)

    async def map_claim_to_skill(
        self,
        claim: Claim,
        skill_definitions: list[SkillDefinition],
    ) -> Claim:
        context = "\n\n".join(
            f"--- {sd.skill_name} ({sd.skill_code}) Level {sd.level} ---\n{sd.content}"
            for sd in skill_definitions
        )
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=[{"role": "user", "content": self._mapping_prompt(claim, context)}],
        )
        mapping = json.loads(response.content[0].text)
        return claim.model_copy(update={
            "sfia_skill_code": mapping["skill_code"],
            "sfia_skill_name": mapping["skill_name"],
            "sfia_level": mapping["level"],
            "confidence": mapping["confidence"],
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

    def _parse_extraction(self, text: str) -> list[Claim]:
        data = json.loads(text)
        claims = []
        for item in data:
            segments = [
                EvidenceSegment(start_time=s["start_time"], end_time=s["end_time"])
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
```

**Wiring** (in `SFIACallBot._build()` or equivalent startup):

```python
from config import settings

llm_provider = AnthropicLLMProvider(
    api_key=settings.anthropic_api_key,
    model=settings.anthropic_post_call_model,   # "claude-sonnet-4-6" per Phase 5
)
```

---

### 1.7 Report Generator

**File:** `apps/voice-engine/src/domain/services/report_generator.py`

```python
from datetime import datetime, timezone, timedelta
from nanoid import generate as nanoid

from domain.models.claim import AssessmentReport, ClaimExtractionResult
from domain.ports.persistence import IPersistence


class ReportGenerator:
    NANOID_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    NANOID_LENGTH = 21
    LINK_EXPIRY_DAYS = 30

    def __init__(self, persistence: IPersistence, base_url: str):
        self.persistence = persistence
        self.base_url = base_url

    async def generate(
        self,
        session_id: str,
        extraction_result: ClaimExtractionResult,
        candidate_name: str,
    ) -> AssessmentReport:
        review_token = nanoid(self.NANOID_ALPHABET, self.NANOID_LENGTH)
        review_url = f"{self.base_url}/review/{review_token}"
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=self.LINK_EXPIRY_DAYS)

        overall_confidence = (
            sum(c.confidence for c in extraction_result.claims) / len(extraction_result.claims)
            if extraction_result.claims else 0.0
        )

        report = AssessmentReport(
            session_id=session_id,
            review_token=review_token,
            review_url=review_url,
            candidate_name=candidate_name,
            claims=extraction_result.claims,
            total_claims=extraction_result.total_claims,
            overall_confidence=overall_confidence,
            generated_at=now,
            expires_at=expires_at,
        )

        await self.persistence.save_report(
            session_id=session_id,
            claims=[c.model_dump() for c in extraction_result.claims],
            review_token=review_token,
            overall_confidence=overall_confidence,
            expires_at=expires_at,
        )

        return report
```

---

### 1.8 Post-Call Pipeline Orchestration

**File:** `apps/voice-engine/src/domain/services/post_call_pipeline.py`

```python
from domain.services.claim_extractor import ClaimExtractor
from domain.services.report_generator import ReportGenerator
from domain.ports.persistence import IPersistence
from domain.models.claim import AssessmentReport


class PostCallPipeline:
    def __init__(
        self,
        claim_extractor: ClaimExtractor,
        report_generator: ReportGenerator,
        persistence: IPersistence,
        notification_sender=None,   # INotificationSender | None — stub until Phase 7
    ):
        self.claim_extractor = claim_extractor
        self.report_generator = report_generator
        self.persistence = persistence
        self.notification_sender = notification_sender

    async def process(self, session_id: str) -> AssessmentReport:
        """
        Full post-call pipeline:
        1. Retrieve session and transcript from assessment_sessions
        2. Extract and enrich claims via LLM + RAG
        3. Generate report with NanoID review token
        4. Persist report columns to assessment_sessions
        5. Update session status to 'processed'
        6. Optionally notify SME (stub in Phase 6; fully wired in Phase 7)
        """
        session = await self.persistence.get_session(session_id)
        transcript_json = await self.persistence.get_transcript(session_id)

        if not transcript_json:
            raise ValueError(f"No transcript found for session {session_id}")

        extraction_result = await self.claim_extractor.process_transcript(
            session_id=session_id,
            transcript_json=transcript_json,
        )

        report = await self.report_generator.generate(
            session_id=session_id,
            extraction_result=extraction_result,
            candidate_name=session.candidate_name,
        )

        await self.persistence.update_session_status(session_id, "processed")

        if self.notification_sender and getattr(session, "sme_email", None):
            await self.notification_sender.send_review_link(
                sme_email=session.sme_email,
                review_url=report.review_url,
                candidate_name=session.candidate_name,
            )

        return report
```

**`INotificationSender` port** (stub — fully implemented in Phase 7):

```python
# apps/voice-engine/src/domain/ports/notification_sender.py
from abc import ABC, abstractmethod

class INotificationSender(ABC):
    @abstractmethod
    async def send_review_link(
        self,
        sme_email: str,
        review_url: str,
        candidate_name: str,
    ) -> None: ...
```

In Phase 6, wire `notification_sender=None` at startup. Phase 7 injects the real adapter.

---

### 1.9 FastAPI Endpoints

**File:** `apps/voice-engine/src/api/routes.py` (additions)

```python
@router.post("/assessment/{session_id}/process")
async def process_assessment(session_id: str):
    """Trigger post-call processing for a completed assessment session."""
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
    report_data = await persistence.get_report(session_id)
    if not report_data:
        raise HTTPException(status_code=404, detail="Report not found")
    return report_data


@router.get("/review/{review_token}")
async def get_review_by_token(review_token: str):
    """Public SME review endpoint — accessed via NanoID token link."""
    report_data = await persistence.get_report_by_token(review_token)
    if not report_data:
        raise HTTPException(status_code=404, detail="Review not found or expired")
    return report_data
```

---

## 2. LLM Prompt Engineering

### Extraction prompt strategy

The extraction prompt instructs the LLM to:
1. Distinguish **verifiable claims** (specific actions, outcomes, metrics) from opinions, aspirations, and vague context statements.
2. Return the **verbatim quote** exactly as spoken.
3. Return `evidence_segments` as `{start_time, end_time}` pairs (seconds from call start), derived from the `[MM:SS]` timestamps in the formatted transcript.

**Valid claims (extracted):**
- "I managed a team of 12 developers across three time zones" → team management claim
- "I designed the migration from on-prem to AWS, which saved $200k annually" → architecture + cost claim
- "I conducted security audits for SOC 2 compliance" → security assessment claim

**Non-claims (excluded):**
- "I think DevOps is really important" → opinion
- "I'd like to move into more leadership roles" → aspiration
- "Yeah, I've been in IT for about 15 years" → background context

### Mapping prompt strategy

The mapping prompt provides candidate SFIA skill definitions from RAG (top 3, filtered by `interpreted_claim` similarity) and instructs the LLM to consider all four SFIA attributes — Autonomy, Influence, Complexity, Knowledge — before assigning a skill code, level, and confidence score.

**Confidence calibration:**

| Range | Meaning |
|-------|---------|
| 0.9–1.0 | Claim explicitly matches skill definition and level descriptors |
| 0.7–0.89 | Claim strongly implies the skill and level |
| 0.5–0.69 | Claim is relevant but level is ambiguous |
| < 0.5 | Weak match — SME must verify carefully |

All claims are sent to the SME regardless of confidence score. Confidence is a display indicator only (per PRD-002).

### Long transcript handling

If the formatted transcript exceeds 60,000 characters (~15,000 tokens), split it into phase-based segments (`introduction`, `skill_discovery`, `evidence_gathering`, `summary`) using the `phase` field stored by `TranscriptRecorder`. Run `extract_claims` on each segment and deduplicate by `verbatim_quote` before mapping.

---

## 3. Acceptance Criteria

### Transcript migration
- [ ] `assessment_sessions.transcript_json` column exists after migration.
- [ ] Post-migration SQL successfully copies existing transcript data from `metadata->'transcript_json'` to `transcript_json` column for all sessions where `transcript_json IS NULL AND metadata ? 'transcript_json'`.
- [ ] `TranscriptRecorder.finalize()` calls `persistence.save_transcript()` and writes to the new column.
- [ ] `persistence.get_transcript(session_id)` returns the stored dict.

### Schema & ports
- [ ] All eight new/updated `assessment_sessions` columns exist: `transcript_json`, `claims_json`, `review_token`, `report_status`, `overall_confidence`, `report_generated_at`, `sme_reviewed_at`, `expires_at`.
- [ ] `review_token` column has a UNIQUE index.
- [ ] `IPersistence` extended with `save_transcript`, `get_transcript`, `save_report`, `get_report`, `get_report_by_token`.
- [ ] Both `InMemoryPersistence` and `PostgresPersistence` implement all five new methods.

### Claim extraction
- [ ] `ClaimExtractor.process_transcript()` produces structured claims from a sample transcript JSON.
- [ ] Each extracted claim has a non-empty UUID `id`, `verbatim_quote`, `interpreted_claim`, and at least one `evidence_segment`.
- [ ] Each mapped claim has `sfia_skill_code`, `sfia_skill_name` (non-empty), `sfia_level` (1–7), `confidence` (0.0–1.0), and `reasoning`.
- [ ] `framework_type` is set on all claims (default `"sfia-9"`).
- [ ] `AnthropicLLMProvider` reads model from injected `model` argument (not hardcoded).

### Report generation
- [ ] `ReportGenerator.generate()` creates an `AssessmentReport` with a valid 21-char NanoID `review_token`.
- [ ] Review URL format: `{base_url}/review/{review_token}`.
- [ ] `expires_at` is exactly 30 days after `report_generated_at`.
- [ ] `overall_confidence` equals the mean of all claim confidence scores.
- [ ] `claims_json` column contains serialised claim array with claim `id` fields intact.
- [ ] `report_status` is set to `"generated"` after `save_report()`.

### Pipeline
- [ ] `PostCallPipeline.process()` raises `ValueError` if `get_transcript()` returns `None`.
- [ ] `PostCallPipeline.process()` updates session status to `"processed"` after report generation.
- [ ] `PostCallPipeline.process()` runs end-to-end with a real sample transcript.

### API
- [ ] `POST /api/v1/assessment/{session_id}/process` triggers pipeline and returns `review_url`, `total_claims`, `overall_confidence`, `status`.
- [ ] `GET /api/v1/assessment/{session_id}/report` returns 200 with report data or 404.
- [ ] `GET /api/v1/review/{review_token}` returns 200 for a valid token or 404 for invalid/missing.

### Testing
- [ ] Unit tests for `ClaimExtractor` with mocked `ILLMProvider` and `IKnowledgeBase`.
- [ ] Unit tests for `ReportGenerator` with known claim sets (verify token length, confidence calc, expiry).
- [ ] Unit tests for `_format_transcript()` (verify MM:SS formatting and elapsed seconds).
- [ ] Integration test: full pipeline with a sample transcript JSON, real `IKnowledgeBase` (test DB), mocked LLM.

---

## 4. Dependencies

| Dependency | Source | Status |
|------------|--------|--------|
| `assessment_sessions` table with `metadata` JSONB | Phase 1 | ✅ Complete |
| `IPersistence` base port | Phase 1 | ✅ Complete |
| Transcript data in `metadata.transcript_json` | Phase 4 | ✅ Complete |
| `IKnowledgeBase` port + `PgVectorKnowledgeBase` adapter | Phase 5 | ✅ Complete |
| `SkillDefinition` dataclass in `domain/ports/knowledge_base.py` | Phase 5 | ✅ Complete |
| `anthropic_post_call_model` config field | Phase 5 | ✅ Complete |
| Anthropic API key | External | Required |
| `nanoid` Python package | External | Add to `pyproject.toml` |

---

## 5. Risks

| Risk | Mitigation |
|------|------------|
| Claude hallucinating SFIA skill codes not in the knowledge base | Validate extracted `sfia_skill_code` against known codes from `framework_skills` table; flag unknown codes for SME |
| Inconsistent or unparseable JSON output from LLM | Wrap parse calls in try/except; retry once with a stricter prompt; if still invalid, raise `ExtractionError` for the pipeline to catch |
| Long transcripts exceeding context window | Split transcript by phase segment (using `phase` field from TranscriptRecorder); aggregate claims across segments |
| `evidence_segments` timestamps inaccurate (LLM drift) | Acceptable — SME uses them as a starting point, not a precise reference; validation is by verbatim_quote match, not timestamp |
| Post-call pipeline failure (no report generated) | Wrap `PostCallPipeline.process()` in a retry handler; expose manual trigger endpoint (`POST /process`) so operators can re-trigger |
| JSONB claim updates in Phase 7 (concurrent SME edits) | Phase 7 must implement optimistic concurrency: read `claims_json`, update target claim by `id`, write back; detect conflicts via `updated_at` timestamp |

---

## 6. Implementation Sequence

1. **Version bump** — Run `/bump-version` → MINOR → `v0.6.0`. Create Prisma migration `v0_6_0_add_transcript_and_report_columns`. Run post-migration SQL.
2. **Domain models** — Implement `claim.py` (Pydantic models) and `notification_sender.py` (stub port).
3. **ILLMProvider port** — Define `llm_provider.py`.
4. **IPersistence extensions** — Add five new methods to port; implement in `InMemoryPersistence` first, then `PostgresPersistence`.
5. **TranscriptRecorder update** — Change `finalize()` to call `persistence.save_transcript()` instead of `persistence.merge_session_metadata()`.
6. **ClaimExtractor** — Implement service with `_format_transcript()` and pipeline logic.
7. **AnthropicLLMProvider** — Implement adapter; wire `model=settings.anthropic_post_call_model` at startup.
8. **ReportGenerator** — Implement service; verify NanoID length and expiry.
9. **PostCallPipeline** — Wire all services together; test with `InMemoryPersistence`.
10. **FastAPI endpoints** — Add three endpoints to `routes.py`.
11. **Tests** — Unit tests for each service; integration test for full pipeline.
12. **CHANGELOG** — Document Phase 6 additions.

---

## 7. Definition of Done

Phase 6 is complete when:

- [ ] All acceptance criteria (section 3) are met.
- [ ] Transcript data successfully migrated from `metadata` JSONB to `transcript_json` column on all existing sessions.
- [ ] A full pipeline run with a real 20-minute transcript JSON produces:
  - [ ] ≥ 5 extracted claims, each with `sfia_skill_code`, `sfia_level`, `confidence`, and ≥ 1 `evidence_segment`.
  - [ ] `claims_json` written to `assessment_sessions` with all claim `id` fields present.
  - [ ] `review_token` written (21 chars, URL-safe), `expires_at` = 30 days from now.
  - [ ] Session status updated to `"processed"`.
- [ ] `GET /api/v1/review/{review_token}` returns full report data for the generated token.
- [ ] All unit and integration tests pass.
- [ ] Version bumped to `v0.6.0`; Prisma migration applied.
- [ ] CHANGELOG.md updated with Phase 6 summary.
- [ ] Phase 6 document moved from `to-be-implemented/` to `implemented/v0.6/` with completion notes.

---

## 8. Revision History

| Date | Author | Change |
|------|--------|--------|
| 2026-05-01 | Doc Refiner | Full rewrite via /doc-refiner. Fixed: broken section numbering (duplicate 1.4/1.5/1.6); conflicting dual Claim model definitions (dataclass vs Pydantic); wrong SkillDefinition import (domain.models.skill → domain.ports.knowledge_base per Phase 5); hardcoded model ID replaced with settings.anthropic_post_call_model; IPersistence method name inconsistencies (save_report/get_report/get_report_by_token unified throughout); wrong dependency reference (Phase 3 → Phase 5 for RAG KB); missing version bump prerequisite. Added: AssessmentTranscript storage (promoted from Phase 4 metadata JSONB to assessment_sessions.transcript_json column, per Phase 5 section 0.7 deferral); claims_json and report metadata as JSONB columns on assessment_sessions (not separate tables); evidence_segments (JSON array of start_time/end_time pairs) on all claims; framework_type on all claims; sfia_skill_name on all claims; INotificationSender stub port; long transcript chunking strategy; Phase 7 JSONB concurrency note. |
| 2026-04-18 | AI Skills Assessor Team | Initial draft |
