# PHASE-6 Implementation: Claim Extraction Pipeline

## Reference
- **Phase Document:** `docs/development/implementated/v0.6/v0.6-phase-6-claim-extraction-pipeline.md`
- **Implementation Date:** 2026-05-01
- **Status:** In Progress

---

## Verification Record

### PRDs Approved
| PRD | Title | Status | Verified |
|-----|-------|--------|---------|
| PRD-002 | Assessment Interview Workflow | 🟢 Approved | 2026-05-01 |

### ADRs Accepted
| ADR | Title | Status | Verified |
|-----|-------|--------|---------|
| ADR-001 | Hexagonal Architecture | Accepted | 2026-05-01 |
| ADR-005 | RAG & Vector Store Strategy | Accepted | 2026-05-01 |

---

## Phase Summary

Builds the post-call LLM processing pipeline that takes a completed assessment transcript, uses Claude (claude-sonnet-4-6) to extract discrete verifiable claims, maps each claim to SFIA skill codes and levels via RAG, assigns confidence scores, and persists a structured report with a NanoID review token onto the `assessment_sessions` row.

---

## Phase Scope

### Deliverables
- Prisma migration v0.6.0: 9 new columns on `assessment_sessions`
- Pydantic domain models: `Claim`, `EvidenceSegment`, `ClaimExtractionResult`, `AssessmentReport`, `SkillSummary`
- `IClaimLLMProvider` port + `AnthropicClaimLLMProvider` adapter
- `INotificationSender` stub port
- `IPersistence` extended with 5 new methods
- `TranscriptRecorder.finalize()` updated to call `save_transcript()`
- `ClaimExtractor` domain service
- `ReportGenerator` domain service (NanoID 21-char, 30-day expiry)
- `PostCallPipeline` orchestrator + background task trigger
- `SfiaFlowController` updated with automatic pipeline trigger
- Three new FastAPI endpoints
- Unit + integration tests

### External Dependencies
- Phases 1, 2, 4, 5 all complete ✅
- `nanoid>=2.0.0` already in pyproject.toml ✅
- `anthropic_post_call_model = "claude-sonnet-4-6"` already in config ✅

---

## Implementation Strategy

### Approach
Follow the 14-step build sequence from the phase document: schema → models → ports → services → adapter → pipeline → trigger → endpoints → tests.

### Build Sequence
1. Prisma migration SQL + schema update
2. Domain model updates (`AssessmentSession`, `claim.py`)
3. New ports (`IClaimLLMProvider`, `INotificationSender`)
4. `IPersistence` extensions + adapter implementations
5. `TranscriptRecorder.finalize()` update
6. `CallManager` candidate_name population
7. `ClaimExtractor` + `AnthropicClaimLLMProvider`
8. `ReportGenerator`
9. `PostCallPipeline` orchestrator
10. `SfiaFlowController` + `SFIACallBot` wiring
11. FastAPI endpoints
12. `main.py` wiring
13. Tests

---

## Known Risks and Unknowns

### Risks
- **`save_transcript` signature conflict**: Existing `IPersistence.save_transcript(transcript: Transcript)` never used in production (stub). Safe to replace signature.
- **Double-finalization risk**: `SfiaFlowController.handle_end_call()` fires pipeline after `_on_call_ended()` which itself calls `finalize()` — pipeline fires only after transcript is persisted.
- **Long transcripts**: Chunking strategy noted in phase doc; not a formal acceptance criterion so deferred to a future revision.

### Unknowns
- Anthropic API JSON parse reliability for structured extraction prompts (handled by retry/error wrapper in adapter).

### Scope Clarifications
- Long-transcript chunking (>60k chars): documented in phase doc but no formal AC — out of scope for this implementation, deferred.
- `SkillSummary`: compute-on-read only, never persisted. Confirmed.
- `notification_sender=None` fully stubbed until Phase 7. Confirmed.
- `IClaimLLMProvider` is a separate port from existing `ILLMProvider` (which has `complete()` for in-call use) — keeps interface segregation principle.

---

## Implementation Notes

### Part 1: Schema + Domain Models
- **Goal:** Add 9 new columns to `assessment_sessions` and replace `claim.py` stub with Pydantic models
- **Acceptance criteria:** All 9 columns exist; `candidate_name` populated at session creation
- **Key decisions going in:**
  - Add columns to `assessment_sessions` (not separate table) per phase doc
  - `AssessmentSession` dataclass gains optional `candidate_name: str | None = None`
  - `claim.py` rewritten from dataclass stubs to Pydantic `BaseModel`

### Part 2: Ports + Persistence
- **Goal:** `IClaimLLMProvider`, `INotificationSender`, and 5 new `IPersistence` methods
- **Acceptance criteria:** Both `InMemoryPersistence` and `PostgresPersistence` implement all new methods
- **Key decisions going in:**
  - `save_transcript(session_id, transcript_json)` replaces old `save_transcript(transcript: Transcript)` stub — old signature was never called in production
  - `TranscriptRecorder.finalize()` now calls `save_transcript()` for transcript data AND `merge_session_metadata()` for remaining fields (identified_skills, recording_duration_seconds)

### Part 3: Services + Adapter
- **Goal:** `ClaimExtractor`, `AnthropicClaimLLMProvider`, `ReportGenerator`, `PostCallPipeline`
- **Acceptance criteria:** Full pipeline produces claims + report from sample transcript

### Part 4: Trigger + Endpoints
- **Goal:** Automatic pipeline trigger in `SfiaFlowController.handle_end_call()`; 3 new FastAPI endpoints
- **Key decisions going in:**
  - Pipeline fires AFTER `_on_call_ended()` completes (transcript already finalized by that point)
  - `post_call_pipeline` and `session_id` are optional kwargs (default None/"") so existing tests don't break

---

## Decisions Log

| Date | Part | Decision | Rationale | Files Affected |
|------|------|----------|-----------|----------------|
| 2026-05-01 | — | Initial implementation plan created | — | This document |
| 2026-05-01 | 2 | Created `IClaimLLMProvider` as separate port from `ILLMProvider` | ISP — in-call `complete()` and post-call extraction are different concerns; existing `ILLMProvider` used by voice transports must not be broken | `domain/ports/claim_llm_provider.py` |
| 2026-05-01 | 2 | Replaced `save_transcript(transcript: Transcript)` with `save_transcript(session_id, transcript_json)` | Old stub was never called in production; Phase 6 needs to write to dedicated DB column | `domain/ports/persistence.py`, both adapters, `transcript_recorder.py` |
| 2026-05-01 | 4 | Pipeline fires after `_on_call_ended()` in `handle_end_call()` | `_on_call_ended()` → `SFIACallBot._finalize_and_end()` → `recorder.finalize()` — guarantees transcript is persisted before pipeline starts | `flows/sfia_flow_controller.py` |

---

## Revision History

| Date | Revision | Summary | Status |
|------|----------|---------|--------|
| 2026-05-01 | — | Initial implementation plan | In Progress |

---

## Related Documents
- Phase: `docs/development/implementated/v0.6/v0.6-phase-6-claim-extraction-pipeline.md`
- PRDs: `docs/development/prd/PRD-002-assessment-interview-workflow.md`
- ADRs: `docs/development/adr/ADR-001-hexagonal-architecture.md`, `docs/development/adr/ADR-005-rag-vector-store-strategy.md`
