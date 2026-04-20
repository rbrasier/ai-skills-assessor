# PHASE-2 Implementation: Basic Voice Engine & Call Tracking

## Reference

- **Phase Document:** `docs/development/implemented/v0.3/v0.3-phase-2-basic-voice-engine.md`
- **Implementation Date:** 2026-04-20
- **Status:** Completed (validation passing locally; awaiting first CI run on the PR)
- **Implementing Agent:** Cloud Agent (`/implement-phase phase-2`)
- **Branch:** `cursor/phase-2-basic-voice-engine-2fc6`

---

## Verification Record

### PRDs Reviewed

| PRD | Title | Status | Verified | Notes |
|-----|-------|--------|----------|-------|
| PRD-001 | Voice-AI SFIA Skills Assessment Platform | 🟢 Approved | 2026-04-20 | — |
| PRD-002 | Assessment Interview Workflow | 🔴 Draft | 2026-04-20 | Phase 2 explicitly defers the structured interview (Phase 3+); PRD-002 is not required to be Approved for this phase. Phase doc only lists PRD-001 as a direct reference. |

### ADRs Verified

| ADR | Title | Status | Verified |
|-----|-------|--------|----------|
| ADR-001 | Hexagonal Architecture | Accepted | 2026-04-20 |
| ADR-002 | Monorepo Structure (pnpm + Turborepo) | Accepted | 2026-04-20 |
| ADR-004 | Voice Engine Technology (Pipecat, Daily, FastAPI) | Accepted | 2026-04-20 |
| ADR-005 | RAG & Vector Store (pgvector) | Accepted | 2026-04-20 |

### Version Bump

- Previous version: `0.2.0`
- New version: `0.3.0` (MINOR — Phase 2 ships a new Prisma migration `v0_3_0_phase_2_voice_engine` and four new API endpoints).
- `CHANGELOG.md` updated with the `0.3.0` entry.

---

## Phase Summary

Phase 2 turns the Phase 1 scaffold into a working candidate self-service
assessment entry point: candidates fill in an intake form on the web
portal, the system creates `Candidate` + `AssessmentSession` rows, the
voice engine triggers an asynchronous outbound call via Daily, and the
candidate watches real-time state transitions (`DIALLING` →
`CALL IN PROGRESS` → `INTERVIEW COMPLETE`). A read-only admin dashboard
lists sessions with filters.

The real Pipecat PSTN dial-out is still stubbed (no Daily account
required to pass CI); `DailyVoiceTransport.dial` talks to Daily's REST
API for room + token creation and returns a `CallConnection` without
actually joining a room. Phase 3 will plug in the Pipecat pipeline
(STT/TTS/LLM providers) and replace the stub.

---

## Phase Scope

### Deliverables (as per phase doc)

1. `IVoiceTransport` port extended with `get_call_duration` and optional
   recording hooks.
2. `IPersistence` port extended with candidate CRUD, session creation,
   status updates, and admin querying.
3. `DailyVoiceTransport` adapter (httpx-backed Daily REST + stub dial).
4. `PostgresPersistence` adapter (asyncpg-backed).
5. `InMemoryPersistence` test adapter.
6. `CallManager` domain service (session creation, async dial,
   status polling, cancellation).
7. `greeting_flow` Pipecat Flows config (introduce → confirm → thank → end)
   with stub LLM responses.
8. FastAPI routes:
   - `POST /api/v1/assessment/candidate`
   - `POST /api/v1/assessment/trigger`
   - `GET  /api/v1/assessment/{session_id}/status`
   - `POST /api/v1/assessment/{session_id}/cancel`
   - `GET  /api/v1/admin/sessions`
9. Next.js `/` — two-step candidate portal (intake form → call status).
10. Next.js `/dashboard` — read-only session list.
11. Prisma migration `v0_3_0_phase_2_voice_engine`:
    - `candidates.email` becomes primary key; drop `phoneNumber`, `updatedAt`; add `metadata` JSONB.
    - `assessment_sessions` gains `metadata` JSONB and `created_at` index; FK switches to `candidates.email`.
12. Docs: `docs/guides/local-setup.md`, `docs/guides/deployed-setup.md`.

### External Dependencies

- Phase 1 scaffold (monorepo, Prisma package, FastAPI shell).
- Daily API key (optional for Phase 2 — only required when running the
  stub against a real Daily account; CI uses env-var fallback).

---

## Implementation Strategy

### Approach

Followed the build sequence from the phase document (Section 5):
schema → ports → domain → adapters → API → UI → docs → tests →
validation. Rationale: each layer depends on the previous, so the
order minimises rework. Domain and adapter stubs can be unit-tested
without real Daily / Postgres credentials.

### Build Sequence

1. Version bump (`0.2.0 → 0.3.0`) + CHANGELOG + phase-doc move.
2. Shared TS types (candidate + status contracts).
3. Prisma schema + migration `v0_3_0_phase_2_voice_engine`.
4. Voice-engine domain models (`Candidate`, `AssessmentSession.metadata`),
   ports (`IPersistence`, `IVoiceTransport`).
5. `CallManager` domain service + `InMemoryPersistence` test adapter.
6. `DailyVoiceTransport` adapter (httpx REST + normalisation).
7. `PostgresPersistence` adapter (asyncpg).
8. `greeting_flow` config.
9. FastAPI routes + wiring in `main.py`.
10. Next.js candidate portal (`/`) and admin dashboard (`/dashboard`).
11. Next.js API proxy routes (`/api/assessment/*`, `/api/admin/sessions`).
12. Docs (`local-setup.md`, `deployed-setup.md`).
13. Tests (unit for domain, FastAPI TestClient integration).
14. `./validate.sh` and fix-until-green.

---

## Known Risks and Unknowns

### Risks

- **Daily PSTN dial-out is stubbed.** The full Pipecat pipeline (VAD,
  STT, TTS, LLM) is out of scope until Phase 3. The phase doc itself
  flags this as acceptable (“stub LLM provider for Phase 2”). Risk:
  end-to-end call behaviour cannot be verified without a paid Daily
  account and real STT/TTS; mitigated by exercising the REST calls in
  integration tests with mocked `httpx` responses.
- **Postgres isn't available in CI.** `PostgresPersistence` is
  exercised only via contract tests (ensuring the adapter matches the
  port shape). Functional tests run against `InMemoryPersistence`.
- **Schema change is potentially data-lossy.** The migration drops
  `candidates.phoneNumber`/`updatedAt`, changes the PK from `id` to
  `email`, and re-keys the `assessment_sessions.candidateId` FK. Safe
  now because Phase 1 shipped no production data; captured explicitly
  in the migration SQL so reviewers see the intent.

### Unknowns

- **Recording URL timing.** Daily may not surface the recording URL
  until after the call disconnects. `DailyVoiceTransport` leaves
  `recording_url=None` until the (future) disconnect handler lands.
- **Retention policy.** Phase doc says "recordings stored
  indefinitely"; Phase 3+ may need to revisit.

### Scope Clarifications

- **Kept candidate `id` UUID + `email` unique+indexed, rather than making
  `email` the literal primary key.** The phase doc example uses email
  as `@id`, but a UUID PK is safer (emails can change; FK cascades are
  nicer on an immutable key). The behaviour is identical from the API
  perspective (`candidate_id` returned equals the email). The existing
  schema already keyed `Candidate` by UUID with a unique index on
  `email`, so this is additive rather than a breaking change.

  **Update:** Revised during implementation to match the phase doc
  literally — `Candidate.email` is now the primary key. See Decisions Log.
- **Stub dial returns a `CallConnection` without joining a room.** Real
  Pipecat integration is explicitly deferred (phase doc §1.3); the
  stub is sufficient to drive status transitions via `CallManager`.

---

## Implementation Notes

### Part 1: Schema + shared types

- **Goal:** `candidates` and `assessment_sessions` carry the Phase 2
  metadata shape (JSONB `metadata` columns, email PK on candidate,
  indexed `created_at`).
- **Acceptance criteria:** Migration generates cleanly; shared-types
  exports compile; new types are re-exported by `apps/web/src/lib/types.ts`.
- **Key decisions:** JSONB columns for forward compatibility
  (`employee_id`, `failureReason`, `cancelledAt`, …). Index
  `assessment_sessions(created_at)` for admin dashboard pagination
  by date.

### Part 2: Voice-engine domain + ports

- **Goal:** Extend ports to cover every operation `CallManager` and
  the API routes need, keeping `src/domain/` free of adapter imports.
- **Acceptance criteria:** Validation Check 6 (domain isolation)
  still green; `mypy` clean.

### Part 3: Adapters

- `DailyVoiceTransport` uses `httpx.AsyncClient` for Daily REST
  (`/v1/rooms`, `/v1/meeting-tokens`). Phone numbers normalised to
  E.164 before any dialling.
- `PostgresPersistence` uses `asyncpg` with raw SQL against the
  Prisma-managed tables (snake_case column names via explicit
  `SELECT ... AS ...`). No ORM; the adapter owns the mapping.
- `InMemoryPersistence` mirrors the port shape with dicts, used by
  the domain tests and the FastAPI test client.

### Part 4: `CallManager`

- Creates the session as `pending` → kicks off `asyncio.create_task`
  for the dial → transitions to `dialling` before the HTTP call →
  depends on Daily event handlers (later) to transition to
  `in_progress` / `completed`.
- `get_call_status` merges persistence state with the live call
  duration (from `IVoiceTransport.get_call_duration`).

### Part 5: FastAPI routes

- Input validation via Pydantic (EmailStr, non-empty strings, phone
  regex). All errors map to `400 Invalid form data. Please update and
  try again.` as per phase doc.
- Routes read the singleton `CallManager` from `app.state` (set in
  `main.py`). Tests override `app.state.call_manager` with an
  in-memory instance via a FastAPI dependency override.

### Part 6: Next.js frontend

- `/` — two-step candidate portal: intake form (FIRST NAME, LAST
  NAME, WORK EMAIL, EMPLOYEE ID, PHONE NUMBER) → call state display
  (DIALLING / CALL IN PROGRESS / INTERVIEW COMPLETE / Failed /
  Cancelled). Status polled every 2 s against
  `/api/assessment/{id}/status`.
- `/dashboard` — read-only list of sessions with status / email /
  date-range filters, 50/page pagination, polling every 5 s.
- All browser → API calls go through Next.js proxy routes at
  `/api/assessment/*` and `/api/admin/sessions` which forward to the
  voice engine (`VOICE_ENGINE_URL`, default `http://localhost:8000`).

### Part 7: Docs

- `docs/guides/local-setup.md` — covers pnpm install, Postgres
  (docker-compose snippet), Prisma migrate, voice-engine venv,
  `.env` values, and running `turbo dev` + `uvicorn`.
- `docs/guides/deployed-setup.md` — Railway deployment: service
  layout, environment variables, Postgres plugin, Daily API
  credentials, health-check configuration.

---

## Decisions Log

| Date | Part | Decision | Rationale | Files Affected |
|------|------|----------|-----------|----------------|
| 2026-04-20 | — | Initial implementation plan created | — | This document |
| 2026-04-20 | Version | Bump `0.2.0 → 0.3.0` (MINOR) | Phase 2 adds new Prisma migration + four new API endpoints; per `/bump-version`, MINOR required. | `package.json`, `apps/web/package.json`, `apps/voice-engine/pyproject.toml`, `packages/database/package.json`, `packages/shared-types/package.json`, `CHANGELOG.md` |
| 2026-04-20 | Schema | Make `Candidate.email` the primary key (rather than keep UUID + unique email) | Phase doc §1.9 specifies `email String @id`. Behaviour is otherwise identical — candidate metadata stays extensible via `metadata` JSONB. Migration is authored as a fresh replacement of the Phase 1 tables (no production data yet). | `packages/database/prisma/schema.prisma`, `packages/database/prisma/migrations/v0_3_0_phase_2_voice_engine/migration.sql` |
| 2026-04-20 | Adapters | Use `asyncpg` (no ORM) for `PostgresPersistence` | Keeps the Python side free of Prisma’s Node-only client; snake_case columns map cleanly. Prisma remains the schema source of truth and runs migrations. | `apps/voice-engine/src/adapters/postgres_persistence.py` |
| 2026-04-20 | Adapters | Stub `DailyVoiceTransport.dial` — REST only, no Pipecat pipeline | Phase doc §1.3 explicitly defers Pipecat wiring to Phase 3. Stub still exercises Daily room/token creation and E.164 normalisation. | `apps/voice-engine/src/adapters/daily_transport.py` |
| 2026-04-20 | Domain | Add `InMemoryPersistence` alongside `PostgresPersistence` | Enables end-to-end FastAPI tests with no Postgres dependency; mirrors the Phase 1 in-memory transport pattern. | `apps/voice-engine/src/adapters/in_memory_persistence.py` |
| 2026-04-20 | API | `CallManager` singleton wired in `app.state` | Matches the pattern Phase 1 established; lets tests inject a fake manager via FastAPI dependency overrides. | `apps/voice-engine/src/main.py`, `apps/voice-engine/src/api/routes.py` |
| 2026-04-20 | Frontend | Two-step candidate portal as a single client component with `step` state | Matches the phase doc's "same page, real-time transitions" requirement; keeps the routing surface minimal. | `apps/web/src/app/page.tsx`, `apps/web/src/components/**` |

---

## Validation Record

All ten `./validate.sh` checks pass locally. Python suite: **32 tests
passed** (Phase 1 orchestrator, CallManager, phone normalisation,
greeting flow, and end-to-end FastAPI routes via TestClient).

| Date | Check | Result | Notes |
|------|-------|--------|-------|
| 2026-04-20 | `pnpm install` | ✅ Pass | — |
| 2026-04-20 | `prisma generate` | ✅ Pass | Regenerates client after schema change. |
| 2026-04-20 | `pnpm build` (turbo) | ✅ Pass | 0 TS errors. `/dashboard`, `/api/admin/sessions`, and the new `/api/assessment/*` routes compile. |
| 2026-04-20 | `pnpm lint` | ✅ Pass | 0 warnings. |
| 2026-04-20 | `pnpm test` | ✅ Pass | TS suites remain placeholders (Phase 1 pattern). |
| 2026-04-20 | ADR-001 domain isolation | ✅ Pass | `src/domain/` imports stay clean. |
| 2026-04-20 | Required ports / adapters | ✅ Pass | All 10 required files present (5 ports + 4 adapters + schema). |
| 2026-04-20 | ADR-002 `@@map` directives | ✅ Pass | 2 / 2 models mapped to snake_case. |
| 2026-04-20 | `ruff` + `mypy` | ✅ Pass | 31 source files, 0 issues. |
| 2026-04-20 | `pytest` | ✅ Pass | **32 passed**. |

---

## Revision History

| Date | Revision | Summary | Status |
|------|----------|---------|--------|
| 2026-04-20 | — | Initial implementation plan | In Progress |
| 2026-04-20 | r1 | Phase 2 implementation landed. Prisma schema updated, voice-engine ports/adapters extended, FastAPI routes added, Next.js candidate portal and admin dashboard built, docs written. All 10 validation checks passing (32 Python tests, 0 TS errors / lint warnings). | Completed |

---

## Related Documents

- Phase: `docs/development/implemented/v0.3/v0.3-phase-2-basic-voice-engine.md`
- PRDs: `docs/development/prd/PRD-001-voice-ai-sfia-assessment-platform.md`
- ADRs: `docs/development/adr/ADR-001-hexagonal-architecture.md`, `docs/development/adr/ADR-002-monorepo-structure.md`, `docs/development/adr/ADR-004-voice-engine-technology.md`, `docs/development/adr/ADR-005-rag-vector-store-strategy.md`
