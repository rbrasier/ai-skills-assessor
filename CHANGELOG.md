# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
