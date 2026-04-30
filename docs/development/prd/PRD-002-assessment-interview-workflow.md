# PRD-002: Assessment Interview Workflow

## Status
🟢 Approved

## Date
2026-04-18

## Last Updated
2026-04-30

## Document Owner
AI Skills Assessor Team

## Build Phase
Phase 5 (RAG Knowledge Base, Framework Configuration & SFIA Data Ingestion) and Phase 6 (Claim Extraction Pipeline)

## References
- PRD-001: Voice-AI SFIA Skills Assessment Platform (parent platform goals)
- ADR-004: Voice Engine Technology Decisions
- ADR-005: RAG & Vector Store Strategy

---

## 1. Executive Summary

This PRD details how an automated, voice-driven interview is conducted and what structured data is extracted. A candidate receives a phone call from an AI assessment bot that conducts a real-time conversation, uses RAG to retrieve framework definitions dynamically, and generates a transcript. Post-call, an LLM pipeline extracts verifiable claims, maps them to framework skills, and assigns confidence scores. The output is a structured dataset (transcripts + claims) ready for SME review.

This workflow is **framework-agnostic** and supports SFIA 9 initially with extensibility to TOGAF, ITIL, and other frameworks via metadata tagging.

---

## 2. Problem Statement

### Current State
Manual assessments rely on assessors to:
- Remember what the candidate said (no real-time recording)
- Manually identify which skills were demonstrated
- Write up evidence linking claims to framework definitions
- Track confidence in their own interpretation

This is:
- Slow to transcribe and analyse
- Inconsistent across assessors
- Hard to audit (unclear which words led to which skill mapping)

### Desired State
An automated interview system that:
- Records the full conversation (audio + text)
- Extracts discrete, verifiable claims in real time from the transcript
- Maps each claim to a framework skill with an interpretable score
- Produces a report ready for SME validation within minutes

---

## 3. Target Users

| User Type | Description | Primary Need |
|-----------|-------------|-------------|
| **Candidate** | IT professional being assessed | Natural, non-intimidating voice conversation; clear framework context |
| **System Engineer** | Developer maintaining the voice engine | Reliable state machine, error recovery, extensible claim extraction |
| **Framework Data Curator** | Subject matter expert loading framework definitions | Easy onboarding of new frameworks (TOGAF, ITIL, etc.) via metadata |

---

## 4. Core Interview Workflow

### 4.1 Interview Session Initialization
1. **Trigger**: Administrator (via PRD-001 web portal) initiates a call for a candidate.
2. **Session Creation**: Voice engine creates an `AssessmentSession` with unique ID.
3. **Call Setup**: Daily transport dials the candidate's phone number (+61 format).
4. **Consent**: Bot introduces itself, explains the purpose, and solicits verbal consent.
   - _Acceptance Criteria_: Consent is audio-recorded and flagged in session metadata.
5. **Framework Context**: Bot selects a framework (default: SFIA 9) and briefly explains the assessment structure to the candidate.

**Error Handling:**
- _Call fails to connect_: Session marked `failed`, administrator notified.
- _Candidate declines consent_: Call ends gracefully, session marked `cancelled`.
- _Network timeout during intro_: Call dropped, session marked `failed` with retry logic.

### 4.2 Skill Discovery Phase
1. **Open Question**: Bot asks: "What are the main IT skills or technical areas you've worked with in the last 3 years?"
2. **Candidate Response**: Candidate speaks freely (typically 1–5 minutes).
3. **Continuous RAG Query**: Voice engine queries the knowledge base in real time using candidate keywords to prepare follow-up probes.
4. **Skill Pool Identification**: Implicit — the claims in phase 2 determine which skills were discussed.

**Output**: Transcript segment tagged `phase:discovery`, list of candidate's keywords.

**Error Handling:**
- _Candidate unresponsive_: Bot waits 3 seconds, repeats question. After 2 repeats, moves to evidence gathering with fallback skills.
- _Audio quality poor_: STT confidence < 0.6 — system flags segment for manual review.

### 4.3 Evidence Gathering Phase
1. **Skill-by-Skill Probing**: For each skill identified in discovery, bot asks targeted questions across responsibility levels.
   - Example: "You mentioned Docker. Tell me about a time you designed a containerization strategy — what were the constraints, and how did you decide on the solution?"
2. **Dynamic RAG Injection**: Bot retrieves framework definitions for the skill and level, embeds them naturally in follow-up questions.
3. **Claim Elicitation**: Bot listens for:
   - **Activity**: What did the candidate do? (verb + object)
   - **Context**: Why? What were the constraints?
   - **Outcome**: What was the result? How do you measure success?
4. **Candidate Elaboration**: Candidate responds (typically 1–3 minutes per skill).
5. **Multiple Levels**: If candidate's response indicates higher-level autonomy/complexity, bot probes further.

**Output**: Transcript segment tagged `phase:evidence`, multiple raw claim text snippets.

**Error Handling:**
- _Candidate says "I don't know"_: Bot notes and moves to next skill.
- _Claim is vague or unclear_: Bot asks clarification: "Can you give me a specific example?"
- _LLM confidence is low during live processing_: System flags claim for extra scrutiny post-call.

### 4.4 Call Closure
1. **Summary**: Bot summarizes the key skill areas discussed and thanks the candidate.
2. **Call End**: Call is hung up gracefully.
3. **Recording Finalized**: Full audio + STT transcript persisted to storage.

**Output**: Complete `Transcript` object with all segments, metadata (duration, framework, quality flags).

---

## 5. Post-Call Claim Extraction Pipeline

### 5.1 Transcript Processing
1. **Input**: Full STT transcript (speaker labels, timestamps, confidence scores).
2. **Segmentation**: Transcript is split by speaker and phase tag.
3. **LLM Analysis**: Claude analyzes the entire transcript to extract discrete claims.

**Acceptance Criteria**:
- Transcript processing completes within 5 minutes of call end.
- Each claim includes: verbatim quote, candidate's interpreted intent, extracted activity/context/outcome.

### 5.2 Claim Extraction
**Input**: Full transcript.

**Process**:
1. **LLM Prompt**: Claude is given:
   - Framework definition (e.g., SFIA skill "Database Design" at levels 1–7 with descriptions)
   - Full transcript
   - Instruction: "Extract all discrete work claims where the candidate demonstrated this skill. For each claim: provide the verbatim quote, your interpretation, and the minimum responsibility level it demonstrates."

2. **Structured Output**: Each claim includes:
   - `verbatim_quote` — Exact text from transcript
   - `interpreted_claim` — Candidate's intent (what they were doing/thinking)
   - `framework_skill_code` — Skill identifier (e.g., "SFIA_DTAN" for Database Design)
   - `responsibility_level` — Inferred level (1–7, or generic framework equivalent)
   - `confidence` — LLM's confidence (0.0–1.0) that this claim maps correctly
   - `evidence_segments` — [timestamp ranges] in transcript supporting the claim
   - `framework_type` — Which framework (e.g., "sfia-9", "togaf-2024")

3. **Confidence-Based Flagging** (display indicator only — all claims go to SME for review):
   - `confidence >= 0.8`: Green indicator (high confidence)
   - `0.5 <= confidence < 0.8`: Yellow indicator ("LLM uncertain — verify carefully")
   - `confidence < 0.5`: Red indicator ("low confidence — manual verification required")

**Acceptance Criteria**:
- Claim extraction completes within 5 minutes of transcript reception.
- Each claim is independently verifiable (SME can find the verbatim quote in transcript).
- Framework skill code and responsibility level are always present (no null values).

**Error Handling**:
- _LLM extraction fails (timeout, error)_: Session marked `extraction_failed`, SME receives partial report with raw transcript + notification.
- _No claims extracted_: Possible if candidate provided no verifiable evidence. Session marked complete; SME receives raw transcript for manual analysis.

### 5.3 Report Generation
1. **Report Creation**: A unique `AssessmentReport` is created with:
   - Session ID, list of all claims, transcript summary
   - Confidence distribution (how many high/medium/low)
   - Framework type and date snapshot
2. **Review Token**: NanoID-based URL (e.g., `/review/V1StGXR8_Z5jdHi6B-myT`) generated.
3. **Expiry**: Link expires in 30 days (configurable per deployment).
4. **SME Notification**: SME is notified (email or webhook, see Open Questions) with review link.

**Output**: `AssessmentReport` object, review URL, SME notification sent.

---

## 6. System Architecture

### 6.1 Voice Engine (High-Level)

```
┌────────────────────────────────────────────────────────┐
│                    VOICE ENGINE DOMAIN                │
│                                                        │
│  ┌──────────────────────────────────────────────────┐ │
│  │        Interview State Machine (Pipecat)         │ │
│  │                                                  │ │
│  │  Discovery → Evidence Gathering → Closure       │ │
│  │      (interjection at 60s no-claim)             │ │
│  └──────────────────────────────────────────────────┘ │
│           ▲ orchestrated by                           │
│  ┌────────┴──────────────────────────────────────────┐ │
│  │      Interview Orchestrator (Coordinator)         │ │
│  │  - Manages state transitions                      │ │
│  │  - Triggers RAG queries at key points            │ │
│  │  - Detects claims in real-time                   │ │
│  │  - Handles interjections                         │ │
│  └────────────────────────────────────────────────────┘ │
│           ▼ uses                                       │
│  ┌──────────────────────────────────────────────────┐ │
│  │              PORTS (Interfaces)                   │ │
│  │  VoiceTransport   │  KnowledgeBase              │ │
│  │  Persistence      │  LLMProvider (optional)     │ │
│  │  STTProvider      │  TTSProvider                │ │
│  └──────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────┘
              ▲ implemented by
┌────────────────────────────────────────────────────────┐
│                    ADAPTERS                            │
│  DailyTransport       │  DeepgramSTT / AzureSTT       │
│  PgVectorKnowledgeBase│  Google TTS / Azure TTS       │
│  PostgresPersistence                                  │
└────────────────────────────────────────────────────────┘
```

### 6.2 Claim Extraction Pipeline (Post-Call)

```
Transcript (STT output)
    ↓
LLM Claim Extractor (Claude)
    ├→ Extract claims from each phase
    ├→ Map to framework skills (via metadata)
    ├→ Assign confidence scores
    ↓
Claim Objects (with verbatim quotes + evidence ranges)
    ↓
Report Generator
    ├→ Group by skill / level
    ├→ Flag low-confidence claims
    ├→ Generate NanoID review token
    ↓
AssessmentReport + Review Link
```

---

## 7. Data Model

All data structures are **framework-agnostic** and use metadata tagging for extensibility.

### Core Entities (Framework-Agnostic)

| Entity | Purpose | Key Fields |
|--------|---------|-----------|
| **Transcript** | Full call recording & STT output | `id`, `session_id`, `full_text`, `segments[]` (speaker, text, timestamp, confidence), `framework_type`, `framework_version`, `quality_flags[]` |
| **Segment** | Transcript piece with metadata | `speaker` (candidate/bot), `text`, `start_time`, `end_time`, `phase` (discovery/evidence/closure), `stt_confidence` |
| **Claim** | Extracted assertion with evidence | `id`, `session_id`, `verbatim_quote`, `interpreted_claim`, `framework_skill_code`, `responsibility_level`, `confidence` (0.0–1.0), `evidence_segments[]` (timestamp ranges), `framework_type`, `sme_status` (pending/approved/adjusted/rejected), `sme_adjusted_level`, `sme_notes` |
| **FrameworkDefinition** | Skill + level metadata | `framework_type` (e.g., "sfia-9"), `skill_code`, `level`, `description`, `autonomy`, `influence`, `complexity`, `knowledge`, `embedding` (vector) |

### Example: Framework-Agnostic Claim

```json
{
  "id": "claim-uuid-123",
  "session_id": "session-uuid-456",
  "verbatim_quote": "I designed the database schema for a multi-tenant SaaS platform, managing 50M customer records, and implemented sharding by tenant ID to maintain sub-100ms query latency.",
  "interpreted_claim": "Candidate designed a scalable database schema for a large multi-tenant system, using sharding for performance.",
  "framework_type": "sfia-9",
  "framework_skill_code": "DTAN",
  "responsibility_level": 5,
  "confidence": 0.87,
  "evidence_segments": [
    { "start_time": 234, "end_time": 267 },
    { "start_time": 290, "end_time": 315 }
  ],
  "sme_status": "pending",
  "created_at": "2026-04-18T10:35:00Z"
}
```

**Notes**:
- `framework_type` is a tag (not an FK to a separate table) → allows runtime switching.
- `responsibility_level` is a generic integer (1–7 for SFIA, can be redefined for other frameworks).
- `framework_skill_code` is arbitrary (e.g., "DTAN" for SFIA, "TOGAF_AA2.8" for TOGAF).
- No SFIA-specific columns; all framework knowledge is in `FrameworkDefinition` embeddings.

---

## 8. Key Technical Decisions

### 8.1 Pipecat for Interview State Machine
- **Why**: Pipecat provides frame-based, real-time voice AI with declarative state machines (Flows).
- **Consequence**: Interview logic maps directly to Pipecat Flows (Discovery → Evidence → Closure).

### 8.2 Daily for Telephony
- **Why**: PSTN dial-out capability with Sydney (`ap-southeast-2`) presence, native WebRTC support.
- **Consequence**: Australian phone numbers (+61) dial out via Daily, call recording enabled by default.
- **Fallback**: If PSTN unavailable, SME can receive a Daily room link for manual assessment.

### 8.3 RAG via pgvector (Dynamic Skill Context)
- **Why**: Store framework definitions (skill codes, descriptions, levels) as vectors in PostgreSQL.
- **Consequence**: At each evidence-gathering turn, bot queries the vector store for the relevant skill definition and naturally injects it into the question.
- **Extensibility**: New frameworks added by inserting rows in `FrameworkDefinition`; no schema change.

### 8.4 Claude Model Tiers
- **In-call responses** (real-time, during live assessment): `claude-haiku-4-5` — low latency, suitable for conversational turn-by-turn responses.
- **Post-call analysis** (claim extraction, final assessment scoring before SME review): `claude-sonnet-4-6` — deep analysis of full transcript, structured JSON output, higher accuracy for confidence scoring.
- **Rationale**: Haiku handles latency-sensitive in-call work; Sonnet handles thoroughness-sensitive post-call work.
- **Version Lock**: Model IDs are pinned; upgrades require an explicit version bump and re-validation of extraction prompt outputs.
- **Consequence**: Claim extraction is not real-time but deterministic and auditable.

### 8.5 Framework-Agnostic Data Model
- **Why**: Support SFIA 9 v1, TOGAF, ITIL in the future without schema migrations.
- **How**: `framework_type` metadata tag + generic `responsibility_level` integer + arbitrary `framework_skill_code` string.
- **Consequence**: New framework onboarding is a data-loading operation, not a schema change.

---

## 9. Non-Functional Requirements

| Requirement | Target | Rationale |
|-------------|--------|-----------|
| **Call Setup Latency** | < 5 seconds from dial to candidate answer | Must feel immediate |
| **STT Latency** | < 1 second (streaming) | Candidate expects natural conversation feel |
| **RAG Query Time** | < 200ms for top-5 skill definitions | Must not break conversation flow |
| **Claim Extraction Time** | < 5 minutes post-call | SME needs report quickly |
| **Call Duration** | 15–40 minutes typical | Sufficient for discovery + evidence gathering |
| **Concurrent Call Limit** | 10+ simultaneous (v1) | Enterprise pilot scale |
| **Transcript Storage** | Full audio + STT transcript retained indefinitely | Compliance + audit trail |

---

## 10. Integration Points

| System | Interface | Purpose |
|--------|-----------|---------|
| **Daily.co** | REST API + WebRTC | PSTN dial-out, room URLs, call recording |
| **Deepgram** (online) / **Faster Whisper** (offline) | WebSocket (Pipecat-managed) | Real-time speech-to-text |
| **ElevenLabs** (online) / **Kokoro** (offline) | WebSocket (Pipecat-managed) | Real-time text-to-speech |
| **PostgreSQL + pgvector** | TCP (pg protocol) | Transcript, claims, framework definitions, embeddings |
| **Anthropic Claude Haiku 4.5** | REST API | Real-time in-call LLM responses |
| **Anthropic Claude Sonnet 4.6** | REST API | Post-call claim extraction and final assessment scoring |

---

## 11. Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Call Completion Rate** | > 85% of initiated calls | Calls reaching evidence-gathering phase / total calls |
| **Claim Extraction Success** | > 90% of transcripts produce claims | Reports with >= 1 claim / total reports |
| **Mean Interview Duration** | 20–35 minutes | Average call length (discovery + evidence) |
| **STT Accuracy (by SME)** | > 95% of transcript text verified | Words correctly transcribed / total words |
| **Interjection Triggering** | Detected >= 1 per 30% of calls | Calls where bot interjected / total calls |

---

## 12. Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| STT/TTS provider latency high in AU | High | Medium | Benchmark Deepgram, Azure, Google in ap-southeast-2; test early |
| Candidate speaks in unclear/non-standard English | Medium | Medium | Fallback to manual transcription; flag low-confidence segments |
| Pipecat Flows are hard to debug | Medium | Low | Comprehensive logging; mock Pipecat flows in tests |
| LLM hallucination (false claims) | High | Medium | SME review mandatory; confidence thresholds; training data |
| Call drops mid-evidence | High | Low | Graceful exit; session marked incomplete; SME can request re-call |
| Framework definitions become stale | Medium | Low | Versioning via `framework_version` field; re-embedding pipeline |

---

## 13. Out of Scope (v1)

- Real-time claim extraction during the call (post-call only).
- Multi-language support (English only).
- Inbound calls (candidate-initiated); administrator-triggered only.
- Mobile app for candidates.
- Candidate self-assessment before interview.

---

## 13a. Minimum Viable Version (v1)

**Must ship (offline-first):**
- Offline STT via Faster Whisper
- Offline TTS via Kokoro
- Full interview state machine: Discovery → Evidence → Closure (no interjection rule)
- Post-call claim extraction pipeline (Claude Sonnet 4.6)
- Confidence indicators on claims (display only — all claims sent to SME)
- Single framework per call (SFIA 9)
- Transcript + audio retained indefinitely

**Online providers (secondary — can ship after offline validated):**
- Deepgram for STT
- ElevenLabs for TTS

**Deferred to v2+:**
- Multi-framework support per deployment
- Multi-language support
- Real-time claim extraction (post-call only in v1)

---

## 14. Open Questions

1. - [x] **STT Provider Selection**: Deepgram (online), Faster Whisper (offline). Offline-first for v1.
2. - [x] **TTS Provider Selection**: ElevenLabs (online), Kokoro (offline). Offline-first for v1.
3. - [x] **Interjection Rule**: Removed from scope entirely.
4. - [x] **Claim Confidence Thresholds**: Confidence is a display indicator only (green/yellow/red). No auto-approval — all claims are sent to SME for review regardless of score.
5. - [x] **Framework Version Handling**: One framework per call, selected at initialization based on interview configuration. No mixed-framework calls.
6. - [x] **Call Recording Retention**: Both audio files and STT transcripts retained indefinitely.

---

## 15. Revision History

| Date | Author | Change |
|------|--------|--------|
| 2026-04-18 | AI Skills Assessor Team | Initial draft |
| 2026-04-30 | AI Skills Assessor Team | Resolved all open questions: STT → Deepgram/Faster Whisper; TTS → ElevenLabs/Kokoro; removed interjection rule; confidence thresholds changed to display-only (no auto-approve); one framework per call; indefinite retention for audio + transcripts. Updated model references to Claude 4 family (Haiku in-call, Sonnet post-call). Added Minimum Viable Version section. |

---

## 16. Dependencies

- **PRD-001** (parent): Defines platform goals, SME review workflow, success metrics.
- **Phase 4** (Assessment Workflow & Interjection): Implements the interview state machine (SfiaFlowController).
- **Phase 5** (RAG Knowledge Base): Implements framework definitions, data ingestion, and RAG queries.
- **Phase 6** (Claim Extraction Pipeline): Implements post-call LLM extraction pipeline.
