# PHASE-4 Revision-1: AI Mock Interview Test

## Reference
- **Original Implementation:** `docs/development/implemented/v0.5/PHASE-4-implementation-assessment-workflow.md`
- **Original Phase Document:** `docs/development/to-be-implemented/phase-4-assessment-workflow.md`
- **Revision Date:** 2026-05-02
- **Revision Reason:** Scope expansion — test infrastructure added to validate the full pipeline end-to-end at the transcript level without voice infrastructure

## What Changed

### Original Plan (From Implementation Notes)
Phase 4 delivers the 5-state `SfiaFlowController`, `TranscriptRecorder`, and the Pipecat pipeline integration that wires STT → LLM → TTS → LiveKit. Testing is defined as unit tests for individual components (flow handlers with mocked LLM, TranscriptRecorder with mocked persistence) plus a manual end-to-end test over a live voice call. There is no automated mechanism to exercise the full pipeline — transcript through claim extraction through assessment report — without standing up voice infrastructure.

### New Plan (Revised)
Add a self-contained, voice-free test capability: a shell script that runs an AI-to-AI mock interview. One Claude instance plays the candidate (configurable role, SFIA level, and honesty scale); the existing `SfiaFlowController` drives the interviewer. Turns are exchanged as text; the complete transcript flows through the live `ClaimExtractor` → `ReportGenerator` pipeline. A scorer then compares the system's SFIA level assessments against the configured candidate profile and reports an accuracy score. No telephony, no database, no audio — pure API-level test.

### Why This Revision
The Phase 4 acceptance criteria include an end-to-end integration test ("full call simulation; verify all 5 states execute in order, transcript is saved") but there is no mechanism to run this automatically without a working LiveKit/STT/TTS stack. The mock interview fills that gap: it lets a developer validate the full flow — from conversation through to an assessment report — on a workstation with only an `ANTHROPIC_API_KEY`.

### Impact
- No DB schema changes (uses `InMemoryPersistence`).
- No new API endpoints.
- No version bump required.
- Adds a new `apps/voice-engine/src/testing/` package and `scripts/mock-interview.sh`.
- Does not change any existing production code paths.

---

## Detailed Changes

### Changes to Scope
- **Added deliverable:** `apps/voice-engine/src/testing/` package (6 modules, ~600 LOC)
- **Added deliverable:** `scripts/mock-interview.sh` — shell entry point
- **No PRDs added or removed.**
- **No ADRs changed.** ADR-004 (Pipecat/Daily/FastAPI) is unaffected; the mock driver bypasses Pipecat at the library level but reuses `SfiaFlowController` logic directly.

### Changes to Strategy

- **Original approach:** End-to-end validation requires a real voice call over LiveKit with a human or a hardcoded test script piped through an audio loopback.
- **Revised approach:** A text-mode driver reuses `SfiaFlowController` and all post-call services (`TranscriptRecorder`, `ClaimExtractor`, `ReportGenerator`) by replacing only the transport layer with a Claude API turn-exchange loop.

### Changes to Technical Decisions

| Layer | Original Decision | Revised Decision |
|-------|------------------|-----------------|
| Pipecat dependency for flow | Required for `FlowManager` and node builders | Monkeypatched via `sys.modules["pipecat_flows"]` with a `MockFlowsFunctionSchema` dataclass — node builders run without the library installed |
| Persistence for test | Not specified (implicit: Postgres) | `InMemoryPersistence` — no DB connection needed |
| RAG for test | Requires pgvector seeded with SFIA data | `StubKnowledgeBase` — in-memory SFIA skill definitions for 15+ common codes, all 7 levels |
| LLM for interviewer (Noa) | Pipecat's `LLMProcessor` in pipeline | Direct `AsyncAnthropic` client; model configurable (defaults to the voice engine's configured model) |
| Candidate | Human on phone | `CandidateBot` — Claude instance with persona prompt built from role, SFIA level, and honesty scale |

### Changes to Risk/Unknowns
- **Resolved:** Whether the full pipeline can be exercised without voice infrastructure — yes, via text-mode driver.
- **New risk:** Mock candidate may produce unrealistically structured responses that inflate extraction accuracy. Mitigation: honesty scale can simulate noisy/evasive candidates; scorer reports confidence alongside accuracy.
- **New risk:** `pipecat_flows` monkeypatch is fragile if the real library is installed and its `FlowsFunctionSchema` has validation that our mock skips. Mitigation: the mock is only installed when `pipecat_flows` is absent from `sys.modules`; if the real library is installed the real class is used unchanged.

---

## Revised Implementation Parts

### Part R1: `CandidatePersona` and `CandidateBot`

**File:** `apps/voice-engine/src/testing/candidate_bot.py`

**Goal:** A Claude-backed candidate that answers interview questions according to a configured profile.

**CandidatePersona** (dataclass):

```python
@dataclass
class CandidatePersona:
    role: str          # e.g. "Senior Software Engineer at a fintech startup"
    sfia_level: int    # 1–7 — the candidate's genuine capability level
    honesty: int       # 1–10 — 10=fully truthful, 1=heavily fabricates
    model: str         # e.g. "claude-haiku-4-5-20251001"
```

**Honesty scale interpretation:**

| honesty | Behaviour |
|---------|-----------|
| 9–10 | Accurate — describes real work at the configured SFIA level |
| 6–8 | Slight embellishment — minor exaggeration, presents some group wins as individual |
| 3–5 | Moderate exaggeration — claims credit for observed work, overstates impact |
| 1–2 | Heavy fabrication — invents plausible project names/outcomes, claims 2–3 levels above actual |

**System prompt construction** (abbreviated):
```
You are Alex, a candidate in a skills assessment interview.
Role: {role}
Actual SFIA Level: {sfia_level} ({level_descriptor})
Behaviour: {honesty_instruction}

Keep responses conversational (2–4 sentences). Do not mention SFIA levels or codes explicitly.
When asked for examples, give specific but realistic work scenarios.
```

**Acceptance criteria:**
- `CandidateBot.respond(interviewer_message: str) -> str` maintains conversation history across turns.
- Persona system prompt reflects the configured role, level, and honesty.
- Model is injected (not hardcoded).

---

### Part R2: `MockFlowDriver`

**File:** `apps/voice-engine/src/testing/mock_flow_driver.py`

**Goal:** Drive `SfiaFlowController` through all 5 states by calling its handlers directly, without Pipecat.

**Pipecat monkeypatch:**
```python
import sys, types
from dataclasses import dataclass

if "pipecat_flows" not in sys.modules:
    @dataclass
    class _MockFlowsFunctionSchema:
        name: str; description: str; properties: dict
        required: list; handler: Any

    _mock = types.ModuleType("pipecat_flows")
    _mock.FlowsFunctionSchema = _MockFlowsFunctionSchema
    sys.modules["pipecat_flows"] = _mock
```

This is applied once at module import time. When the real `pipecat_flows` library is installed, the real `FlowsFunctionSchema` is used instead.

**Conversation loop** (pseudocode):
```
current_node = controller.get_initial_node()
messages    = current_node["task_messages"]   # initial task instruction
tools       = [node_func_to_tool(f) for f in current_node["functions"]]

while not done and turn < max_turns:
    response = await noa_client.messages.create(
        system=current_node["role_message"],
        messages=messages,
        tools=tools,
    )

    if response.stop_reason == "tool_use":
        # Noa is transitioning — may also have leading text
        record any text blocks to transcript
        add response.content as assistant message
        for each tool_use block:
            _, new_node = await func.handler(args, mock_fm)
            if name == "call_ended": done = True; break
            # Embed next task instruction inside the tool_result to avoid
            # consecutive user messages (Anthropic API constraint)
            tool_result_content = "OK." + (new_node.task_messages[0].content if new_node else "")
        add tool_results as user message
        if new_node: current_node = new_node; update tools
    else:
        # Pure text — Noa said something; get candidate response
        record noa text to transcript
        messages.append(assistant: noa_text)
        candidate_text = await candidate_bot.respond(noa_text)
        record candidate text to transcript
        messages.append(user: candidate_text)
```

**Key design decisions:**
- Next node's task instruction is embedded in the `tool_result` content to maintain strict user/assistant alternation required by the Anthropic API.
- `max_turns` (default 40) guards against infinite loops if the LLM never calls a transition function.
- The `mock_flow_manager` passed to handlers is `None` — handlers do not use it (they return a new node config directly).

**Acceptance criteria:**
- All 5 states are visited in order for a consent=yes run.
- Closing immediately if consent is declined.
- `recorder.current_phase` reflects the flow state after each transition.
- Raises `MockInterviewTimeoutError` if `max_turns` is exceeded.

---

### Part R3: `StubKnowledgeBase`

**File:** `apps/voice-engine/src/testing/mock_flow_driver.py` (co-located with driver)

**Goal:** In-memory `IKnowledgeBase` that returns SFIA skill definitions without pgvector.

Covers 15 common SFIA 9 skill codes across all 7 levels with short but meaningful descriptions (enough for `ClaimExtractor` to map claims correctly). Skills included: PROG, DENG, CLOP, ARCH, SCTY, ITMG, PRMG, BUAN, TEST, DBAD, NTAS, HSIN, SINT, DESN, DLMG.

**Acceptance criteria:**
- `query(text, ...)` returns the top-k closest skills by simple keyword overlap (no embedding needed for tests).
- `query_by_skill_code(code, ...)` returns all 7 levels for the requested code.

---

### Part R4: `MockInterviewRunner`

**File:** `apps/voice-engine/src/testing/mock_interview_runner.py`

**Goal:** Orchestrate a complete mock interview and return transcript + assessment report.

**Wiring:**
```python
persistence = InMemoryPersistence()
recorder    = TranscriptRecorder()
kb          = StubKnowledgeBase()
controller  = SfiaFlowController(
    recorder=recorder,
    on_call_ended=lambda: None,
    system_prompt=FALLBACK_SYSTEM_PROMPT,
    knowledge_base=kb,
    session_id=session_id,
    post_call_pipeline=None,   # we run it manually after the interview
)
driver      = MockFlowDriver(noa_model=noa_model, candidate_bot=candidate_bot)

await driver.run(controller, recorder)
await recorder.finalize(session_id, persistence,
                        identified_skills=controller.identified_skills)

pipeline    = PostCallPipeline(
    claim_extractor=ClaimExtractor(
        llm_provider=AnthropicClaimLLMProvider(api_key, post_call_model),
        knowledge_base=kb,
    ),
    report_generator=ReportGenerator(persistence, base_url="http://localhost"),
    persistence=persistence,
)
report = await pipeline.process(session_id)
```

**Returns** a `MockInterviewResult` dataclass:
```python
@dataclass
class MockInterviewResult:
    session_id: str
    persona: CandidatePersona
    transcript: dict          # from recorder.to_dict()
    report: AssessmentReport
    turn_count: int
    elapsed_seconds: float
```

---

### Part R5: `MockInterviewScorer`

**File:** `apps/voice-engine/src/testing/scorer.py`

**Goal:** Compare the system's SFIA assessments against the candidate's configured profile.

**Scoring model:**
- For each claim in the report, compute `delta = abs(claim.sfia_level - persona.sfia_level)`.
- `level_accuracy` per claim = `1.0 - (delta / 6)` (0–1 scale; delta=0 → 1.0, delta=6 → 0.0).
- `mean_accuracy` = average across all claims.
- `mean_assessed_level` = average `claim.sfia_level` across all claims.
- `mean_confidence` = average `claim.confidence` across all claims.

**Output** (`ScoreResult` dataclass):
```python
@dataclass
class ScoreResult:
    configured_level: int
    mean_assessed_level: float
    mean_level_delta: float
    mean_accuracy_pct: float        # 0–100
    mean_confidence: float          # 0–1
    total_claims: int
    per_skill: list[PerSkillScore]  # one entry per unique sfia_skill_code
```

**Acceptance criteria:**
- A perfectly honest candidate at SFIA Level 5 produces `mean_assessed_level` ≈ 4.5–5.5 and `mean_accuracy_pct` ≥ 80%.
- A heavily fabricating candidate (honesty=1) at Level 3 claiming Level 6 behaviours produces `mean_assessed_level` > 4.0.

---

### Part R6: CLI and Shell Script

**File:** `apps/voice-engine/src/testing/cli.py`

**Goal:** Argparse-based entry point that reads CLI flags, runs the mock interview, and writes results to a JSON file.

**Arguments:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--role` | str | required | Candidate's job title/context |
| `--sfia-level` | int 1–7 | required | Candidate's genuine SFIA level |
| `--honesty` | int 1–10 | `8` | Honesty scale |
| `--model` | str | `claude-haiku-4-5-20251001` | Candidate bot model |
| `--noa-model` | str | same as `--model` | Interviewer model (Noa) |
| `--post-call-model` | str | `claude-sonnet-4-6` | Claim extraction model |
| `--max-turns` | int | `40` | Safety cap on conversation turns |
| `--output-dir` | path | `./mock-results` | Directory for output JSON |
| `--seed` | int | none | Optional random seed for reproducibility |

**Output file** (`mock-interview-{timestamp}.json`):
```json
{
  "meta": {
    "timestamp": "2026-05-02T10:00:00Z",
    "persona": { "role": "...", "sfia_level": 5, "honesty": 8, "model": "..." },
    "noa_model": "claude-haiku-4-5-20251001",
    "post_call_model": "claude-sonnet-4-6",
    "turn_count": 24,
    "elapsed_seconds": 47.3
  },
  "transcript": { "turns": [...] },
  "report": { "session_id": "...", "claims": [...], "overall_confidence": 0.78 },
  "score": {
    "configured_level": 5,
    "mean_assessed_level": 4.9,
    "mean_level_delta": 0.4,
    "mean_accuracy_pct": 93.3,
    "mean_confidence": 0.78,
    "total_claims": 5,
    "per_skill": [
      { "skill_code": "PROG", "skill_name": "Programming", "configured": 5, "assessed": 5, "delta": 0, "confidence": 0.85, "claim_count": 3 }
    ]
  }
}
```

---

**File:** `scripts/mock-interview.sh`

Thin shell wrapper — activates the voice-engine virtual environment and delegates to the CLI.

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VOICE_ENGINE_DIR="$SCRIPT_DIR/../apps/voice-engine"

if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
  echo "ERROR: ANTHROPIC_API_KEY is not set." >&2; exit 1
fi

cd "$VOICE_ENGINE_DIR"
source .venv/bin/activate 2>/dev/null || true

python -m src.testing.cli "$@"
```

**Example usage:**
```bash
./scripts/mock-interview.sh \
  --role "Senior Software Engineer, 8 years experience in fintech" \
  --sfia-level 5 \
  --honesty 8 \
  --model claude-haiku-4-5-20251001

./scripts/mock-interview.sh \
  --role "Junior developer, 1 year experience" \
  --sfia-level 2 \
  --honesty 2 \
  --model claude-haiku-4-5-20251001 \
  --noa-model claude-sonnet-4-6
```

---

## Next Steps
1. Implement all 6 modules in `apps/voice-engine/src/testing/`.
2. Create `scripts/mock-interview.sh`.
3. Run at least two end-to-end mock interviews: one at honesty=9 and one at honesty=2, and record the score output.
4. Update Phase 4 Definition of Done to include: "Mock interview at SFIA Level 5, honesty=8 completes with `mean_accuracy_pct ≥ 70%`."

---

## Revision Chain
- **Base Implementation:** `docs/development/implemented/v0.5/PHASE-4-implementation-assessment-workflow.md`
- **Previous Revisions:** None
- **This Revision:** Revision-1 — AI Mock Interview Test

---

## Related Documents
- Phase: `docs/development/to-be-implemented/phase-4-assessment-workflow.md`
- Implementation: `docs/development/implemented/v0.5/PHASE-4-implementation-assessment-workflow.md`
- ADR-004: `docs/development/adr/ADR-004-voice-engine-technology.md`
- ADR-005: `docs/development/adr/ADR-005-rag-vector-store-strategy.md`
