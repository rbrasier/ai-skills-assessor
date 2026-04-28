# Phase 4: Assessment Workflow & Transcript Persistence

## Status
To Be Implemented

## Date
2026-04-28

## References
- ADR-004: Voice Engine Technology Decisions
- Phase 2: Basic Voice Engine & Call Tracking (prerequisite)
- Phase 3: Infrastructure Deployment & LiveKit Integration (prerequisite)

## Objective

Implement the full SFIA assessment conversation flow (5-state state machine) and structured transcript persistence. Build a stateful conversation that guides candidates through Introduction → Skill Discovery → Evidence Gathering → Summary → Closing, with all turns recorded and labeled by phase. By the end of this phase, the system conducts a complete assessment interview and persists detailed transcripts with speaker turns, timestamps, and phase metadata.

---

## 1. Deliverables

### 1.1 SFIAFlowController (Pipecat Flows State Machine)

**File:** `apps/voice-engine/src/flows/sfia_flow_controller.py`

The core conversation state machine using Pipecat Flows. Controls the assessment conversation as a 5-state flow with transitions driven by LLM function calls.

**States:**

```
┌──────────────────────────────────────────┐
│ Introduction                             │  Name, consent, process explanation
│ (3–5 seconds to read, await consent)     │
└──────┬───────────────────────────────────┘
       │ "yes, proceed" function called
       ▼
┌──────────────────────────────────────────┐
│ SkillDiscovery                           │  Probe: "Tell me about your IT career"
│ (LLM identifies 2–5 key skill areas)     │
└──────┬───────────────────────────────────┘
       │ set_identified_skills() function called
       ▼
┌──────────────────────────────────────────┐
│ EvidenceGathering                        │  Per-skill probes for specificity
│ (loops per skill, ~2–3 min per skill)    │  (no RAG context in Phase 4)
└──────┬───────────────────────────────────┘
       │ transition_to_summary() called
       ▼
┌──────────────────────────────────────────┐
│ Summary                                  │  Recap skills and evidence heard
└──────┬───────────────────────────────────┘
       │ transition_to_closing() called
       ▼
┌──────────────────────────────────────────┐
│ Closing                                  │  Thank, next steps, goodbye
└──────────────────────────────────────────┘
```

**Flow Definition:**

The flow is implemented using Pipecat Flows with LLM function calling. The LLM drives state transitions by calling functions like `transition_to_skill_discovery()`, `set_identified_skills()`, and `transition_to_summary()`.

```python
# Pseudo-structure of the flow config. See apps/voice-engine/src/flows/sfia_flow.py
# for the full Pipecat Flows configuration.

flow_config: FlowConfig = {
    "initial_node": "introduction",
    "nodes": {
        "introduction": {
            "role_messages": [
                {
                    "role": "system",
                    "content": (
                        "You are Noa, an AI skills assessor from Resonant. "
                        "Introduce yourself, explain the SFIA-based assessment, "
                        "and ask for verbal consent to proceed and record the conversation."
                    ),
                }
            ],
            "functions": [
                {
                    "name": "consent_given",
                    "description": "Candidate consents to proceed.",
                    "transition_to": "skill_discovery",
                },
                {
                    "name": "consent_declined",
                    "description": "Candidate declines; end gracefully.",
                    "transition_to": "closing",
                },
            ],
        },
        "skill_discovery": {
            "role_messages": [
                {
                    "role": "system",
                    "content": (
                        "Ask the candidate to describe their role, key responsibilities, "
                        "and IT expertise. Listen for skill mentions. Keep natural; "
                        "do not name SFIA codes yet. Identify 2-5 skill areas."
                    ),
                }
            ],
            "functions": [
                {
                    "name": "skills_identified",
                    "description": "Record identified skills and move to evidence gathering.",
                    "parameters": {
                        "skills": {
                            "type": "array",
                            "items": {
                                "skill_code": "string",
                                "skill_name": "string",
                            },
                        }
                    },
                    "handler": "handle_identified_skills",
                    "transition_to": "evidence_gathering",
                },
            ],
        },
        "evidence_gathering": {
            "role_messages": [
                {
                    "role": "system",
                    "content": (
                        "For each identified skill, ask for concrete examples. "
                        "Probe for: Autonomy (did they decide?), Influence (who did they impact?), "
                        "Complexity (what was hard?), and Knowledge (what did they learn?). "
                        "Get at least one example per skill."
                    ),
                }
            ],
            "functions": [
                {
                    "name": "evidence_complete",
                    "description": "Sufficient evidence gathered. Move to summary.",
                    "transition_to": "summary",
                },
            ],
        },
        "summary": {
            "role_messages": [
                {
                    "role": "system",
                    "content": (
                        "Summarize the key skills and example evidence discussed. "
                        "Thank the candidate for their time and engagement. "
                        "Explain that an assessment report will be reviewed by a subject matter expert."
                    ),
                }
            ],
            "functions": [
                {
                    "name": "summary_complete",
                    "description": "Summary delivered. Move to closing.",
                    "transition_to": "closing",
                },
            ],
        },
        "closing": {
            "role_messages": [
                {
                    "role": "system",
                    "content": (
                        "Thank the candidate warmly. Let them know next steps "
                        "(SME review, feedback timeline). Say goodbye professionally."
                    ),
                }
            ],
            "functions": [
                {
                    "name": "call_ended",
                    "description": "Call is complete. End the session.",
                    "handler": "handle_end_call",
                }
            ],
        },
    },
}
```

**Key function handlers:**
- `handle_identified_skills(skills)`: Records skill list to session metadata.
- `handle_end_call()`: Triggers transcript finalization and persistence (see section 1.3).

### 1.2 Transcript Persistence & Recording

**File:** `apps/voice-engine/src/domain/services/transcript_recorder.py` (new)

Tracks speaker turns, timestamps, and phase labels throughout the call. Records to database at call end.

**Data structure per turn:**

```python
@dataclass
class TranscriptTurn:
    timestamp: float              # Unix timestamp when turn started
    speaker: Literal["candidate", "bot"]
    text: str                     # Exact text spoken
    phase: str                    # Which state machine phase: "introduction", "skill_discovery", etc.
    vad_confidence: float | None  # Voice activity detection confidence (0.0–1.0)
```

**Storage schema (PostgreSQL):**

```sql
-- Extend assessment_sessions to include transcript data
ALTER TABLE assessment_sessions ADD COLUMN (
    transcript_json JSONB,  -- Array of TranscriptTurn objects
    recording_url TEXT,     -- URL to LiveKit recording (MP3)
    recording_duration_seconds INTEGER,
    identified_skills JSONB  -- Array from skill_discovery phase
);

-- transcript_json structure:
{
  "turns": [
    {
      "timestamp": 1714344000.123,
      "speaker": "bot",
      "text": "Hello, I'm Noa...",
      "phase": "introduction",
      "vad_confidence": null
    },
    {
      "timestamp": 1714344005.456,
      "speaker": "candidate",
      "text": "Hi, yes I consent...",
      "phase": "introduction",
      "vad_confidence": 0.95
    },
    ...
  ]
}
```

**Responsibility:**
- Accumulate transcript turns as the bot and candidate speak.
- Tag each turn with the current flow phase (read from Pipecat Flows state).
- Save full transcript to `assessment_sessions.transcript_json` when call ends.
- Retrieve LiveKit recording metadata from the session and store `recording_url` and `recording_duration_seconds`.

### 1.3 Pipecat Pipeline Integration

**File:** `apps/voice-engine/src/flows/assessment_pipeline.py` (modify existing)

The Pipecat pipeline wires STT, LLM, TTS, and LiveKit transport. The flow state is passed to `TranscriptRecorder` so each turn is tagged with the current phase.

**Pipeline structure (pseudo):**

```python
pipeline = Pipeline([
    livekit_transport.input(),       # Audio from candidate
    stt_processor,                   # STT (already working per Phase 3)
    context_aggregator.user(),       # Accumulate user utterances
    llm_processor,                   # LLM with flow management
    tts_processor,                   # TTS (already working per Phase 3)
    livekit_transport.output(),      # Audio to candidate
    context_aggregator.assistant(),  # Accumulate bot utterances
])
```

**Key changes from Phase 3:**
1. Replace "basic greeting + ack" with `SFIAFlowController` (Pipecat Flows).
2. Inject `TranscriptRecorder` as a side-effect processor to tag turns with phase.
3. At call end, call `transcript_recorder.finalize()` to save to database.

### 1.4 Augmentation to POST /api/v1/assessment/trigger

**File:** `apps/voice-engine/src/api/routes.py` (augment existing)

The trigger endpoint already exists and works for both `dialing_method: "browser"` (LiveKit) and `dialing_method: "daily"` (PSTN). Phase 4 additions:

- **No new fields required** in the request (existing `candidate_id`, `phone_number`, `dialing_method` are sufficient).
- **Response augmentation**: The trigger response's `status` field may now be `"speech_phase: introduction"` to reflect the flow state (optional; currently just `"dialling"`).
- **Status endpoint augmentation** (`GET /api/v1/assessment/{session_id}/status`):
  - Add optional `transcript_snippet` field (first 500 chars of assembled transcript for debugging).
  - Add optional `livekit_recording_url` field (populated when recording is ready).
  - These are **optional** for backward compatibility; default to `null` if not available yet.

---

## 2. Pipecat Event Flow

### VAD (Voice Activity Detection) Events

Pipecat fires `UserStartedSpeaking` and `UserStoppedSpeaking` events as the candidate speaks. These drive:

1. **Transcript turn detection**: When `UserStartedSpeaking` fires, mark the start of a candidate turn (timestamp, phase).
2. **Turn-taking**: VAD/LLM manages when the bot should yield and listen.
3. **Context accumulation**: STT text is accumulated in Pipecat's context for the LLM.

### Flow State Transitions

Pipecat Flows drive state transitions via LLM function calls:

1. LLM reads the current flow state ("introduction", "skill_discovery", etc.).
2. Based on conversation context, LLM calls a transition function (e.g., `skills_identified()`).
3. Pipecat Flows transitions to the next state.
4. `TranscriptRecorder` reads the new state and tags subsequent turns accordingly.

### LiveKit Recording

- LiveKit (self-hosted) records the entire call to local/cloud storage.
- At call end, LiveKit provides a recording metadata object with `recording_url` and `duration`.
- Phase 4 persists `recording_url` to `assessment_sessions.recording_url` for SME review.
- **Note**: The actual MP3 encoding/egress is handled by LiveKit; we just store the URL.

---

## 3. Acceptance Criteria

**Flow State Machine:**
- [ ] `SFIAFlowController` implements all 5 states: Introduction, SkillDiscovery, EvidenceGathering, Summary, Closing.
- [ ] State transitions are driven by LLM function calls (e.g., `consent_given()`, `skills_identified()`, `evidence_complete()`, `summary_complete()`).
- [ ] The flow correctly transitions from Introduction → SkillDiscovery when consent is given.
- [ ] The flow transitions to Closing if consent is declined.
- [ ] SkillDiscovery asks the candidate about their role and responsibilities (no SFIA codes mentioned).
- [ ] EvidenceGathering asks for specific examples per identified skill (focus on autonomy, influence, complexity, knowledge).

**Transcript Persistence:**
- [ ] `TranscriptRecorder` accumulates speaker turns with timestamp, speaker, text, and phase label.
- [ ] Each turn includes VAD confidence (where available from STT provider).
- [ ] Full transcript is persisted to `assessment_sessions.transcript_json` (JSONB) at call end.
- [ ] Transcript schema matches the structure defined in section 1.2.

**LiveKit Recording:**
- [ ] LiveKit recording URL is captured from the call session.
- [ ] Recording URL and duration are persisted to `assessment_sessions.recording_url` and `assessment_sessions.recording_duration_seconds`.

**API Endpoints:**
- [ ] `POST /api/v1/assessment/trigger` accepts `candidate_id`, `phone_number` (or null for browser), and `dialing_method: "browser"`.
- [ ] Trigger endpoint returns `session_id` and initial `status: "dialling"`.
- [ ] `GET /api/v1/assessment/{session_id}/status` returns call status and optional `transcript_snippet` and `livekit_recording_url`.
- [ ] Status endpoint works throughout the call (not just after completion).

**Testing:**
- [ ] Unit tests for flow state transitions with mocked LLM.
- [ ] Unit tests for `TranscriptRecorder` (accumulation, serialization, phase tagging).
- [ ] Integration test: Full call with 5 states completes and transcript is saved.
- [ ] Integration test: LiveKit recording metadata is captured and persisted.

## 4. Prerequisites & Dependencies

**Internal:**
- Phase 1: Monorepo structure, IPersistence and IVoiceTransport ports.
- Phase 2: CallManager, basic voice infrastructure, call lifecycle management.
- Phase 3: LiveKit transport (verified working), STT & TTS providers (tested).

**External:**
- ✅ **STT Provider** (Deepgram, Google Cloud Speech, or equivalent): Tested and working.
- ✅ **TTS Provider** (ElevenLabs, Kokoro, or equivalent): Tested and working.
- ✅ **LLM Provider** (Anthropic Claude, OpenAI GPT-4, or equivalent): Available (soft-required; basic fallback ack in Phase 3 if absent).
- ✅ **LiveKit** (self-hosted): Recording enabled, accessible from voice engine.

**Database schema changes:**
- Phase 1 established `assessment_sessions` table; Phase 4 adds columns `transcript_json`, `recording_url`, `recording_duration_seconds`, `identified_skills`.
- No Prisma migration required if schema is flexible (JSONB); otherwise, create a migration.

## 5. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Pipecat Flows API changes between versions | Pin Pipecat version; review release notes before upgrading. |
| LLM function call parsing fails or returns invalid state names | Add fallback handlers; log invalid calls and transition to error state with retry. |
| VAD (voice activity detection) misses short utterances | Use configured VAD confidence threshold; test with representative candidate voices. |
| LiveKit recording egress is slow or fails silently | Monitor recording callbacks in LiveKit transport; log all recording events; set a 5-minute timeout for recording availability. |
| Transcript JSONB bloat for long calls (60+ min) | Compress transcript on disk; consider archival to S3 for calls >30 min. |
| Phase state transitions are ambiguous from LLM output | Add explicit function signatures with required parameters; validate before transition; log edge cases for manual review. |

## 6. Implementation Sequence

Phase 4 work should follow this order:

1. **Design & schema** (parallel): Define `TranscriptTurn` schema and `assessment_sessions` schema additions; finalize SFIA flow config (system prompts, function names).
2. **TranscriptRecorder** (first): Implement turn accumulation and JSONB serialization; test with mocked VAD/TTS events.
3. **SFIAFlowController** (second): Implement Pipecat Flows config; test with mocked LLM (returns hardcoded functions in order).
4. **LiveKit recording integration** (third): Wire call-end callback to capture recording URL; persist to database.
5. **Endpoint augmentation** (fourth): Add transcript and recording fields to status endpoint response.
6. **End-to-end testing** (fifth): Run full call simulation; verify all 5 states execute in order, transcript is saved, recording URL is captured.
7. **Version bump** (at completion): Bump voice engine version from 0.4.2 to 0.5.0 using `/bump-version` (creates Prisma migration for schema columns).

## 7. Definition of Done

Phase 4 is complete when:

- [ ] All acceptance criteria (section 3) are met.
- [ ] All 5 states (Introduction, SkillDiscovery, EvidenceGathering, Summary, Closing) transition correctly.
- [ ] A full 5-minute test call completes with:
  - [ ] Transcript saved to `assessment_sessions.transcript_json` with ≥10 speaker turns, each tagged with phase.
  - [ ] Recording URL saved to `assessment_sessions.recording_url`.
  - [ ] Status endpoint returns transcript snippet and recording URL.
- [ ] No LLM/external provider logs show errors or retries (beyond initial provider checks).
- [ ] All unit and integration tests pass.
- [ ] Version bumped to 0.5.0 and Prisma migration created (if schema columns added).
- [ ] CHANGELOG.md updated with Phase 4 summary.
- [ ] Phase 4 document moved from `to-be-implemented/` to `implemented/v0.5.0/` with completion notes.

## 8. Revision History

| Date | Author | Change |
|------|--------|--------|
| 2026-04-28 | Doc Refiner | Refine scope: remove interjection, defer RAG to Phase 5, focus on 5-state flow + transcript persistence. Clarify LiveKit recording strategy. Add implementation sequence and Definition of Done. |
