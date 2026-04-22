# Local Setup Guide — Phase 3 (v0.4.2)

This guide gets the AI Skills Assessor running end-to-end on a laptop:
candidate intake form → Python voice engine → Postgres. v0.4.1
(Phase 3 Revision 1) adds the basic-call runtime — a greeting, one
question, an LLM-generated acknowledgement, and a hangup — on top of
the v0.4.0 deploy plumbing (pgvector, Railway service manifests,
hardened Dockerfiles, deep health checks, smoke test).

The full structured interview (SFIA, claim extraction, transcripts,
interjections) is still Phase 4+.

---

## 1. Prerequisites

| Tool         | Version    | Notes                                            |
|--------------|------------|--------------------------------------------------|
| Node.js      | ≥ 20.x     | `.nvmrc` pins `20`.                              |
| pnpm         | ≥ 10.x     | `packageManager` pins `pnpm@10.33.0`.            |
| Python       | 3.11+      | Voice engine targets 3.11 but runs on 3.12.      |
| Docker       | any        | Easiest way to run Postgres locally.             |
| `make` / bash| —          | Some helper scripts are POSIX shell.             |

**Transport:** set `DIALING_METHOD` in `apps/voice-engine/.env` to `daily`
(telephone via Daily) or `browser` (self-hosted LiveKit). In `daily` mode, a
Daily API key and domain are **required** at process startup. In `browser` mode,
use `LIVEKIT_URL`, `LIVEKIT_API_KEY`, and `LIVEKIT_API_SECRET` instead; Daily
variables are not read.

---

## 2. Clone & install

```bash
git clone <repo>
cd ai-skills-assessor

pnpm install                             # TS workspace
cd apps/voice-engine
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"        # lean install (no Pipecat)
# Or, when you need asyncpg + Pipecat:
# .venv/bin/pip install -e ".[voice,dev]"
```

---

## 3. Database (Postgres with pgvector)

Phase 3 requires the pgvector extension. The simplest path is the
community `pgvector/pgvector` image. Use the automated `setup-local.sh`
script (see §2) which handles Docker creation and permissions correctly.

Alternatively, set up manually:

```bash
# Create container with postgres DB, then create app DB as superuser
docker run --name ai-skills-pg \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=postgres \
  -p 5432:5432 -d pgvector/pgvector:pg16

# Wait for startup, then create the app database
sleep 5
docker exec ai-skills-pg psql -U postgres -d postgres -c \
  "CREATE DATABASE ai_skills_assessor OWNER postgres;"
```

Then from the repo root:

```bash
export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/ai_skills_assessor"

pnpm --filter @ai-skills-assessor/database run generate   # prisma client
pnpm --filter @ai-skills-assessor/database run migrate    # prisma migrate deploy
```

This runs all three migrations in order:

1. `v0_2_0_init_schema` (Phase 1) — baseline tables.
2. `v0_3_0_phase_2_voice_engine` (Phase 2) — candidate + session
   reshape.
3. `v0_4_0_phase_3_infrastructure` (Phase 3) — `CREATE EXTENSION
   vector` + `skill_embeddings` + `assessment_reports` scaffold.

All three are safe on an empty dev DB. The Phase 3 migration is
purely additive, so it is also safe against a populated v0.3.0 DB.

---

## 4. Environment variables

Copy the per-package `.env.example` files:

```bash
cp apps/voice-engine/.env.example apps/voice-engine/.env
cp apps/web/.env.example          apps/web/.env.local
cp packages/database/.env.example packages/database/.env
```

Populate `apps/voice-engine/.env`:

```bash
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/ai_skills_assessor

# How the candidate connects: daily = telephone, browser = WebRTC in browser (LiveKit)
DIALING_METHOD=daily

# Daily (only when DIALING_METHOD=daily; required in that case)
DAILY_API_KEY=
DAILY_DOMAIN=                # e.g. "your-team.daily.co"
DAILY_GEO=ap-southeast-1     # Singapore SFU — see ADR-006
DAILY_CALLER_ID=             # optional

# LiveKit (only when DIALING_METHOD=browser)
# LIVEKIT_URL=wss://your-server:7880
# LIVEKIT_API_KEY=
# LIVEKIT_API_SECRET=
# LIVEKIT_MEET_URL=https://meet.livekit.io/custom

# AI providers (Phase 3 Revision 1)
ANTHROPIC_API_KEY=           # optional — missing key = hard-coded fallback ack
ANTHROPIC_MODEL=claude-3-5-haiku-latest
DEEPGRAM_API_KEY=            # required to place a call
DEEPGRAM_MODEL=nova-2-phonecall
ELEVENLABS_API_KEY=          # required to place a call
ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM

# Bot identity
BOT_NAME=Noa
BOT_ORG_NAME=Resonant

LOG_LEVEL=INFO
PORT=8000

# Set to "1" to bypass Postgres and use InMemoryPersistence instead —
# useful if you want to kick the tyres without running migrations.
USE_IN_MEMORY_ADAPTERS=0
```

> **Soft-fail (STT/TTS).** Missing `DEEPGRAM_API_KEY` / `ELEVENLABS_API_KEY` at
> boot is a warning (not fatal). A trigger with those missing skips the bot. For
> **Daily vs LiveKit** credentials, the process fails fast on startup if the
> wrong set is empty (e.g. `DIALING_METHOD=daily` with blank `DAILY_API_KEY`).
> Missing
> `ANTHROPIC_API_KEY` is non-fatal for the call itself — the bot will
> use its hard-coded acknowledgement *"Thanks for sharing that."*
> instead of a Claude-generated line.

And `apps/web/.env.local`:

```bash
VOICE_ENGINE_URL=http://localhost:8000
```

---

## 5. Run the stack (native processes)

In three terminals:

```bash
# 1. Voice engine (FastAPI)
cd apps/voice-engine
.venv/bin/uvicorn src.main:app --reload --port 8000

# 2. Web app (Next.js)
pnpm --filter @ai-skills-assessor/web run dev

# 3. (optional) Postgres psql for poking around
psql "$DATABASE_URL"
```

Open <http://localhost:3000>:

- `/` — candidate portal (Step 01 form → Step 02 call status).
- `/dashboard` — read-only admin dashboard.

---

## 6. Run the stack (docker compose)

Phase 3 added a root-level `docker-compose.yml` that mirrors the
Railway topology. Use it to exercise the full image-build path
before a push:

```bash
# Build and start postgres + voice-engine + web
docker compose up --build

# Health probes
curl http://localhost:8000/health
# {"status":"ok","version":"0.4.0","database":"ok"}
curl http://localhost:3000/api/health
# {"status":"ok","version":"0.4.0"}

# Stop the stack (volume persists)
docker compose down

# Wipe the DB volume too
docker compose down -v
```

You still need to run the Prisma migrations once — the compose file
does not bake a migrate step (Railway deploy hooks handle that in
production). From the host:

```bash
export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/ai_skills_assessor"
pnpm --filter @ai-skills-assessor/database run migrate
```

---

## 7. Smoke test (post-deploy only)

The end-to-end smoke test in `apps/voice-engine/tests/smoke_test.py`
is gated behind `--run-smoke` and `SMOKE_TEST_URL` so it never runs
during normal local testing. To run it against a staging or
production URL:

```bash
export SMOKE_TEST_URL="https://voice-engine-prod.up.railway.app"
cd apps/voice-engine
pytest tests/smoke_test.py --run-smoke -q
```

---

## 8. Smoke test (local, manual)

```bash
# 1. Health (voice engine deep check: status + version + DB)
curl http://localhost:8000/health
# {"status":"ok","version":"0.4.0","database":"ok"}

# 2. Create candidate
curl -X POST http://localhost:8000/api/v1/assessment/candidate \
  -H 'Content-Type: application/json' \
  -d '{"work_email":"amara@helixrobotics.com","first_name":"Amara","last_name":"Okafor","employee_id":"HLX-00481"}'

# 3. Trigger call
curl -X POST http://localhost:8000/api/v1/assessment/trigger \
  -H 'Content-Type: application/json' \
  -d '{"candidate_id":"amara@helixrobotics.com","phone_number":"+44 7700 900118"}'

# 4. Status
curl http://localhost:8000/api/v1/assessment/<session_id>/status

# 5. Admin listing
curl http://localhost:8000/api/v1/admin/sessions
```

---

## 9. Running the checks

From the repo root:

```bash
./validate.sh
```

…runs pnpm install / Prisma generate / TypeScript build / lint / tests
plus the voice-engine ruff / mypy / pytest suite. Everything must pass
before landing a PR.

---

## 10. Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `prisma generate` complains about missing Postgres | `DATABASE_URL` not set | Export it in the shell before running. |
| Migration fails with `P1010: User postgres was denied access` | pgvector/pgvector Docker image permission issue — DB created with restricted owner | Use the manual setup (§3) or `setup-local.sh`; ensure the app database is created with `OWNER postgres`. |
| Migration fails at `CREATE EXTENSION vector` | Running against a vanilla `postgres:16` image | Use `pgvector/pgvector:pg16` (see §3). |
| `setup-local.sh` fails with `sed: command a expects` | macOS `sed -i` requires empty string argument for in-place edit | Already fixed in `setup-local.sh` (uses `sed -i ''`). Re-run the script. |
| `pip install -e ".[dev]"` fails with `ensurepip` error | Missing `python3.XX-venv` OS package | `sudo apt install python3.12-venv` (or the matching version). |
| Voice engine boots but returns `503` on `/health` | DB probe (`IPersistence.ping()`) failed | Check `DATABASE_URL` and that Postgres is up. |
| Voice engine boots but returns `503 Voice engine not ready` | `app.state.call_manager` is `None` — lifespan crashed | Check the `uvicorn` stderr for import / DB errors. |
| Candidate portal shows "Invalid form data" | API validation failed | Check the voice-engine logs; 422 errors come from Pydantic, 400 from domain validation. |
| No outbound call rings | Missing one of `DAILY_API_KEY` / `DEEPGRAM_API_KEY` / `ELEVENLABS_API_KEY` | Set the keys in `.env` and restart the voice engine. The admin dashboard will show `failureReason = "missing_provider_credentials"` until you do. |
| Call connects but the bot is silent | ElevenLabs rate limit / bad voice ID | Check voice-engine logs for 401/429 from ElevenLabs; override `ELEVENLABS_VOICE_ID` with a voice from your account's library. |
| Call connects, bot greets, but candidate reply isn't acknowledged | Deepgram returning no transcriptions or LLM timeout | Logs will show either `TranscriptionFrame: (empty)` (check your mic / line quality) or `LLM ack timed out after 10.0s`. The bot still says the goodbye + hangs up, so the call completes. |
| `docker compose up` fails to build `web` | Running from inside `apps/web` instead of repo root | `cd` to the repo root — the web Dockerfile needs the pnpm workspace. |

---

## 11. Deploying to production

See [`docs/guides/deployed-setup.md`](./deployed-setup.md) for the
Railway (Singapore) deployment walkthrough — Dockerfiles,
`railway.json`, `DAILY_GEO`, health checks, and the
`.github/workflows/deploy.yml` CI-gated deploy pipeline.

For the decision rationale on why Railway Singapore was chosen over
AWS Sydney, see
[ADR-006](../development/adr/ADR-006-deployment-platform.md).
