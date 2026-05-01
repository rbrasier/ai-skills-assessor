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

Claims and report metadata are stored as JSONB columns on `assessment_sessions` (not as separate rows in separate tables). Individual claim objects each carry a UUID `id` field so Phase 7 (expert + supervisor review) can address them for per-row updates using PostgreSQL `jsonb_set()` (see Phase 7 plan).

### Config field

Phase 5 introduced `anthropic_post_call_model: str = "claude-sonnet-4-6"` in `config.py`. Phase 6 reads this field — no hardcoded model IDs.

### SkillDefinition import

Phase 5 deleted `domain/models/skill.py` and moved `SkillDefinition` to `domain/ports/knowledge_base.py`. All Phase 6 code imports from there.

---

## Objective

Build the post-call processing pipeline that takes a completed assessment transcript, uses Claude (model configured via `anthropic_post_call_model`) to extract discrete verifiable claims with evidence timestamps, maps each claim to SFIA skill codes and responsibility levels via RAG, assigns confidence scores, and writes a structured report back onto the `assessment_sessions` row. Generates **two** NanoID-based review tokens (`expert_review_token`, `supervisor_review_token`) for Phase 7 — separate URLs with capability isolation (see [Phase 7](phase-7-sme-review-portal.md)).

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
    # Phase 7 expert / supervisor review (initially unset after extraction)
    expert_level: int | None = Field(default=None, ge=1, le=7)  # SME-endorsed or adjusted SFIA level
    supervisor_decision: str = "pending"   # pending | verified | rejected
    supervisor_comment: str | None = None   # required on supervisor submit for every row (Phase 7)


class ClaimExtractionResult(BaseModel):
    session_id: str
    claims: list[Claim]
    total_claims: int
    extracted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AssessmentReport(BaseModel):
    """In-memory representation of the full report — not a separate DB table."""
    session_id: str
    expert_review_token: str         # NanoID, 21 chars — SME/expert modal URL
    supervisor_review_token: str    # NanoID, 21 chars — supervisor modal URL
    expert_review_url: str
    supervisor_review_url: str
    candidate_name: str
    claims: list[Claim]
    total_claims: int
    overall_confidence: float
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    report_status: str = "generated"   # see §1.3 column reference (extended enum)
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

**Legacy field migration:** If earlier drafts stored `sme_status`, `sme_adjusted_level`, or `sme_notes` on claims, map them on read into `expert_level` / supervisor fields as appropriate, or drop after one-off data migration — Phase 7 canonical shape is `expert_level` + `supervisor_decision` + `supervisor_comment`.

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

  // Phase 6 additions (Phase 7 extends tokens + report_status workflow)
  candidateName           String?   @db.VarChar(255) @map("candidate_name")
  transcriptJson          Json?     @map("transcript_json")
  claimsJson              Json?     @map("claims_json")
  expertReviewToken       String?   @unique @db.VarChar(21) @map("expert_review_token")
  supervisorReviewToken   String?   @unique @db.VarChar(21) @map("supervisor_review_token")
  reportStatus            String?   @db.VarChar(28) @map("report_status")
  overallConfidence       Float?    @map("overall_confidence")
  reportGeneratedAt       DateTime? @map("report_generated_at")
  expertSubmittedAt       DateTime? @map("expert_submitted_at")
  expertReviewerName      String?   @db.VarChar(255) @map("expert_reviewer_name")
  expertReviewerEmail     String?   @db.VarChar(255) @map("expert_reviewer_email")
  supervisorSubmittedAt   DateTime? @map("supervisor_submitted_at")
  supervisorReviewerName  String?   @db.VarChar(255) @map("supervisor_reviewer_name")
  supervisorReviewerEmail String?   @db.VarChar(255) @map("supervisor_reviewer_email")
  reviewsCompletedAt      DateTime? @map("reviews_completed_at")
  expiresAt               DateTime? @map("expires_at")
}
```

**Column reference:**

| Column | Type | Purpose |
|--------|------|---------|
| `candidate_name` | VARCHAR(255) | Denormalised from `Candidate.first_name + last_name` at session creation — avoids a JOIN in the post-call pipeline |
| `transcript_json` | JSONB | Full call transcript (promoted from `metadata->'transcript_json'`) |
| `claims_json` | JSONB | Array of serialised `Claim` objects with UUID `id`; carries Phase 7 expert/supervisor fields per row |
| `expert_review_token` | VARCHAR(21) UNIQUE | NanoID for SME/expert modal (`/review/expert/{token}`) |
| `supervisor_review_token` | VARCHAR(21) UNIQUE | NanoID for supervisor modal (`/review/supervisor/{token}`) |
| `report_status` | VARCHAR(28) | Workflow: `generated` → `awaiting_expert` → `awaiting_supervisor` → `reviews_complete` (exact strings implementable); operator may set `sent` when notifications dispatch |
| `overall_confidence` | FLOAT | Pre-computed mean confidence across all claims |
| `report_generated_at` | TIMESTAMPTZ | When post-call pipeline completed |
| `expert_submitted_at` | TIMESTAMPTZ | When expert PUT succeeded |
| `expert_reviewer_name` / `expert_reviewer_email` | VARCHAR | Declared identity at expert save (audit) |
| `supervisor_submitted_at` | TIMESTAMPTZ | When supervisor PUT succeeded |
| `supervisor_reviewer_name` / `supervisor_reviewer_email` | VARCHAR | Declared identity at supervisor save (audit) |
| `reviews_completed_at` | TIMESTAMPTZ | When **both** reviews recorded — eligibility for final HR/export outcome (Phase 7+) |
| `expires_at` | TIMESTAMPTZ | When review links expire (default: 30 days after generation) |

**Deprecated:** Single `review_token` / `sme_reviewed_at` — replaced by dual tokens and timestamps above. New migrations should add the new columns; if `review_token` exists from an earlier migration, migrate values or drop in the same MINOR bump as Phase 6 delivery.

**`candidate_name` population**: Wherever `AssessmentSession` is created (triggered from the intake form flow), populate `candidate_name` as `f"{candidate.first_name} {candidate.last_name}"`. This is a one-line addition to the existing session creation path — no new port method required.

**Post-migration SQL** (run once after `prisma migrate dev`):

```sql
-- Promote existing transcript data from metadata JSONB to dedicated column
UPDATE assessment_sessions
SET transcript_json = (metadata->>'transcript_json')::jsonb
WHERE metadata ? 'transcript_json'
  AND transcript_json IS NULL;

-- Efficient lookup by review tokens
CREATE INDEX IF NOT EXISTS idx_assessment_sessions_expert_review_token
    ON assessment_sessions (expert_review_token)
    WHERE expert_review_token IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_assessment_sessions_supervisor_review_token
    ON assessment_sessions (supervisor_review_token)
    WHERE supervisor_review_token IS NOT NULL;

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
    expert_review_token: str,
    supervisor_review_token: str,
    overall_confidence: float,
    expires_at: datetime,
) -> None:
    """
    Write claims_json and report metadata columns to assessment_sessions.

    Sets: claims_json, expert_review_token, supervisor_review_token,
    overall_confidence, report_status='generated' (or 'awaiting_expert' per product),
    report_generated_at=now(), expires_at.
    Clears expert/supervisor submission columns until Phase 7 PUTs run.
    """
    ...

@abstractmethod
async def get_report(
    self,
    session_id: str,
) -> dict | None:
    """
    Read report metadata and claims_json for a session.

    Returns a dict with keys: session_id, claims_json, expert_review_token,
    supervisor_review_token, report_status, overall_confidence,
    report_generated_at, expires_at, expert_submitted_at, expert_reviewer_*,
    supervisor_submitted_at, supervisor_reviewer_*, reviews_completed_at.
    Returns None if no report exists yet.
    """
    ...

@abstractmethod
async def get_report_by_expert_token(
    self,
    expert_review_token: str,
) -> dict | None:
    """Public expert review GET — returns None if token invalid or expired."""

    ...

@abstractmethod
async def get_report_by_supervisor_token(
    self,
    supervisor_review_token: str,
) -> dict | None:
    """Public supervisor review GET — returns None if token invalid or expired."""

    ...

@abstractmethod
async def save_expert_review(
    self,
    expert_review_token: str,
    reviewer_full_name: str,
    reviewer_email: str,
    claims_patch: list[dict],
) -> dict:
    """
    Atomically merge claims_patch into claims_json by claim id; set expert_level per row;
    set expert_submitted_at, expert_reviewer_name, expert_reviewer_email;
    advance report_status (e.g. to awaiting_supervisor). Returns updated report dict.
    Raises if token invalid, expired, or supervisor already completed (policy).
    """

    ...

@abstractmethod
async def save_supervisor_review(
    self,
    supervisor_review_token: str,
    reviewer_full_name: str,
    reviewer_email: str,
    claims_patch: list[dict],
) -> dict:
    """
    Merge supervisor_decision + supervisor_comment per claim id; set supervisor_* audit columns;
    set reviews_completed_at when expert submission already exists; report_status → reviews_complete.
    """

    ...
```

**Both `InMemoryPersistence` (tests) and `PostgresPersistence` (production) must implement all methods** (including token lookups and both save paths).

**Note:** If an interim implementation keeps `get_report_by_token(review_token)` for backwards compatibility, delegate to expert or supervisor lookup by trying both columns until legacy tokens are removed.

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
        expert_token = nanoid(self.NANOID_ALPHABET, self.NANOID_LENGTH)
        supervisor_token = nanoid(self.NANOID_ALPHABET, self.NANOID_LENGTH)
        expert_review_url = f"{self.base_url}/review/expert/{expert_token}"
        supervisor_review_url = f"{self.base_url}/review/supervisor/{supervisor_token}"
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=self.LINK_EXPIRY_DAYS)

        overall_confidence = (
            sum(c.confidence for c in extraction_result.claims) / len(extraction_result.claims)
            if extraction_result.claims else 0.0
        )

        report = AssessmentReport(
            session_id=session_id,
            expert_review_token=expert_token,
            supervisor_review_token=supervisor_token,
            expert_review_url=expert_review_url,
            supervisor_review_url=supervisor_review_url,
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
            expert_review_token=expert_token,
            supervisor_review_token=supervisor_token,
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
            await self.notification_sender.send_review_links(
                sme_email=session.sme_email,
                supervisor_email=getattr(session, "supervisor_email", "") or "",
                expert_review_url=report.expert_review_url,
                supervisor_review_url=report.supervisor_review_url,
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
    async def send_review_links(
        self,
        sme_email: str,
        supervisor_email: str,
        expert_review_url: str,
        supervisor_review_url: str,
        candidate_name: str,
    ) -> None: ...
```

In Phase 6, wire `notification_sender=None` at startup. Phase 7 injects the real adapter.

---

### 1.9 Automatic Pipeline Trigger — `handle_end_call()`

The post-call pipeline fires automatically when a call ends, immediately after the transcript is finalised. The trigger point is the existing `handle_end_call()` handler in `SFIAFlowController` (Phase 4).

**Why a background task**: Claim extraction takes 1–5 minutes (multiple LLM calls per claim). The call teardown must not block on this. Use `asyncio.create_task()` to fire and forget, with error handling that logs failures and leaves the session in a recoverable state.

**Updated `handle_end_call()` in `SFIAFlowController`:**

```python
import asyncio
import logging

logger = logging.getLogger(__name__)

async def handle_end_call(self, args: dict, flow_manager) -> tuple[None, None]:
    """Call is complete — finalise transcript then kick off post-call pipeline."""
    # Step 1: persist transcript (fast — DB write only)
    await self._recorder.finalize()

    # Step 2: fire post-call pipeline as background task (slow — multiple LLM calls)
    asyncio.create_task(
        self._run_pipeline_safe(self._session_id),
        name=f"post-call-pipeline-{self._session_id}",
    )

    await self._on_call_ended()
    return None, None

async def _run_pipeline_safe(self, session_id: str) -> None:
    """Run PostCallPipeline, logging errors without crashing the call teardown."""
    try:
        await self._post_call_pipeline.process(session_id)
    except Exception:
        logger.exception(
            "PostCallPipeline failed for session %s — "
            "manual re-trigger via POST /api/v1/assessment/%s/process",
            session_id, session_id,
        )
```

**`SFIAFlowController` constructor addition**: inject `post_call_pipeline: PostCallPipeline` and `session_id: str` alongside the existing `recorder`, `on_call_ended`, `system_prompt`, and `knowledge_base` arguments. Wire at startup in `SFIACallBot._build()`.

**Manual re-trigger**: The `POST /api/v1/assessment/{session_id}/process` endpoint (section 1.10) remains available as a recovery path if the background task fails.

---

### 1.10 FastAPI Endpoints

**File:** `apps/voice-engine/src/api/routes.py` (additions)

```python
@router.post("/assessment/{session_id}/process")
async def process_assessment(session_id: str):
    """Trigger post-call processing for a completed assessment session."""
    report = await post_call_pipeline.process(session_id)
    return {
        "session_id": session_id,
        "expert_review_url": report.expert_review_url,
        "supervisor_review_url": report.supervisor_review_url,
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


@router.get("/review/expert/{token}")
async def get_expert_review(token: str):
    """Expert/SME review surface — read-only report + transcript context."""
    report_data = await persistence.get_report_by_expert_token(token)
    if not report_data:
        raise HTTPException(status_code=404, detail="Review not found or expired")
    return report_data


@router.put("/review/expert/{token}")
async def put_expert_review(token: str, body: ExpertReviewPayload):
    """Persist expert levels + reviewer identity — see Phase 7 contract."""
    return await persistence.save_expert_review(
        expert_review_token=token,
        reviewer_full_name=body.reviewer_full_name,
        reviewer_email=body.reviewer_email,
        claims_patch=body.claims,
    )


@router.get("/review/supervisor/{token}")
async def get_supervisor_review(token: str):
    report_data = await persistence.get_report_by_supervisor_token(token)
    if not report_data:
        raise HTTPException(status_code=404, detail="Review not found or expired")
    return report_data


@router.put("/review/supervisor/{token}")
async def put_supervisor_review(token: str, body: SupervisorReviewPayload):
    return await persistence.save_supervisor_review(
        supervisor_review_token=token,
        reviewer_full_name=body.reviewer_full_name,
        reviewer_email=body.reviewer_email,
        claims_patch=body.claims,
    )
```

**Payload types** (`ExpertReviewPayload` / `SupervisorReviewPayload`) must match [Assessment Report Contract](../contracts/assessment-report-contract.md) §6.

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
- [ ] All Phase 6 `assessment_sessions` columns exist per §1.3 (including `expert_review_token`, `supervisor_review_token`, dual reviewer audit columns, `reviews_completed_at`).
- [ ] `candidate_name` is populated at session creation time as `"{first_name} {last_name}"` from the `Candidate` record.
- [ ] Both token columns have UNIQUE partial indexes.
- [ ] `IPersistence` extended with transcript/report methods per §1.4 (including `get_report_by_expert_token`, `get_report_by_supervisor_token`, `save_expert_review`, `save_supervisor_review`).
- [ ] Both `InMemoryPersistence` and `PostgresPersistence` implement all methods.

### Claim extraction
- [ ] `ClaimExtractor.process_transcript()` produces structured claims from a sample transcript JSON.
- [ ] Each extracted claim has a non-empty UUID `id`, `verbatim_quote`, `interpreted_claim`, and at least one `evidence_segment`.
- [ ] Each mapped claim has `sfia_skill_code`, `sfia_skill_name` (non-empty), `sfia_level` (1–7), `confidence` (0.0–1.0), and `reasoning`.
- [ ] `framework_type` is set on all claims (default `"sfia-9"`).
- [ ] `AnthropicLLMProvider` reads model from injected `model` argument (not hardcoded).

### Report generation
- [ ] `ReportGenerator.generate()` creates an `AssessmentReport` with two valid 21-char NanoIDs (`expert_review_token`, `supervisor_review_token`).
- [ ] Review URL formats: `{base_url}/review/expert/{token}`, `{base_url}/review/supervisor/{token}`.
- [ ] `expires_at` is exactly 30 days after `report_generated_at`.
- [ ] `overall_confidence` equals the mean of all claim confidence scores.
- [ ] `claims_json` column contains serialised claim array with claim `id` fields intact and Phase 7 fields defaulted (`supervisor_decision` = `pending`, `expert_level` null until expert save).
- [ ] `report_status` is set to `"generated"` after `save_report()`.

### Pipeline
- [ ] `PostCallPipeline.process()` raises `ValueError` if `get_transcript()` returns `None`.
- [ ] `PostCallPipeline.process()` updates session status to `"processed"` after report generation.
- [ ] `PostCallPipeline.process()` runs end-to-end with a real sample transcript.

### Automatic trigger
- [ ] `handle_end_call()` calls `transcript_recorder.finalize()` then fires `PostCallPipeline.process()` as an `asyncio.create_task()` background task.
- [ ] If the background task raises an exception, it is logged with the session ID and manual re-trigger path; the exception does not propagate to the call teardown.
- [ ] `SFIAFlowController` accepts `post_call_pipeline: PostCallPipeline` and `session_id: str` as constructor arguments.

### API
- [ ] `POST /api/v1/assessment/{session_id}/process` triggers pipeline and returns `expert_review_url`, `supervisor_review_url`, `total_claims`, `overall_confidence`, `status` (manual re-trigger / recovery path).
- [ ] `GET /api/v1/assessment/{session_id}/report` returns 200 with report data or 404.
- [ ] `GET /api/v1/review/expert/{token}` and `GET /api/v1/review/supervisor/{token}` return 200 for a valid token or 404 for invalid/expired.
- [ ] `PUT /api/v1/review/expert/{token}` and `PUT /api/v1/review/supervisor/{token}` persist reviewer identity + claim patches per [Assessment Report Contract](../contracts/assessment-report-contract.md); duplicate submit returns **409**.

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
2. **Session creation update** — Add `candidate_name` population (one line) to the existing session creation path.
3. **Domain models** — Implement `claim.py` (Pydantic models) and `notification_sender.py` (stub port).
4. **ILLMProvider port** — Define `llm_provider.py`.
5. **IPersistence extensions** — Add five new methods to port; implement in `InMemoryPersistence` first, then `PostgresPersistence`.
6. **TranscriptRecorder update** — Change `finalize()` to call `persistence.save_transcript()` instead of `persistence.merge_session_metadata()`.
7. **ClaimExtractor** — Implement service with `_format_transcript()` and pipeline logic.
8. **AnthropicLLMProvider** — Implement adapter; wire `model=settings.anthropic_post_call_model` at startup.
9. **ReportGenerator** — Implement service; verify NanoID length and expiry.
10. **PostCallPipeline** — Wire all services together; test with `InMemoryPersistence`.
11. **Automatic trigger** — Inject `PostCallPipeline` and `session_id` into `SFIAFlowController`; update `handle_end_call()` to fire background task.
12. **FastAPI endpoints** — Add routes per §1.10 (`GET`/`PUT` expert + supervisor).
13. **Tests** — Unit tests for each service; integration test for full pipeline including automatic trigger.
14. **CHANGELOG** — Document Phase 6 additions.

---

## 7. Definition of Done

Phase 6 is complete when:

- [ ] All acceptance criteria (section 3) are met.
- [ ] Transcript data successfully migrated from `metadata` JSONB to `transcript_json` column on all existing sessions.
- [ ] A full pipeline run with a real 20-minute transcript JSON produces:
  - [ ] ≥ 5 extracted claims, each with `sfia_skill_code`, `sfia_level`, `confidence`, and ≥ 1 `evidence_segment`.
  - [ ] `claims_json` written to `assessment_sessions` with all claim `id` fields present.
  - [ ] `expert_review_token` and `supervisor_review_token` written (21 chars, URL-safe), `expires_at` = 30 days from now.
  - [ ] Session status updated to `"processed"`.
- [ ] `GET /api/v1/review/expert/{token}` and `GET /api/v1/review/supervisor/{token}` return full report context for generated tokens.
- [ ] `handle_end_call()` automatically fires the pipeline; verified in integration test (pipeline completes and `report_status = "generated"` on session row).
- [ ] All unit and integration tests pass.
- [ ] Version bumped to `v0.6.0`; Prisma migration applied.
- [ ] CHANGELOG.md updated with Phase 6 summary.
- [ ] Phase 6 document moved from `to-be-implemented/` to `implemented/v0.6/` with completion notes.

---

## 8. Revision History

| Date | Author | Change |
|------|--------|--------|
| 2026-05-01 | Doc | Phase 7 alignment: dual review tokens (`expert_review_token`, `supervisor_review_token`), session-level reviewer audit columns, `Claim` fields `expert_level` / `supervisor_decision` / `supervisor_comment`, extended `report_status` workflow, `IPersistence` + FastAPI `GET`/`PUT` for `/review/expert` and `/review/supervisor`. Deprecated single `review_token` in favour of dual URLs. |
| 2026-05-01 | Doc Refiner | Full rewrite via /doc-refiner. Fixed: broken section numbering (duplicate 1.4/1.5/1.6); conflicting dual Claim model definitions (dataclass vs Pydantic); wrong SkillDefinition import (domain.models.skill → domain.ports.knowledge_base per Phase 5); hardcoded model ID replaced with settings.anthropic_post_call_model; IPersistence method name inconsistencies (save_report/get_report/get_report_by_token unified throughout); wrong dependency reference (Phase 3 → Phase 5 for RAG KB); missing version bump prerequisite. Added: AssessmentTranscript storage (promoted from Phase 4 metadata JSONB to assessment_sessions.transcript_json column, per Phase 5 section 0.7 deferral); claims_json and report metadata as JSONB columns on assessment_sessions (not separate tables); evidence_segments (JSON array of start_time/end_time pairs) on all claims; framework_type on all claims; sfia_skill_name on all claims; INotificationSender stub port; long transcript chunking strategy; Phase 7 JSONB concurrency note. |
| 2026-04-18 | AI Skills Assessor Team | Initial draft |
