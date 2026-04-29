# PHASE-3 Revision 1: Basic Call Runtime

## Reference

- **Parent Phase:** [`v0.4-phase-3-infrastructure-deployment.md`](./v0.4-phase-3-infrastructure-deployment.md)
- **Parent Implementation:** [`PHASE-3-implementation-infrastructure-deployment.md`](./PHASE-3-implementation-infrastructure-deployment.md)
- **Revision Date:** 2026-04-20
- **Status:** In Progress
- **Implementing Agent:** Cloud Agent (revision request on PR #9)
- **Branch:** `cursor/phase-3-infrastructure-deployment-e139` (same branch as the parent phase)
- **Version bump:** `0.4.0` → `0.4.1` (MINOR — new provider env vars + new adapter code; no schema changes).

---

## Why a Revision

The original Phase 3 document was explicitly scoped to *Infrastructure Deployment* and deferred the Pipecat pipeline + STT/TTS/LLM wiring to Phase 4. That scoping left the Phase 3 success criterion *"A candidate can self-initiate an assessment call"* and *"Calls to real phone numbers work in production"* unsatisfiable — the Daily room was created but no bot joined, no PSTN dial-out was placed, and the session hung at `dialling` forever.

This revision closes that gap with a deliberately narrow scope: one greeting, one question, one LLM-generated acknowledgement, one goodbye, one hangup. Nothing else. No SFIA, no claims, no RAG, no interjections.

## What this Revision Ships

### 1. New provider adapters (all lazily imported — lean CI still builds)

- `AnthropicLLMProvider.complete()` — full implementation against the Anthropic Python SDK (`claude-3-5-haiku-latest` default). Splits `system` prompts from `user` / `assistant` turns, concatenates the Messages API's text blocks.
- Deepgram STT + ElevenLabs TTS are wired via Pipecat's built-in services inside `BasicCallBot._build()` — no custom adapter class needed.

### 2. New domain port

- `ICallLifecycleListener` (`apps/voice-engine/src/domain/ports/call_lifecycle_listener.py`) — three methods: `on_call_connected`, `on_call_ended`, `on_call_failed`. `CallManager` implements it; `DailyVoiceTransport` receives it via setter injection. This satisfies ADR-001 — the transport never imports the domain service.

### 3. Scripted conversation FrameProcessor

- `BasicCallScript` dataclass + helpers in `src/flows/greeting_flow.py` — deterministic dialogue plan (greeting, question, goodbye, fallback ack, system prompt for the ack).
- `ScriptedConversationMixin` in `src/flows/basic_call_bot.py` — pure state machine (`IDLE` → `SPEAKING_GREETING` → `SPEAKING_QUESTION` → `WAITING_FOR_REPLY` → `GENERATING_ACK` → `SPEAKING_ACK` → `SPEAKING_GOODBYE` → `ENDING`), unit-testable without Pipecat.
- `build_scripted_conversation()` composes the mixin with Pipecat's `FrameProcessor` at runtime (lazy import).

### 4. Basic-call bot runner

- `BasicCallBot` in `src/flows/bot_runner.py` builds the Pipecat pipeline (`transport.input() → Deepgram STT → ScriptedConversation → ElevenLabs TTS → transport.output()`), wires Daily event handlers to the `ICallLifecycleListener`, and owns the `PipelineRunner` task.
- Event handlers:
  - `on_joined` → `transport.start_dialout(...)` with optional `callerId`.
  - `on_dialout_answered` / `on_dialout_connected` → `listener.on_call_connected`.
  - `on_dialout_error` → `listener.on_call_failed`, then cancel the task.
  - `on_dialout_stopped` / `on_participant_left` → `listener.on_call_ended`, then cancel the task.
  - Bot-initiated hangup (after the goodbye) → `listener.on_call_ended` + task cancel.

### 5. Daily transport rewrite

- `DailyVoiceTransport.dial()` now creates the room + meeting token, then starts a `BasicCallBot` as a background task.
- The room is created with `enable_dialout: true` and `enable_recording: "cloud"` (recording stays in Daily's dashboard — no `recording_url` writer yet; that's still Phase 4).
- Soft-fails on missing provider credentials: the room is still created (so the audit trail is visible in Daily), but the bot is skipped and the session transitions to `failed` with `metadata.failureReason = "missing_provider_credentials"`.
- `close()` cancels all in-flight bots before tearing down the HTTP client.

### 6. Settings + `.env.example` additions

- `DEEPGRAM_API_KEY`, `DEEPGRAM_MODEL` (default `nova-2-phonecall`).
- `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID` (default `21m00Tcm4TlvDq8ikWAM` / "Rachel").
- `ANTHROPIC_MODEL` (default `claude-3-5-haiku-latest`).
- `DAILY_CALLER_ID` (optional — Daily rotates the workspace pool when blank).
- `BOT_NAME` (default `Noa`), `BOT_ORG_NAME` (default `Resonant`).
- Startup warning when any of `DAILY_API_KEY` / `DEEPGRAM_API_KEY` / `ELEVENLABS_API_KEY` is missing.

### 7. `[voice]` extras bumped

- `pipecat-ai[daily,anthropic,deepgram,elevenlabs,silero]>=0.0.47`.
- `pipecat-ai-flows>=0.0.10` (not consumed yet, but aligned with Phase 4's plan).
- `anthropic>=0.30.0` (already present).
- `loguru>=0.7.0` (Pipecat transitively).

### 8. Test coverage

- `test_basic_call_bot.py` — 6 new tests against `ScriptedConversationMixin` covering the happy path, LLM failure fallback, empty-reply debounce, out-of-state transcripts, idempotent end, and LLM-absent fallback.
- `test_anthropic_llm_provider.py` — 4 new tests with a fake SDK: system-prompt extraction, synthetic user insertion when only system prompts are supplied, missing API key, missing SDK.
- `test_call_lifecycle_listener.py` — 4 new tests: `dialling → in_progress`, `in_progress → completed`, idempotency against terminal statuses, `failed` writes `metadata.failureReason`.
- `test_daily_transport.py` — 3 new tests with `httpx.MockTransport`: REST flow creates room + token, missing provider keys emit `on_call_failed`, unknown-session duration is zero.
- `test_greeting_flow.py` rewritten for the new `BasicCallScript` shape; Phase 2 tests retired.

Total Python test count: 33 → 54 passed, 1 smoke test still skipped.

## Deferrals (unchanged from the plan)

These stay in Phase 4:

- Transcript persistence.
- Recording URL writer (Daily cloud recording is enabled but no DB writer).
- Verbal consent capture / privacy notice / email whitelisting.
- SFIA content, claim extraction, RAG, interjections.
- Structured interview state machine beyond the single-question script.
- Barge-in / interruption handling (the candidate waits for the bot to finish each line).

## Verification

- `./validate.sh` — 10/10 passes locally (ruff, mypy, pytest, Prisma generate, TS build, lint, tests, ADR-001 isolation, required ports/adapters, ADR-002 `@@map` audit).
- Python suite: 54 passed, 1 skipped (smoke, gated by `--run-smoke`).
- Manual live-call verification will be performed by the product owner against a deployed Railway instance, per the runbook appended to `docs/guides/deployed-setup.md` §"First live call".

## Decisions Log (additions to parent doc)

| Date | Decision | Rationale | Files |
|------|----------|-----------|-------|
| 2026-04-20 | Scripted state machine instead of Pipecat Flows for the basic call. | One-question script doesn't justify Flows' declarative overhead. Phase 4's SFIA interview will adopt Flows. | `src/flows/basic_call_bot.py`, `src/flows/greeting_flow.py` |
| 2026-04-20 | `ICallLifecycleListener` is a new port; `CallManager` implements it; `DailyVoiceTransport` receives it via setter injection. | Keeps ADR-001 clean — the transport never imports the domain service. Setter injection resolves the circular dependency at lifespan time. | `src/domain/ports/call_lifecycle_listener.py`, `src/domain/services/call_manager.py`, `src/adapters/daily_transport.py`, `src/main.py` |
| 2026-04-20 | Soft-fail on missing provider keys: create the Daily room, skip the bot, mark the session `failed` with `missing_provider_credentials`. | Keeps local dev + intake smoke tests painless (the API surface works without keys). Surfaces the misconfig visibly in the admin dashboard instead of hanging the candidate UI. | `src/adapters/daily_transport.py`, `src/main.py` |
| 2026-04-20 | LLM defaults to `claude-3-5-haiku-latest`. | Fastest + cheapest Claude family member; one-turn ack doesn't need Sonnet-level reasoning. Configurable via `ANTHROPIC_MODEL`. | `src/config.py`, `src/adapters/anthropic_llm_provider.py` |
| 2026-04-20 | TTS defaults to ElevenLabs "Rachel" (`21m00Tcm4TlvDq8ikWAM`), override via `ELEVENLABS_VOICE_ID`. | Ships a plausible-sounding default so the first production call doesn't need a dashboard tweak. | `src/config.py`, `.env.example` |
| 2026-04-20 | STT defaults to Deepgram `nova-2-phonecall`. | Purpose-built for 8kHz PSTN audio; matches Pipecat examples. | `src/config.py` |
| 2026-04-20 | Reply finalised after a 1.5 s pause in the STT stream; 30 s absolute timeout. | Prevents the bot from racing the candidate mid-sentence while also guaranteeing the call terminates if the candidate falls silent. | `ScriptedConversationMixin._finalise_reply_after_pause`, `_reply_timeout_guard` |
| 2026-04-20 | LLM ack capped at 80 tokens with a 10 s timeout; fallback to `"Thanks for sharing that."` on any failure. | Keeps the call responsive even when Claude is slow/down. | `ScriptedConversationMixin._generate_ack` |

## Revision History

| Date | Revision | Summary | Status |
|------|----------|---------|--------|
| 2026-04-20 | 1 | Basic live-call runtime on top of the Phase 3 infrastructure. | In Progress |
