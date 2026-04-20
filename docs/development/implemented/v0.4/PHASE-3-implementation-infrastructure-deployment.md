# PHASE-3 Implementation: Infrastructure Deployment

## Reference

- **Phase Document:** [`docs/development/implemented/v0.4/v0.4-phase-3-infrastructure-deployment.md`](./v0.4-phase-3-infrastructure-deployment.md)
- **Implementation Date:** 2026-04-20
- **Status:** Completed
- **Implementing Agent:** Cloud Agent (`/implement-phase phase-3`)
- **Branch:** `cursor/phase-3-infrastructure-deployment-e139`
- **Deployment platform decision (user-provided):** Railway (Singapore) — confirms ADR-006.

---

## Verification Record

### PRDs Reviewed

| PRD | Title | Status | Verified | Notes |
|-----|-------|--------|----------|-------|
| PRD-001 | Voice-AI SFIA Skills Assessment Platform | 🟢 Approved | 2026-04-20 | Only PRD referenced by the phase doc. |

PRD-002 (Assessment Interview Workflow) is currently 🔴 Draft, but Phase 3 does **not** reference it — Phase 3 is strictly infrastructure-only and defers the structured interview to Phase 4. The PRD gate is therefore satisfied.

### ADRs Verified

| ADR | Title | Status | Verified |
|-----|-------|--------|----------|
| ADR-001 | Hexagonal Architecture | Accepted | 2026-04-20 |
| ADR-002 | Monorepo Structure (pnpm + Turborepo) | Accepted | 2026-04-20 |
| ADR-004 | Voice Engine Technology (Pipecat, Daily, FastAPI) | Accepted | 2026-04-20 |
| ADR-005 | RAG & Vector Store (pgvector) | Accepted | 2026-04-20 |
| ADR-006 | Deployment Platform (Railway → AWS migration path) | Accepted | 2026-04-20 |

### Version Bump

- Previous version: `0.3.0`
- New version: `0.4.0` (MINOR — Phase 3 ships a new Prisma migration `v0_4_0_phase_3_infrastructure` that enables the `pgvector` extension and creates `skill_embeddings` + a scaffold `assessment_reports` table, plus a new deploy CI workflow and new Dockerfiles).
- `CHANGELOG.md` updated with the `0.4.0` entry.

---

## Phase Summary

Phase 3 promotes the Phase 2 voice engine + Next.js web app from a local-only
stack to a production Railway (Singapore) deployment. It locks in the
deployment platform (ADR-006), enables `pgvector` in Postgres, stamps out the
RAG-ready `skill_embeddings` table (used by Phase 5), adds a minimal
`assessment_reports` scaffold (flesh-out in Phase 6), adds a second Dockerfile
for the Next.js service, wires a GitHub Actions workflow that gates Railway
auto-deploy behind the full CI suite, and ships a production smoke test plus a
deep `/health` endpoint so Railway can roll back bad deploys.

No new user-facing features are shipped in this phase. Feature development
resumes in Phase 4 against the validated infrastructure.

---

## Phase Scope

### Deliverables (as per phase doc §1)

1. **Cloud Infrastructure Setup** — Railway (Singapore) project with three services: `postgres`, `voice-engine`, `web`. `pgvector` extension enabled in Postgres.
2. **CI/CD Pipeline** — `.github/workflows/deploy.yml` (Railway option A). Test gate → Railway deploy.
3. **Database Initialization & Migrations** — `v0_4_0_phase_3_infrastructure/migration.sql` creates the `pgvector` extension, the `skill_embeddings` table (ready for Phase 5), and a minimal `assessment_reports` table (fleshed out in Phase 6).
4. **Containerization** — `apps/voice-engine/Dockerfile` hardened (non-root user, healthcheck); new `apps/web/Dockerfile` for the Next.js service; root-level `docker-compose.yml` for local multi-container testing.
5. **Environment Configuration** — `apps/voice-engine/src/config.py` + `.env.example` extended with `DAILY_GEO`, `DAILY_DOMAIN`, and production `DATABASE_URL` hints. Railway service variables documented in `docs/guides/deployed-setup.md`.
6. **Monitoring & Logging** — Structured JSON logging (Railway log viewer + optional Datadog ingestion); documented in the deployed-setup guide.
7. **Smoke Tests** — `apps/voice-engine/tests/smoke_test.py` runs the end-to-end intake → trigger → status → admin listing flow against a live URL (gated by `SMOKE_TEST_URL`).
8. **Deep Health Check** — `/health` (voice engine) and `/api/health` (web) now return the service version and, for the voice engine, a DB reachability probe so Railway can trigger automatic rollback on DB-less deploys.
9. **Railway Service Manifests** — `railway.json` per service so deploys are reproducible from config rather than clicks.
10. **Definition of Done docs refresh** — `docs/guides/deployed-setup.md` and `docs/guides/local-setup.md` updated to v0.4.0 and cross-checked against the shipped code.

### External Dependencies

- Phase 1 (monorepo scaffold, CI skeleton) — ✅ implemented in v0.2.0.
- Phase 2 (working voice engine + call tracking) — ✅ implemented in v0.3.0.
- A Railway account with a Postgres plugin provisioned in the Singapore region (human action — see `docs/guides/deployed-setup.md` §1).
- A Daily.co account with PSTN dial-out enabled (Phase 2 already documents this).

---

## Implementation Strategy

### Approach

Infrastructure-first, in the order defined by the phase document:

1. Schema/migration (`pgvector`, `skill_embeddings`, `assessment_reports` scaffold) so the new migration is visible to deploy-time automation.
2. Container images (web Dockerfile, voice-engine Dockerfile hardening, `docker-compose.yml`) so deploys are reproducible.
3. Railway service manifests (`railway.json`) alongside each Dockerfile.
4. CI workflow (`.github/workflows/deploy.yml`) — gates Railway auto-deploy behind the same checks as `ci.yml`.
5. Runtime config + deep health check so Railway can detect a bad deploy and roll back automatically.
6. Smoke test that a human can run against production post-deploy.
7. Docs + CHANGELOG refresh; move phase doc into `implemented/v0.4/`.

### Build Sequence

1. Prisma schema + migration → `prisma generate` → validate TS build.
2. Dockerfiles + `docker-compose.yml` → validate images build locally (skipped in CI to keep the workflow fast; documented in `local-setup.md` §10).
3. `railway.json` per service.
4. `deploy.yml` workflow.
5. Deep `/health` + `/api/health` + smoke test.
6. Doc + CHANGELOG refresh.
7. `./validate.sh` green → commit → push → PR.

---

## Known Risks and Unknowns

### Risks

- **Singapore ↔ Sydney media latency unknown until measured in production.** ADR-006 accepts this risk — if P50 > 600ms in production smoke tests, trigger the AWS Sydney migration path documented in ADR-006.
- **Railway auto-deploy without a staging environment.** Mitigation: the deploy workflow runs the full CI suite (`ci.yml`'s jobs) before letting Railway redeploy. Railway then uses the deep `/health` endpoint to roll back automatically if the new deploy fails its healthcheck.
- **Prisma drop-and-replace pattern (used in v0.3.0) is destructive.** v0.4.0 avoids repeating it: the new migration is purely additive (`CREATE EXTENSION` + `CREATE TABLE`), safe on a populated database.

### Unknowns

- Whether Daily's Singapore SFU reliably routes PSTN to `+61` Australian numbers at a sub-600ms round-trip. Will be confirmed by the smoke test on first production deploy.
- Whether Railway's `pgvector` extension is available on the default Postgres plugin or requires the "Postgres with extensions" template. Both paths are documented in the deployed-setup guide §3.

### Scope Clarifications

- **`assessment_reports` table is a scaffold only.** Phase 3 creates the table so Phase 3's acceptance criteria ("assessment_reports table created") is met, but the richer relations to `claims` land in Phase 6. The Phase 3 table intentionally omits `claims` FK; Phase 6 adds it.
- **No staging environment is provisioned.** Phase 3 deploys directly to production with a deep health check + automatic rollback — acceptable for MVP per ADR-006. A staging environment can be added later as a second Railway project.

---

## Implementation Notes

### Part 1: Prisma schema + `v0_4_0_phase_3_infrastructure` migration

- **Goal:** Enable `pgvector` on Railway Postgres and create the `skill_embeddings` + `assessment_reports` tables so Phases 5 and 6 can land without schema work.
- **Acceptance criteria:** `pnpm --filter @ai-skills-assessor/database run migrate` runs cleanly; `prisma generate` still succeeds; `validate.sh` checks 2 + 8 (prisma generate, `@@map` audit) stay green.
- **Key decisions going in:**
  - Additive SQL only — no `DROP TABLE`, no data loss.
  - `embedding` column declared as `Unsupported("vector(1536)")?` so Prisma's TS client ignores it (pgvector requires raw SQL at query time anyway).
  - `skill_embeddings` unique index matches ADR-005's framework/version/skill/level tuple.
- **Blockers:** None.

### Part 2: Container images + local multi-container testing

- **Goal:** Both services build into portable Docker images that run on Railway, AWS, or a laptop.
- **Acceptance criteria:**
  - `docker build -f apps/voice-engine/Dockerfile apps/voice-engine` succeeds (measured by smoke-build in the deploy workflow).
  - `docker build -f apps/web/Dockerfile .` succeeds (Next.js builds the standalone output — requires monorepo context).
  - `docker compose up` from the repo root starts Postgres + voice-engine + web against a local stack.
- **Key decisions going in:**
  - Voice-engine Dockerfile pins `python:3.11-slim`, runs as non-root (`appuser`), and declares `HEALTHCHECK` against `/health`. It still installs the `[voice]` extras so `asyncpg` + Pipecat are available in production.
  - Web Dockerfile uses Next's `output: "standalone"` mode for a smaller runtime image. Build stage installs the whole pnpm workspace so the Next build can reference `@ai-skills-assessor/shared-types`.
- **Blockers:** None.

### Part 3: Railway service manifests

- **Goal:** Capture Railway service config (root dir, build command, start command, healthcheck path) in source control so deploys are reproducible.
- **Acceptance criteria:** Each service has a `railway.json` that Railway picks up on next deploy.
- **Key decisions going in:**
  - Per-service `railway.json` at `apps/voice-engine/railway.json` and `apps/web/railway.json`.
  - Use the `DOCKERFILE` builder (not `NIXPACKS`) so Railway uses the same Dockerfile we test locally.

### Part 4: GitHub Actions `deploy.yml`

- **Goal:** Gate Railway auto-deploy behind the existing CI test suite.
- **Acceptance criteria:** Push to `main` runs the full test matrix; on success, the deploy job triggers Railway redeploys for both services via the Railway CLI; both deploys pass their healthchecks or Railway rolls them back.
- **Key decisions going in:**
  - Re-use `actions/setup-node@v4` + `actions/setup-python@v5` to avoid duplicating CI setup.
  - Use the official Railway CLI (`@railway/cli`) via `npx` rather than a third-party action — the CLI is first-party and supports service-level redeploys with `railway redeploy --service`.
  - Deploy triggers only on `push` to `main`, not on PRs (PRs still get `ci.yml`).

### Part 5: Deep health check + runtime config

- **Goal:** Railway's auto-rollback needs `/health` to fail when the DB is unreachable, not just when the process is dead.
- **Acceptance criteria:**
  - `GET /health` returns `200 {"status":"ok", "version": "0.4.0", "database": "ok"}` when the DB is reachable and `503` when it isn't.
  - `GET /api/health` on the web app returns `{"status":"ok", "version": "0.4.0"}`.
  - `Settings` exposes `daily_geo` and `daily_domain` with sensible defaults.
- **Key decisions going in:**
  - The DB probe lives in the `IPersistence` port (`async def ping() -> bool`) rather than reaching into `asyncpg` directly — stays honest to ADR-001.
  - `InMemoryPersistence.ping()` always returns `True` (it has no failure mode worth testing against here).
  - `PostgresPersistence.ping()` runs `SELECT 1` against its connection pool.

### Part 6: Smoke test

- **Goal:** Reproducible end-to-end smoke test that a human (or a post-deploy job) can run against production.
- **Acceptance criteria:**
  - `pytest apps/voice-engine/tests/smoke_test.py --run-smoke` runs the end-to-end flow against the URL in `SMOKE_TEST_URL`.
  - Skipped automatically in normal CI (no `--run-smoke` flag).
- **Key decisions going in:**
  - Use `httpx.AsyncClient` (already a project dependency) rather than pulling in `requests`.
  - The test is permissive: it accepts that the candidate flow returns 202/200 and that the call may have `failed` status if no Daily key is configured on the target — it only asserts the HTTP surface is reachable and well-formed.

### Part 7: Documentation + CHANGELOG

- **Goal:** Local + deployed setup guides match the shipped code; CHANGELOG records the v0.4.0 entry; phase doc moves into `implemented/v0.4/`.
- **Acceptance criteria:**
  - Both guides open in v0.4.0 heading and reference the new migration, Dockerfiles, `railway.json`, and smoke test.
  - `CHANGELOG.md` has an `## [0.4.0]` section at the top.
  - `docs/development/to-be-implemented/phase-3-*.md` is moved (via `git mv`) to `docs/development/implemented/v0.4/v0.4-phase-3-infrastructure-deployment.md`.

---

## Decisions Log

| Date | Part | Decision | Rationale | Files Affected |
|------|------|----------|-----------|----------------|
| 2026-04-20 | — | Use Railway (Singapore) as the deployment platform for MVP. | User-confirmed. Matches ADR-006's "Railway → AWS migration path" decision. Sub-hour deploy vs weeks of AWS setup, ~$20–60/month vs ~$200–500/month. | ADR-006, this document, deploy workflow |
| 2026-04-20 | 1 | Additive-only migration for v0.4.0 (`CREATE EXTENSION`, `CREATE TABLE`) — no `DROP`. | v0.3.0 already used a destructive drop-and-replace; production data must survive future migrations. | `packages/database/prisma/migrations/v0_4_0_phase_3_infrastructure/migration.sql` |
| 2026-04-20 | 1 | `skill_embeddings.embedding` declared as `Unsupported("vector(1536)")?` in Prisma. | Prisma has no native `vector` type; ADR-005 uses raw SQL for pgvector queries anyway. This keeps Prisma's TS client type-safe without fighting the extension. | `packages/database/prisma/schema.prisma` |
| 2026-04-20 | 1 | `assessment_reports` scaffolded (sessionId, reviewToken, status, generatedAt, expiresAt) only — `claims` FK deferred to Phase 6. | Phase 3 must satisfy the "assessment_reports table created" acceptance criterion without pre-empting Phase 6's richer model. Phase 6 will add `claims` FK via a new additive migration. | Prisma schema, migration |
| 2026-04-20 | 2 | Next.js Dockerfile uses `output: "standalone"` + monorepo-aware build. | Standalone mode ships a ~150 MB image vs ~1 GB for a full `node_modules` image; standard Next pattern. Requires `next.config.js` opt-in. | `apps/web/Dockerfile`, `apps/web/next.config.js` |
| 2026-04-20 | 2 | Voice-engine container runs as `appuser` (non-root) with a `HEALTHCHECK`. | Defence-in-depth baseline; Railway picks up `HEALTHCHECK` for auto-rollback. | `apps/voice-engine/Dockerfile` |
| 2026-04-20 | 3 | One `railway.json` per service using the `DOCKERFILE` builder. | Matches Railway's per-service config model. Source-controlled so deploys don't drift from clicks in the dashboard. | `apps/voice-engine/railway.json`, `apps/web/railway.json` |
| 2026-04-20 | 4 | Railway CLI via `npx @railway/cli redeploy --service` rather than a third-party GitHub Action. | First-party, maintained; supports per-service redeploys; avoids a supply-chain surface. | `.github/workflows/deploy.yml` |
| 2026-04-20 | 5 | DB reachability probe lives on `IPersistence.ping()` (new abstract method). | Keeps the `/health` endpoint adapter-free (ADR-001). `InMemoryPersistence.ping() = True`; `PostgresPersistence.ping()` runs `SELECT 1`. | `apps/voice-engine/src/domain/ports/persistence.py`, both adapters, `src/api/routes.py` |
| 2026-04-20 | 6 | Smoke test gated behind `--run-smoke` (custom pytest marker). | Keeps CI fast; smoke only runs post-deploy against a reachable URL. | `apps/voice-engine/tests/smoke_test.py`, `pyproject.toml` |

---

## Revision History

| Date | Revision | Summary | Status |
|------|----------|---------|--------|
| 2026-04-20 | — | Initial implementation plan | In Progress |

---

## Related Documents

- Phase: `docs/development/to-be-implemented/phase-3-infrastructure-deployment.md` (will move to `docs/development/implemented/v0.4/v0.4-phase-3-infrastructure-deployment.md`)
- PRDs: [`PRD-001`](../../prd/PRD-001-voice-ai-sfia-assessment-platform.md)
- ADRs: [`ADR-001`](../../adr/ADR-001-hexagonal-architecture.md), [`ADR-002`](../../adr/ADR-002-monorepo-structure.md), [`ADR-004`](../../adr/ADR-004-voice-engine-technology.md), [`ADR-005`](../../adr/ADR-005-rag-vector-store-strategy.md), [`ADR-006`](../../adr/ADR-006-deployment-platform.md)
- Guides: [`local-setup.md`](../../../guides/local-setup.md), [`deployed-setup.md`](../../../guides/deployed-setup.md)
