# Deployed Setup Guide — Railway (Phase 2 / v0.3.0)

Phase 2 ships the first remotely-callable version of the platform.
This guide walks through deploying the Next.js web app and the Python
voice engine to [Railway](https://railway.app), backed by Railway's
managed Postgres.

> The voice engine runs in a single region. Daily rooms are created in
> `ap-southeast-2` (Sydney) to minimise PSTN latency for Australian
> candidates — see ADR-004 §2 and the phase doc §1.2.

---

## 1. Railway project layout

Create **one Railway project** with three services:

| Service       | Source          | Start command                               |
|---------------|-----------------|---------------------------------------------|
| `postgres`    | Railway plugin  | (managed)                                   |
| `voice-engine`| `apps/voice-engine` | `uvicorn src.main:app --host 0.0.0.0 --port $PORT` |
| `web`         | `apps/web`      | `pnpm --filter @ai-skills-assessor/web run start -p $PORT` |

Because this is a monorepo, set each service's **Root Directory**
accordingly (Railway → Service → Settings → Root Directory).

---

## 2. Environment variables

Set these in Railway's **Variables** panel for each service.

### `voice-engine`

| Key                   | Value / source                                                  |
|-----------------------|-----------------------------------------------------------------|
| `DATABASE_URL`        | `${{postgres.DATABASE_URL}}` (reference)                        |
| `DAILY_API_KEY`       | From Daily dashboard → Developers                               |
| `DAILY_DOMAIN`        | `your-team.daily.co`                                            |
| `LOG_LEVEL`           | `INFO`                                                          |
| `PORT`                | Railway injects this — do not override                          |

### `web`

| Key                   | Value / source                                                  |
|-----------------------|-----------------------------------------------------------------|
| `VOICE_ENGINE_URL`    | Internal URL of the `voice-engine` service, e.g. `http://voice-engine.railway.internal:8000` |
| `PORT`                | Railway injects this                                            |

### `postgres`

No manual configuration — Railway manages it.

---

## 3. Database migrations

From your laptop (or a one-shot Railway job):

```bash
export DATABASE_URL="<railway-provided-url>"
pnpm --filter @ai-skills-assessor/database run generate
pnpm --filter @ai-skills-assessor/database run migrate   # prisma migrate deploy
```

This runs every migration under
`packages/database/prisma/migrations/` in order, including
`v0_3_0_phase_2_voice_engine`.

For ongoing deploys, prefer a Railway **deploy hook**:

```
pnpm --filter @ai-skills-assessor/database run migrate
```

…run before each new build of the `voice-engine` service.

---

## 4. Daily configuration

1. Create a Daily account at [daily.co](https://www.daily.co).
2. Ensure **PSTN dial-out** is enabled for your workspace (may require
   contacting Daily support for the initial allow-list).
3. Copy the API key from Daily → Developers.
4. Paste into Railway's `DAILY_API_KEY` variable on the `voice-engine`
   service.
5. `DailyVoiceTransport` pins rooms to `ap-southeast-2` — no extra
   configuration needed; overridable via the `CallConfig.region`
   domain object if you need to experiment.

---

## 5. Health checks

Each service exposes a health endpoint. Configure Railway's built-in
health check:

| Service | Path             | Expected body      |
|---------|------------------|--------------------|
| `voice-engine` | `/health`  | `{"status":"ok"}`  |
| `web`   | `/api/health`    | `{"status":"ok"}`  |

Setting these lets Railway roll back a bad deploy automatically.

---

## 6. API surface (v0.3.0)

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
| `GET  /health`                                      | Voice engine liveness                      |

---

## 7. Monitoring & logs

Railway streams stdout/stderr for each service. Highlights to watch:

- **`voice-engine`** — look for `CallManager._place_call failed` log
  lines (raised on Daily / dial errors).
- **`voice-engine`** — `InMemoryPersistence (USE_IN_MEMORY_ADAPTERS=1)`
  means the adapter fell back; production deploys should always use
  Postgres.
- **`web`** — 5xx responses from `/api/assessment/*` indicate upstream
  voice-engine failures.

---

## 8. Rollback

Railway keeps the previous successful deploy. To roll back:

1. Railway → Service → Deployments → select the last good one → *Redeploy*.
2. If a migration must be reverted, author a follow-up migration
   (Prisma does not ship `down` migrations in `deploy` mode).

---

## 9. Future phases

- **Phase 3** will add real STT/TTS/LLM providers (Deepgram, ElevenLabs,
  Anthropic). Expect new env vars and new internal services.
- **Phase 4+** will add claim extraction, RAG knowledge base, SME
  review portal. Plan for additional DB migrations and storage.
