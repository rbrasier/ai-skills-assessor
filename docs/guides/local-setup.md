# Local Setup Guide — Phase 2 (v0.3.0)

This guide gets the AI Skills Assessor running end-to-end on a laptop:
candidate intake form → Python voice engine → Postgres. Phase 2 ships
candidate self-service call triggering; the Pipecat pipeline (STT /
TTS / LLM) is deferred to Phase 3, so calls won't actually audio-chat
yet — but the full state machine is wired up.

---

## 1. Prerequisites

| Tool         | Version    | Notes                                            |
|--------------|------------|--------------------------------------------------|
| Node.js      | ≥ 20.x     | `.nvmrc` pins `20`.                              |
| pnpm         | ≥ 10.x     | `packageManager` pins `pnpm@10.33.0`.            |
| Python       | 3.11+      | Voice engine targets 3.11 but runs on 3.12.      |
| Docker       | any        | Easiest way to run Postgres locally.             |
| `make` / bash| —          | Some helper scripts are POSIX shell.             |

A Daily API key is **optional** for Phase 2. Without it, the voice
engine will fall back to the `InMemoryPersistence` + still accept
trigger requests, but Daily room creation will fail. Sign up at
[daily.co](https://www.daily.co) when you need the real adapter.

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

## 3. Database (Postgres)

The quickest path is Docker:

```bash
docker run --name ai-skills-pg \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=ai_skills_assessor \
  -p 5432:5432 -d postgres:16
```

Then from the repo root:

```bash
export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/ai_skills_assessor"

pnpm --filter @ai-skills-assessor/database run generate   # prisma client
pnpm --filter @ai-skills-assessor/database run migrate    # prisma migrate deploy
```

This runs `v0_2_0_init_schema` (Phase 1) followed by
`v0_3_0_phase_2_voice_engine` (this phase). The second migration
drops and re-creates `candidates` / `assessment_sessions` — safe on a
dev box with no data.

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
DAILY_API_KEY=               # optional — omit to skip real Daily rooms
DAILY_DOMAIN=                # e.g. "your-team.daily.co"
LOG_LEVEL=INFO

# Set to "1" to bypass Postgres and use InMemoryPersistence instead —
# useful if you want to kick the tyres without running migrations.
USE_IN_MEMORY_ADAPTERS=0
```

And `apps/web/.env.local`:

```bash
VOICE_ENGINE_URL=http://localhost:8000
```

---

## 5. Run the stack

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

## 6. Smoke test

```bash
# 1. Health
curl http://localhost:8000/health
# {"status":"ok"}

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

## 7. Running the checks

From the repo root:

```bash
./validate.sh
```

…runs pnpm install / Prisma generate / TypeScript build / lint / tests
plus the voice-engine ruff / mypy / pytest suite. Everything must pass
before landing a PR.

---

## 8. Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `prisma generate` complains about missing Postgres | `DATABASE_URL` not set | Export it in the shell before running. |
| `pip install -e ".[dev]"` fails with `ensurepip` error | Missing `python3.XX-venv` OS package | `sudo apt install python3.12-venv` (or the matching version). |
| Voice engine boots but returns `503 Voice engine not ready` | `app.state.call_manager` is `None` — lifespan crashed | Check the `uvicorn` stderr for import / DB errors. |
| Candidate portal shows "Invalid form data" | API validation failed | Check the voice-engine logs; 422 errors come from Pydantic, 400 from domain validation. |
| No outbound call rings | Expected in Phase 2 | Pipecat pipeline lands in Phase 3; the stub only creates a Daily room. |

---

## 9. Deploying to production

See [`docs/guides/deployed-setup.md`](./deployed-setup.md) for the
Railway deployment walkthrough (Singapore region, `DAILY_GEO=ap-southeast-1`).

For the decision rationale on why Railway Singapore was chosen over AWS
Sydney, see [ADR-006](../development/adr/ADR-006-deployment-platform.md).
