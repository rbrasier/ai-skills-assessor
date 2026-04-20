# Deployed Setup Guide — Railway (Phase 3 / v0.4.1)

Phase 3 promotes the Phase 2 voice engine + Next.js web app to a
production Railway (Singapore) deployment. v0.4.1 (Phase 3 Revision 1)
adds the basic-call runtime — a greeting, one question, an
LLM-generated acknowledgement, and a hangup — on top of that
infrastructure. This guide is the source-of-truth walkthrough: env
vars, service layout, migrations, healthchecks, the CI-gated deploy
pipeline, and the "first live call" runbook all match what ships in
v0.4.1.

> **Region**: Railway Singapore (`asia-southeast1`). Daily rooms are
> pinned to the Singapore SFU (`DAILY_GEO=ap-southeast-1`) so the
> voice engine and Daily's media server are co-located. PSTN dial-out
> to Australian +61 numbers is handled by Daily's internal network
> from their Singapore SFU to their Sydney PSTN gateway.
>
> See [ADR-006](../development/adr/ADR-006-deployment-platform.md) for
> the full Railway vs AWS trade-off analysis. The migration trigger
> criteria are unchanged in v0.4.0.

---

## 1. Railway project layout

Create **one Railway project** with three services:

| Service         | Source                | Builder    | Start command                                         |
|-----------------|-----------------------|------------|-------------------------------------------------------|
| `postgres`      | Railway plugin        | (managed)  | (managed)                                             |
| `voice-engine`  | `apps/voice-engine/`  | Dockerfile | `uvicorn src.main:app --host 0.0.0.0 --port $PORT`    |
| `web`           | `apps/web/`           | Dockerfile | `node apps/web/server.js`                             |

Both application services are configured via `railway.json` at the
service root — see `apps/voice-engine/railway.json` and
`apps/web/railway.json`. Railway picks these up automatically when the
service's Root Directory is set to `apps/voice-engine` or `apps/web`
respectively. The `DOCKERFILE` builder references the Dockerfiles
shipped in the repo, so local `docker build` and Railway produce
identical images.

**Root Directory per service** (Railway → Service → Settings → Root
Directory):

| Service        | Root directory        | Dockerfile path (relative to project root) |
|----------------|-----------------------|--------------------------------------------|
| `voice-engine` | `apps/voice-engine`   | `apps/voice-engine/Dockerfile`             |
| `web`          | (repo root)           | `apps/web/Dockerfile`                      |

> The `web` service builds from the **repo root** because its
> Dockerfile needs the pnpm workspace (shared-types + database) in
> scope. Leave its Root Directory unset (or `/`).

---

## 2. Docker images

Both services are built by Railway using the Dockerfiles in this
repo. They're identical to the images produced by
`docker compose up --build` from the repo root.

- `apps/voice-engine/Dockerfile` — Python 3.11-slim, two-stage
  venv build, runs `uvicorn` as a non-root `appuser` user under
  `tini`, with a deep `/health` healthcheck.
- `apps/web/Dockerfile` — Next.js 14 `output: "standalone"` build,
  Node 20-alpine runtime, runs `node apps/web/server.js` as the
  non-root `nextjs` user, with a `/api/health` healthcheck.

---

## 3. Database migrations

Railway's default Postgres plugin does not ship with `pgvector`
enabled. Two paths to enable it:

**Option A (recommended)** — use the "Postgres with pgvector"
template:

1. Railway → New → Plugin → Database → **Postgres (pgvector)**.
2. Railway provisions `postgres:16` with `CREATE EXTENSION vector`
   already whitelisted.

**Option B** — start from the default Postgres plugin and run the
migration on deploy:

1. Railway → New → Plugin → Database → Postgres.
2. Connect to it via `railway connect postgres` (or `psql
   "$DATABASE_URL"`).
3. Run the v0.4.0 migration from a laptop:

   ```bash
   export DATABASE_URL="<railway-provided-url>?sslmode=require"
   pnpm --filter @ai-skills-assessor/database run generate
   pnpm --filter @ai-skills-assessor/database run migrate
   # prisma migrate deploy — runs:
   #   v0_2_0_init_schema
   #   v0_3_0_phase_2_voice_engine
   #   v0_4_0_phase_3_infrastructure
   ```

   The v0.4.0 migration runs `CREATE EXTENSION IF NOT EXISTS vector`
   before creating `skill_embeddings`, so Option B works on any
   modern Postgres where pgvector is installed on the server (most
   Railway Postgres instances today).

Set a Railway **deploy hook** on the `voice-engine` service so new
migrations are applied automatically before the app boots:

```
pnpm --filter @ai-skills-assessor/database run migrate
```

---

## 4. Environment variables

Set these in Railway's **Variables** panel per service. Values prefixed
with `${{…}}` are Railway variable references.

### `voice-engine`

| Key                     | Value / source                                                      |
|-------------------------|---------------------------------------------------------------------|
| `DATABASE_URL`          | `${{postgres.DATABASE_URL}}`                                        |
| `DAILY_API_KEY`         | From Daily dashboard → Developers                                   |
| `DAILY_DOMAIN`          | `your-team.daily.co`                                                |
| `DAILY_GEO`             | `ap-southeast-1` (Singapore SFU — co-located with Railway)          |
| `DAILY_CALLER_ID`       | Optional — Daily phone-number ID. Blank = use workspace pool.       |
| `DEEPGRAM_API_KEY`      | From Deepgram dashboard → Projects → API keys                       |
| `DEEPGRAM_MODEL`        | `nova-2-phonecall` (tuned for 8kHz PSTN audio — recommended)        |
| `ELEVENLABS_API_KEY`    | From ElevenLabs dashboard → Profile → API Keys                      |
| `ELEVENLABS_VOICE_ID`   | Voice ID. Default `21m00Tcm4TlvDq8ikWAM` ("Rachel").                |
| `ANTHROPIC_API_KEY`     | From Anthropic console → API Keys                                   |
| `ANTHROPIC_MODEL`       | `claude-3-5-haiku-latest` (default — fast + cheap for the ack turn) |
| `BOT_NAME`              | `Noa` (default — override per-tenant)                               |
| `BOT_ORG_NAME`          | `Resonant` (default — override per-tenant)                          |
| `LOG_LEVEL`             | `INFO`                                                              |
| `USE_IN_MEMORY_ADAPTERS`| `0` (leave unset or `0` — in-memory adapter is dev-only)            |
| `PORT`                  | Railway injects this — do not override                              |

> **Soft-fail behaviour.** If `DEEPGRAM_API_KEY`, `ELEVENLABS_API_KEY`,
> or `DAILY_API_KEY` is missing, the voice engine still boots and the
> intake / admin endpoints work, but triggering a call will create the
> Daily room, skip the Pipecat bot, and transition the session to
> `failed` with `metadata.failureReason =
> "missing_provider_credentials"`. The admin dashboard surfaces this
> immediately. If `ANTHROPIC_API_KEY` is missing, the call still works
> but uses a hard-coded fallback acknowledgement
> (*"Thanks for sharing that."*) instead of a Claude-generated line.

### `web`

| Key                  | Value / source                                                          |
|----------------------|-------------------------------------------------------------------------|
| `VOICE_ENGINE_URL`   | `http://voice-engine.railway.internal:8080` (Railway private network)   |
| `PORT`               | Railway injects this                                                    |

> Railway's private networking exposes each service on its
> `railway.internal` hostname. Use the internal URL from `web` →
> `voice-engine` so traffic stays inside the Railway fabric.

### `postgres`

No manual configuration — Railway manages it.

---

## 5. Daily configuration

1. Create a Daily account at [daily.co](https://www.daily.co).
2. Ensure **PSTN dial-out** is enabled for your workspace (may require
   contacting Daily support for the initial allow-list).
3. Copy the API key from Daily → Developers.
4. Paste into Railway's `DAILY_API_KEY` variable on the `voice-engine`
   service.
5. Set `DAILY_GEO=ap-southeast-1` on the `voice-engine` service.
   This pins Daily rooms to the Singapore SFU, co-located with
   Railway. PSTN calls to Australian +61 numbers still work — Daily
   routes them internally from the Singapore SFU to their Sydney PSTN
   gateway. To use the Sydney SFU instead (e.g. after migrating to
   AWS), set `DAILY_GEO=ap-southeast-2`.

---

## 6. Health checks

Each service exposes a deep health endpoint that Railway's healthcheck
uses to detect and roll back bad deploys.

| Service         | Path             | Healthy response (200)                                    |
|-----------------|------------------|-----------------------------------------------------------|
| `voice-engine`  | `/health`        | `{"status":"ok", "version":"0.4.0", "database":"ok"}`     |
| `web`           | `/api/health`    | `{"status":"ok", "version":"0.4.0"}`                      |

The voice engine's `/health` returns **503** if the database is
unreachable (see `src/api/routes.py` — Phase 3 added the DB probe via
the `IPersistence.ping()` port). Railway's healthcheck reads this as
"deploy failed" and rolls back to the previous successful revision.

Configure the healthcheck in `railway.json` (already in the repo):

```json
{
  "deploy": {
    "healthcheckPath": "/health",
    "healthcheckTimeout": 30,
    "restartPolicyType": "ON_FAILURE"
  }
}
```

---

## 7. CI/CD pipeline

Deploys are gated by a GitHub Actions workflow
(`.github/workflows/deploy.yml`) that runs the full CI matrix before
redeploying Railway services:

```
push main
  └─► ci-gate (reuses .github/workflows/ci.yml)
        ├─► lint + typecheck + test (TypeScript)
        └─► ruff + mypy + pytest (Python)
  └─► deploy-voice-engine (railway redeploy --service)
  └─► deploy-web          (railway redeploy --service)
  └─► smoke-test          (when vars.SMOKE_TEST_URL is set)
```

Required GitHub secrets/vars (mirror any values you set in Railway):

| Name (scope)                     | Purpose                                        |
|----------------------------------|------------------------------------------------|
| `secrets.RAILWAY_TOKEN`          | Project-scoped deploy token                    |
| `secrets.RAILWAY_PROJECT_ID`     | Target project UUID (optional — CLI infers it) |
| `secrets.RAILWAY_ENVIRONMENT`    | e.g. `production`                              |
| `secrets.RAILWAY_VOICE_ENGINE_ID`| Service ID of the voice-engine service         |
| `secrets.RAILWAY_WEB_ID`         | Service ID of the web service                  |
| `vars.SMOKE_TEST_URL`            | Public URL of the voice-engine (for smoke job) |

Railway also watches `main` directly; the workflow's test gate ensures
we never deploy a failing commit even if someone bypasses the PR.

---

## 8. API surface (v0.4.0)

All routes are proxied by the Next.js app at `/api/assessment/*` and
`/api/admin/sessions`, which in turn call the voice engine's
`/api/v1/*` surface:

| Endpoint                                            | Purpose                                    |
|-----------------------------------------------------|--------------------------------------------|
| `POST /api/v1/assessment/candidate`                 | Create / lookup candidate by email         |
| `POST /api/v1/assessment/trigger`                   | Trigger outbound call                      |
| `GET  /api/v1/assessment/{session_id}/status`       | Poll call status                           |
| `POST /api/v1/assessment/{session_id}/cancel`       | Candidate cancel                           |
| `GET  /api/v1/admin/sessions`                       | Paginated read-only session history        |
| `GET  /health`                                      | Voice engine liveness + DB probe           |

---

## 9. Monitoring & logs

Railway streams stdout/stderr for each service. Highlights to watch:

- **`voice-engine`** — look for `CallManager._place_call failed` log
  lines (raised on Daily / dial errors) and any `InMemoryPersistence
  (USE_IN_MEMORY_ADAPTERS=1)` message — production must always use
  Postgres.
- **`voice-engine`** — 503s from `/health` mean Railway is about to
  roll back. Check `DATABASE_URL` and the `postgres` service.
- **`web`** — 5xx responses from `/api/assessment/*` indicate upstream
  voice-engine failures.

For metric dashboards beyond log streaming, add Datadog or Sentry:
both integrate with Railway via the "Plugins" marketplace and accept
Railway env vars for their ingestion keys.

---

## 10. Smoke test (post-deploy)

After the first production deploy, run the smoke test against the
voice engine URL:

```bash
export SMOKE_TEST_URL="https://voice-engine-prod.up.railway.app"
cd apps/voice-engine
pytest tests/smoke_test.py --run-smoke -q
```

The same command runs automatically in the `smoke-test` job of
`.github/workflows/deploy.yml` when `vars.SMOKE_TEST_URL` is set.

---

## 10a. First live call runbook (v0.4.1)

Once deploys are green and all four provider keys are set, run this
once against the deployed voice engine to prove the basic-call
runtime works end-to-end. You'll need a phone you can answer.

**Pre-flight:**

1. `DAILY_API_KEY`, `DEEPGRAM_API_KEY`, `ELEVENLABS_API_KEY`,
   `ANTHROPIC_API_KEY` all set on the `voice-engine` Railway service.
2. Daily workspace has **PSTN dial-out** enabled (Daily → Support).
3. You have at least one number purchased in Daily (for caller ID) or
   are comfortable with Daily rotating the workspace pool.
4. The Next.js web app's `VOICE_ENGINE_URL` points at the internal
   Railway hostname of the voice-engine service.

**Run:**

```bash
# 1. Candidate intake (your own email — this is a smoke test)
curl -X POST https://<voice-engine-railway-url>/api/v1/assessment/candidate \
  -H 'Content-Type: application/json' \
  -d '{
    "work_email":"you@example.com",
    "first_name":"You",
    "last_name":"Tester",
    "employee_id":"TEST-001"
  }'

# 2. Trigger the call to your own phone (+61 ... for AU)
curl -X POST https://<voice-engine-railway-url>/api/v1/assessment/trigger \
  -H 'Content-Type: application/json' \
  -d '{
    "candidate_id":"you@example.com",
    "phone_number":"+61 4XX XXX XXX"
  }'
# => { "session_id": "...", "status": "pending" }

# 3. Poll status while your phone rings
curl https://<voice-engine-railway-url>/api/v1/assessment/<session_id>/status
```

**Expected sequence:**

| Second | Your side                    | API status         | Railway logs (voice-engine)               |
|--------|------------------------------|--------------------|-------------------------------------------|
| 0      | —                            | `pending`          | `CallManager._place_call` dial start      |
| ~2     | —                            | `dialling`         | `BasicCallBot … start_dialout → +61…`     |
| ~5–15  | Phone rings                  | `dialling`         | Daily WebSocket: `on_joined`              |
| answer | You pick up, hear greeting   | `in_progress`      | `CallManager.on_call_connected`           |
| +1–2s  | Bot asks the question        | `in_progress`      | `ScriptedConversation` → `SPEAKING_QUESTION` |
| you    | You answer (1 sentence)      | `in_progress`      | Deepgram `TranscriptionFrame` received    |
| +1.5s  | Bot says an ack line         | `in_progress`      | `ScriptedConversation` → `SPEAKING_ACK`   |
| +2–4s  | Bot says goodbye and hangs up| `completed`        | `CallManager.on_call_ended`               |

**If something sticks at `dialling` for >30 s:**
- Check voice-engine logs for `dialout error` — usually PSTN isn't
  allow-listed for the target country (contact Daily support).
- Check for `missing_provider_credentials` — one of the four API keys
  isn't set.
- Check the Daily dashboard → Rooms — the room should exist and be
  joinable.

**If the session transitions to `failed`:**

The admin dashboard surfaces `metadata.failureReason` via
`GET /api/v1/admin/sessions`. Common values:

| `failureReason`                   | Fix                                                        |
|-----------------------------------|------------------------------------------------------------|
| `missing_provider_credentials`    | Set `DAILY_API_KEY`, `DEEPGRAM_API_KEY`, `ELEVENLABS_API_KEY` |
| `dial_out_start_failed: …`        | Check Daily PSTN enablement + caller ID                    |
| `dialout_error: busy`             | Candidate's line busy — try again                          |
| `dialout_error: no-answer`        | Candidate didn't pick up within Daily's ring window        |
| `pipeline_crashed: …`             | Voice-engine logs will have a full traceback               |

---

## 11. Rollback

Railway keeps the previous successful deploy. To roll back:

1. Railway → Service → Deployments → select the last good one →
   *Redeploy*.
2. The deep `/health` check will reject a deploy that can't reach
   Postgres, so accidental regressions on the DB wiring auto-rollback.
3. If a migration must be reverted, author a follow-up additive
   migration (Prisma does not ship `down` migrations in `deploy`
   mode).

---

## 12. Future phases

- **Phase 4** will add the full Pipecat pipeline (real STT/TTS/LLM
  providers — Deepgram, ElevenLabs, Anthropic). Expect new env vars
  on the `voice-engine` service.
- **Phase 5** ingests SFIA skill definitions into the
  `skill_embeddings` table (created in v0.4.0 by the Phase 3
  migration).
- **Phase 6** fleshes out `assessment_reports` with the `claims` FK
  and adds the post-call processing pipeline.
- **Phase 7+** adds the SME review portal and production hardening.
