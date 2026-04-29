# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.1] - 2026-04-20

### Added — Phase 3 Revision 1: Basic Call Runtime

Closes the gap between v0.4.0's deployment plumbing and Phase 3's
success criterion *"A candidate can self-initiate an assessment call"*
by wiring the Pipecat pipeline end-to-end. Scope deliberately narrow:
one greeting, one question, one LLM-generated ack, one goodbye, one
hangup. See
[`PHASE-3-Revision-1-basic-call-runtime.md`](docs/development/implemented/v0.4/PHASE-3-Revision-1-basic-call-runtime.md).

- **Voice engine — new port**
  - `ICallLifecycleListener` (`src/domain/ports/call_lifecycle_listener.py`)
    with `on_call_connected` / `on_call_ended` / `on_call_failed`. Keeps
    the transport adapter from importing the domain service (ADR-001).
- **Voice engine — `CallManager` changes**
  - Implements `ICallLifecycleListener`: `dialling → in_progress` on
    `on_call_connected`, `→ completed` on `on_call_ended`
    (idempotent against terminal statuses), `→ failed` with
    `metadata.failureReason` on `on_call_failed`.
  - Removed the Phase 2 redundant double-write of `dialling`.
  - Default region changed from `ap-southeast-2` → `ap-southeast-1` to
    match the Railway Singapore deployment.
- **Voice engine — new flow layer**
  - `BasicCallScript` dataclass in `src/flows/greeting_flow.py`:
    greeting, one-sentence question, goodbye, LLM-ack system prompt,
    safe fallback ack.
  - `ScriptedConversationMixin` in `src/flows/basic_call_bot.py`: pure
    state machine (`IDLE → SPEAKING_GREETING → SPEAKING_QUESTION →
    WAITING_FOR_REPLY → GENERATING_ACK → SPEAKING_ACK →
    SPEAKING_GOODBYE → ENDING`), debounced reply finalisation (1.5s
    pause), 30 s reply timeout, 10 s LLM ack timeout with fallback.
  - `build_scripted_conversation()` composes the mixin with Pipecat's
    `FrameProcessor` at runtime (lazy import — the module still loads
    without the `[voice]` extras installed).
- **Voice engine — new bot runner**
  - `BasicCallBot` in `src/flows/bot_runner.py` assembles the Pipecat
    pipeline (`transport.input() → Deepgram STT → ScriptedConversation
    → ElevenLabs TTS → transport.output()`), wires Daily event
    handlers to the listener port, and owns the `PipelineRunner` task.
  - Events wired: `on_joined` → `transport.start_dialout(...)`;
    `on_dialout_answered` / `on_dialout_connected` →
    `on_call_connected`; `on_dialout_error` → `on_call_failed` + task
    cancel; `on_dialout_stopped` / `on_participant_left` →
    `on_call_ended` + task cancel; bot-initiated hangup after goodbye
    → `on_call_ended` + task cancel.
- **Voice engine — adapters**
  - `AnthropicLLMProvider.complete()` fully implemented against the
    Anthropic Python SDK. Splits `system` prompts from user/assistant
    turns, concatenates text blocks, raises a descriptive error when
    the SDK is missing or the API key is empty.
  - `DailyVoiceTransport` rewritten: creates room with
    `enable_dialout: true` and `enable_recording: "cloud"`, launches
    `BasicCallBot` as a background task, soft-fails on missing
    provider credentials (creates the room, skips the bot, marks the
    session `failed` with `metadata.failureReason =
    "missing_provider_credentials"`), cancels in-flight bots on
    `close()`.
- **Voice engine — config**
  - `Settings` extended with `deepgram_api_key`, `deepgram_model`
    (default `nova-2-phonecall`), `elevenlabs_api_key`,
    `elevenlabs_voice_id` (default `21m00Tcm4TlvDq8ikWAM` — "Rachel"),
    `anthropic_model` (default `claude-3-5-haiku-latest`),
    `daily_caller_id` (optional), `bot_name`, `bot_org_name`.
  - `.env.example` documents the new variables; startup warns when
    any of `DAILY_API_KEY` / `DEEPGRAM_API_KEY` / `ELEVENLABS_API_KEY`
    is missing.
  - `main.py` lifespan wires `AnthropicLLMProvider` and injects
    `CallManager` back into the transport as the lifecycle listener.
- **Voice engine — `[voice]` extras**
  - `pipecat-ai[daily,anthropic,deepgram,elevenlabs,silero]>=0.0.47`
    (added `elevenlabs` + `silero`).
  - `pipecat-ai-flows>=0.0.10` (aligned with Phase 4's plan).
  - `loguru>=0.7.0` (Pipecat transitively).
- **Tests**
  - New: `test_basic_call_bot.py` (6 tests — scripted-conversation
    state machine covering happy path, LLM failure, empty reply,
    out-of-state transcripts, idempotent end, no-LLM fallback).
  - New: `test_anthropic_llm_provider.py` (4 tests with a fake SDK —
    system-prompt extraction, synthetic user insertion, missing API
    key, missing SDK).
  - New: `test_call_lifecycle_listener.py` (4 tests — listener-driven
    status transitions).
  - New: `test_daily_transport.py` (3 tests with `httpx.MockTransport`
    — REST flow, soft-fail on missing keys, unknown-session duration).
  - `test_greeting_flow.py` rewritten for the new `BasicCallScript`.
  - Python suite: 33 → 54 passed, 1 smoke skipped.
- **Docs**
  - New `docs/development/implemented/v0.4/PHASE-3-Revision-1-basic-call-runtime.md`.
  - `docs/guides/deployed-setup.md` gains a "First live call" runbook
    and the new env-var list.
  - `docs/guides/local-setup.md` documents the new provider env vars
    and the no-LLM fallback path.

### Changed

- Package versions bumped to `0.4.1` across the TS workspace
  (`package.json`, `apps/web`, `packages/database`,
  `packages/shared-types`) and the Python voice engine
  (`apps/voice-engine/pyproject.toml`).
- Default `CallConfig.region` → `ap-southeast-1` (Railway Singapore).

### Notes

- Phase 3 Revision 1 is strictly the basic-call runtime. Transcripts,
  recording URL writer, consent capture, SFIA content, RAG, claim
  extraction, interjections, and barge-in are all still Phase 4+.
- Recording is enabled on the Daily room so audio is retained in
  Daily's dashboard; no DB writer yet.

## [0.4.0] - 2026-04-20

### Added — Phase 3: Infrastructure Deployment (Railway Singapore)

- **Prisma schema migration** `v0_4_0_phase_3_infrastructure`:
  - Enables the `pgvector` extension (required by ADR-005 for RAG).
  - Creates `skill_embeddings` with a (framework, version, skill, level)
    uniqueness tuple, an IVFFlat cosine index on the `vector(1536)`
    column, and the standard category / subcategory / level metadata —
    ready for SFIA ingestion in Phase 5.
  - Creates a scaffold `assessment_reports` table (sessionId FK,
    reviewToken, status, generatedAt, smeReviewedAt, expiresAt). The
    richer `claims` relation lands in Phase 6.
  - Purely additive: no `DROP`, no data loss — safe on a populated
    v0.3.0 database.
- **Prisma schema** gains `SkillEmbedding` + `AssessmentReport` models,
  enables the `postgresqlExtensions` preview feature, and declares
  `extensions = [vector]` on the datasource.
- **Dockerfiles**:
  - `apps/voice-engine/Dockerfile` — hardened two-stage build: non-root
    `appuser`, `tini` init, `HEALTHCHECK` against `/health`, full
    `[voice]` extras (Pipecat, asyncpg, pgvector, Anthropic).
  - `apps/web/Dockerfile` — new Next.js multi-stage image using
    `output: "standalone"` for a ~150MB runtime, built from the repo
    root so the pnpm workspace is in scope. Runs as non-root
    `nextjs` user with a `/api/health` healthcheck.
- **`docker-compose.yml`** at the repo root — mirrors the Railway
  topology locally (postgres + voice-engine + web) so the full image
  build can be exercised before a push.
- **Railway service manifests** — `apps/voice-engine/railway.json` and
  `apps/web/railway.json` declare builder = Dockerfile, start command,
  healthcheck path, and restart policy so deploys are reproducible
  from source control rather than Railway dashboard clicks.
- **Deploy CI workflow** (`.github/workflows/deploy.yml`) — runs on
  push to `main`: reuses `ci.yml` as the full test gate, then triggers
  Railway redeploys for both services via the Railway CLI, and runs
  the production smoke test when `vars.SMOKE_TEST_URL` is set.
  `ci.yml` now exposes `workflow_call` so `deploy.yml` can reuse it.
- **Deep health check** — `GET /health` on the voice engine now
  returns `{"status","version","database"}` and 503s when the DB is
  unreachable, so Railway's healthcheck can roll back bad deploys.
  `GET /api/health` on the web app now returns the build version.
- **New port method** `IPersistence.ping() -> bool` (ADR-001) — probes
  the backing store without leaking adapter details into
  `/health`. `InMemoryPersistence.ping()` returns `True`;
  `PostgresPersistence.ping()` runs `SELECT 1` via the asyncpg pool.
- **Settings** — `Settings.daily_geo` (default `ap-southeast-1`) and
  `Settings.port` added; `.env.example` documents both.
- **Production smoke test** — `apps/voice-engine/tests/smoke_test.py`
  runs the intake → trigger → status → admin listing flow against a
  live URL. Gated by `--run-smoke` + `SMOKE_TEST_URL` so it never
  runs in normal CI.
- **Docs**:
  - `docs/guides/deployed-setup.md` — rewritten for v0.4.0: Railway
    project layout, Dockerfile-based builds, pgvector migration,
    deep health checks, CI-gated deploy pipeline, post-deploy smoke
    test, rollback procedure.
  - `docs/guides/local-setup.md` — updated to v0.4.0: pgvector
    Postgres image, Phase 3 migration, `docker compose` path, deep
    health endpoint, smoke test.

### Changed

- `CHANGELOG.md` `[0.3.0]` entry is now followed by the new `[0.4.0]`
  block.
- Package versions bumped to `0.4.0` across the TS workspace
  (`package.json`, `apps/web`, `packages/database`,
  `packages/shared-types`) and the Python voice engine
  (`apps/voice-engine/pyproject.toml`).
- `apps/web/next.config.js` opts into `output: "standalone"` so the
  production Docker image is monorepo-aware.

### Notes

- Railway (Singapore) is the MVP deployment target per
  [ADR-006](docs/development/adr/ADR-006-deployment-platform.md). The
  migration trigger criteria for moving to AWS Sydney remain
  unchanged.
- Phase 3 is infrastructure-only: no new user-facing features. Phases
  4–7 build on the validated production environment.

## [0.3.0] - 2026-04-20

### Added — Phase 2: Basic Voice Engine & Call Tracking

- **Prisma schema migration** `v0_3_0_phase_2_voice_engine`:
  - `candidates` switched to email-as-primary-key; added `metadata` JSONB column
    for `employee_id` and other extensible fields; dropped `phoneNumber` /
    `updatedAt` (phone now belongs to each session).
  - `assessment_sessions` gained a `metadata` JSONB column (for
    `failureReason`, `cancelledAt`, …), a `created_at` index, and the
    `candidateId` FK now references `candidates.email`.
- **Shared types** extended with candidate intake + call status contracts
  (`CandidateRequest`, `CandidateResponse`, `TriggerCallRequest`,
  `TriggerCallResponse`, `CallStatusResponse`, `SessionSummary`).
- **Voice engine (Python)**:
  - New domain model `Candidate`, `AssessmentSession.metadata`,
    phone-number normalisation helper.
  - Ports extended: `IPersistence.get_or_create_candidate` /
    `create_session` / `update_session_status` / `query_sessions`;
    `IVoiceTransport.get_call_duration` and optional recording hooks.
  - `CallManager` domain service orchestrates trigger → async dial →
    state updates using only ports.
  - `DailyVoiceTransport` adapter — `httpx`-backed Daily REST client
    (rooms + meeting tokens in `ap-southeast-2`, phone normalisation,
    stubbed dial for Phase 2).
  - `PostgresPersistence` adapter — `asyncpg`-backed implementation of
    the persistence port.
  - `InMemoryPersistence` test adapter.
  - Pipecat Flows `greeting_flow` config (introduce → confirm → thank →
    end) plus stub LLM responses.
- **FastAPI routes**:
  - `POST /api/v1/assessment/candidate` — create/lookup candidate by email.
  - `POST /api/v1/assessment/trigger` — trigger asynchronous outbound call.
  - `GET  /api/v1/assessment/{session_id}/status` — call status polling.
  - `POST /api/v1/assessment/{session_id}/cancel` — candidate-initiated cancel.
  - `GET  /api/v1/admin/sessions` — paginated read-only session history.
- **Next.js frontend** (`apps/web`):
  - Candidate portal at `/` — two-step UI (intake form → call state display),
    2-second status polling, DIALLING / CALL IN PROGRESS / INTERVIEW COMPLETE /
    Failed / Cancelled labels, timer, waveform placeholder, cancel button.
  - Admin dashboard at `/dashboard` — read-only session list with status /
    email / date-range filters.
  - New API-proxy routes under `/api/assessment/*` and `/api/admin/sessions`.
- **Documentation**:
  - `docs/guides/local-setup.md` — local development guide.
  - `docs/guides/deployed-setup.md` — Railway deployment guide.

### Notes

- Phase 2 is a minimal vertical slice: greeting-only conversation,
  stub STT/TTS/LLM providers, recordings stored in Daily's cloud
  indefinitely.
- STUB Daily dial implementation: real Pipecat pipeline + PSTN
  dial-out wired in Phase 3 (voice engine core).

## [0.2.0] - 2026-04-19

### Added — Phase 1: Foundation & Monorepo Scaffold

- pnpm + Turborepo monorepo structure (`pnpm-workspace.yaml`, `turbo.json`).
- Shared TypeScript, ESLint, and Prettier base configurations.
- `packages/shared-types` with `AssessmentTriggerRequest` / `AssessmentTriggerResponse`.
- `packages/database` with Prisma schema for `Candidate` and `AssessmentSession`,
  plus initial migration `v0_2_0_init_schema/migration.sql`.
- `apps/web` Next.js 14 (App Router) shell with `/api/health`,
  `/api/assessment/trigger`, and stub pages for landing (`/`), dashboard
  (`/dashboard`), and SME review (`/review/[token]`).
- `apps/voice-engine` FastAPI shell with:
  - Domain models (`AssessmentSession`, `CallConfig`, `CallConnection`,
    `Transcript`, `TranscriptSegment`, plus stub `Claim` / `SkillDefinition` models).
  - Port interfaces (`IAssessmentTrigger`, `IVoiceTransport`, `IPersistence`).
  - Adapter stubs for Daily transport, pgvector knowledge base, Postgres
    persistence, and Anthropic LLM provider.
  - `/health` and `/api/v1/assessment/trigger` endpoints.
- GitHub Actions CI workflow (`.github/workflows/ci.yml`) covering lint,
  typecheck, build, TypeScript tests, and Python lint/typecheck/tests.

### Notes

- This is the initial scaffold release; no business logic is implemented yet.
- All adapter implementations are stubs that raise `NotImplementedError`; they
  will be filled in by subsequent phases.

## [0.1.0] - 2026-04-18

### Added

- Initial documentation set: PRDs, ADRs, contract specs, and phase plans.
