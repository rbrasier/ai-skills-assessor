# PHASE-4 Implementation: Assessment Workflow & Transcript Persistence

## Reference
- **Phase Document:** `docs/development/to-be-implemented/phase-4-assessment-workflow.md`
- **Implementation Date:** 2026-04-29
- **Status:** In Progress

---

## Verification Record

### PRDs Approved
No PRDs referenced by Phase 4.

### ADRs Accepted
| ADR | Title | Status | Verified |
|-----|-------|--------|---------|
| ADR-004 | Voice Engine Technology (Pipecat, Daily, FastAPI) | Accepted | 2026-04-29 |

---

## Phase Summary

Implements the full 5-state SFIA assessment conversation flow (Introduction → SkillDiscovery → EvidenceGathering → Summary → Closing) using Pipecat Flows and persists structured transcripts (per-turn, phase-labelled) to the database. Replaces the Phase 3 basic "greeting + ack" bot with a stateful LLM-driven interview.

---

## Phase Scope

### Deliverables
- `SFIAFlowController` — Pipecat Flows 5-state machine (replaces stub)
- `TranscriptRecorder` — New domain service, accumulates speaker turns with phase labels
- `TranscriptFrameObserver` — Pipecat FrameProcessor that intercepts pipeline frames for recording
- `assessment_pipeline.py` — New: SFIA pipeline builder (replaces basic scripted bot)
- `SFIACallBot` — New: bot class wiring SFIA pipeline, analogous to `BasicCallBot`
- LiveKit recording URL capture at call end
- Status endpoint augmentation (`transcript_snippet`, `livekit_recording_url`)
- Unit tests for `TranscriptRecorder` and `SFIAFlowController`

### External Dependencies
- Phase 1: Monorepo, IPersistence port ✅
- Phase 2: CallManager, call lifecycle ✅
- Phase 3: LiveKit + STT/TTS providers working ✅
- `pipecat-ai-flows>=0.0.10` already in `pyproject.toml` ✅
- `assessment_sessions.recording_url` DB column already present ✅

---

## Implementation Strategy

### Approach
Follow the phase document's recommended sequence: schema/models → TranscriptRecorder → SFIAFlowController → pipeline integration → recording → API augmentation → tests.

### Build Sequence
1. Domain models: add `TranscriptTurn`, `merge_session_metadata` port method
2. `TranscriptRecorder` service (pure Python, fully testable without Pipecat)
3. `SFIAFlowController` (flow config + handlers, testable without Pipecat)
4. `assessment_pipeline.py` + `SFIACallBot` in `bot_runner.py` (Pipecat-specific)
5. LiveKit recording capture
6. Status API augmentation
7. Unit tests

---

## Known Risks and Unknowns

### Risks
- **pipecat-ai-flows exact API**: The library is not installed in the dev environment; the flow config format and FlowManager constructor signature were researched but cannot be live-tested without audio infrastructure. Mitigation: implement with defensive imports, comprehensive unit test mocks, and clear error logging.
- **LLM function call parsing**: LLM may fail to call transition functions. Mitigation: add fallback handler logging; phase transitions will surface in logs.
- **Transcript JSONB bloat**: For long calls, `metadata.transcript_json` may grow large. Mitigation: noted as a future concern (Phase 5 can move to a dedicated table).
- **LiveKit recording**: LiveKit's egress API requires egress configuration (S3/GCS). Without it, `recording_url` remains `null`. Mitigation: store whatever URL LiveKit provides; `null` is valid and handled gracefully.

### Unknowns
- Exact pipecat-ai-flows 0.0.10+ FlowManager constructor and handler registration API (researched; pending confirmation from agent).

### Scope Clarifications
No deviations from the phase document. RAG context injection deferred to Phase 5 as specified.

---

## Implementation Notes

### Part 1: Domain Models & Persistence Port
- **Goal:** Add `TranscriptTurn` dataclass; add `merge_session_metadata()` to `IPersistence` so transcript/skills data can be stored without changing session status.
- **Acceptance criteria:** `TranscriptTurn` matches phase doc schema. Both `InMemoryPersistence` and `PostgresPersistence` implement `merge_session_metadata()`.
- **Key decisions going in:**
  - Store `transcript_json`, `identified_skills`, `recording_duration_seconds` in `metadata` JSONB (not new columns) — per phase doc: "No Prisma migration required if schema is flexible".
  - `recording_url` already has its own column.

### Part 2: TranscriptRecorder
- **Goal:** Pure Python service accumulating `TranscriptTurn` objects, tracking current flow phase, providing `finalize()` that persists to session metadata.
- **Acceptance criteria:** Accumulates turns with phase label; `to_dict()` matches phase doc JSONB structure; `finalize()` writes to persistence; fully testable without Pipecat.

### Part 3: SFIAFlowController
- **Goal:** Pipecat Flows 5-state machine config with function handlers for state transitions.
- **Acceptance criteria:** All 5 states defined; `consent_given` → `skill_discovery`; `consent_declined` → `closing`; `skills_identified` stores skills; handlers update `TranscriptRecorder` phase; `call_ended` triggers finalization.

### Part 4: Pipeline Integration
- **Goal:** `assessment_pipeline.py` creates a complete Pipecat pipeline with FlowManager + TranscriptFrameObserver; `SFIACallBot` in `bot_runner.py` runs it for a session.
- **Acceptance criteria:** Pipeline wires transport → STT → context_aggregator → LLM(FlowManager) → TTS → transport; transcript turns captured for both bot and candidate speech.

### Part 5: LiveKit Recording
- **Goal:** Capture recording URL and duration from LiveKit at call end and persist to session.
- **Acceptance criteria:** `recording_url` populated in session after call ends; `null` if LiveKit egress not configured.

### Part 6: API Augmentation
- **Goal:** `GET /api/v1/assessment/{session_id}/status` returns `transcript_snippet` (first 500 chars) and `livekit_recording_url`.
- **Acceptance criteria:** Both fields optional, default `null`; read from session metadata/recording_url.

---

## Decisions Log

| Date | Part | Decision | Rationale | Files Affected |
|------|------|----------|-----------|----------------|
| 2026-04-29 | — | Initial implementation plan created | — | This document |
| 2026-04-29 | 1 | Store transcript data in `metadata` JSONB, not new DB columns | Phase doc explicitly states "No Prisma migration required if schema is flexible (JSONB)"; avoids schema migration complexity | `postgres_persistence.py`, `in_memory_persistence.py` |
| 2026-04-29 | 1 | Add `merge_session_metadata()` to `IPersistence` port | `update_session_status()` requires a status arg; transcript save shouldn't alter status | `persistence.py`, both adapters |
| 2026-04-29 | 2 | `TranscriptRecorder` is pure Python (no Pipecat dependency) | Testable in lean CI without `[voice]` extras; phase tracking is just string state | `transcript_recorder.py` |
| 2026-04-29 | 3 | `SFIAFlowController` separates config from bot lifecycle | Keeps domain logic (flow config, handlers) separate from Pipecat pipeline wiring | `sfia_flow_controller.py`, `assessment_pipeline.py` |
| 2026-04-29 | 4 | `SFIACallBot` added alongside `BasicCallBot` (not replacing it) | Existing tests rely on `BasicCallBot`; `BasicCallBot` stays for backward compatibility and test coverage | `bot_runner.py` |
| 2026-04-29 | 4 | `enable_sfia_flow` settings flag (default `False`) | Enables gradual rollout; basic bot remains active for existing E2E tests | `config.py`, `livekit_transport.py` |

---

## Revision History

| Date | Revision | Summary | Status |
|------|----------|---------|--------|
| 2026-04-29 | — | Initial implementation plan | In Progress |
| 2026-05-02 | Revision-1 | AI Mock Interview Test — text-only AI-to-AI end-to-end pipeline test via `scripts/mock-interview.sh`. See `docs/development/to-be-implemented/PHASE-4-Revision-1-ai-mock-interview-test.md` | Added |

---

## Related Documents
- Phase: `docs/development/to-be-implemented/phase-4-assessment-workflow.md`
- ADR: `docs/development/adr/ADR-004-voice-engine-technology.md`
