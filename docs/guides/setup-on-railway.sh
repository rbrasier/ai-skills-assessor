#!/usr/bin/env bash
# docs/guides/setup-on-railway.sh — Railway deployment setup for AI Skills Assessor
#
# Usage (from repo root):
#   bash docs/guides/setup-on-railway.sh
#
# Requires the Railway CLI. Install with:
#   npm install -g @railway/cli
#   # or
#   curl -fsSL https://railway.app/install.sh | sh
#
# What it automates:
#   1. Verifies Railway CLI is installed
#   2. Checks / initiates authentication
#   3. Links or creates the Railway project
#   4. Prompts for API keys and sets them on the voice-engine service
#   5. Sets the VOICE_ENGINE_URL on the web service
#   6. Runs Prisma migrations against the Railway database (optional)
#   7. Triggers a deploy of both services (optional)
#
# What requires the Railway dashboard (printed at the end):
#   - Creating the three services (postgres plugin + voice-engine + web)
#   - Setting root directories and Dockerfile paths per service
#   - Adding GitHub Actions secrets for the CI/CD pipeline
#   - Enabling PSTN dial-out on your Daily workspace (daily mode) or
#     provisioning a self-hosted LiveKit server (browser mode)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

ok()      { echo -e "${GREEN}✓${RESET} $*"; }
warn()    { echo -e "${YELLOW}⚠${RESET}  $*"; }
err()     { echo -e "${RED}✗${RESET} $*"; }
info()    { echo -e "${CYAN}→${RESET} $*"; }
section() { echo -e "\n${BOLD}── $* ──${RESET}"; }

MANUAL_STEPS=()
add_manual() { MANUAL_STEPS+=("$*"); }

echo -e "\n${BOLD}AI Skills Assessor — Railway Setup${RESET}"
echo "Working directory: $REPO_ROOT"

# ═══════════════════════════════════════════════════════════════════════════════
section "1/6  Railway CLI"
# ═══════════════════════════════════════════════════════════════════════════════

if ! command -v railway &>/dev/null; then
  err "Railway CLI not found"
  echo
  echo "Install it with one of:"
  echo "  npm install -g @railway/cli"
  echo "  curl -fsSL https://railway.app/install.sh | sh"
  echo
  exit 1
fi

RAILWAY_VER=$(railway --version 2>/dev/null | head -1 || echo "unknown")
ok "Railway CLI $RAILWAY_VER"

# ═══════════════════════════════════════════════════════════════════════════════
section "2/6  Authentication"
# ═══════════════════════════════════════════════════════════════════════════════

if railway whoami &>/dev/null 2>&1; then
  WHOAMI=$(railway whoami 2>/dev/null || echo "authenticated")
  ok "Logged in as: $WHOAMI"
else
  info "Not logged in — launching authentication..."
  railway login
fi

# ═══════════════════════════════════════════════════════════════════════════════
section "3/6  Project link"
# ═══════════════════════════════════════════════════════════════════════════════

if railway status &>/dev/null 2>&1; then
  ok "Project already linked"
  railway status 2>/dev/null || true
else
  echo
  warn "No Railway project is linked to this directory."
  echo
  echo "  A) Link to an existing project: railway link"
  echo "  B) Create a new project:        railway init"
  echo
  read -rp "Create a new project? [y/N] " choice
  if [[ "$choice" =~ ^[Yy]$ ]]; then
    railway init
  else
    railway link
  fi
fi

# ═══════════════════════════════════════════════════════════════════════════════
section "4/6  Services"
# ═══════════════════════════════════════════════════════════════════════════════

echo
info "Current Railway project services:"
railway status 2>/dev/null || true
echo

cat <<'INFO'
This project needs three Railway services. If not already created, add them
in the Railway dashboard (railway.app) → your project → New Service:

  Service 1 — postgres
    Type:           Plugin → Database → Postgres (pgvector)
    Note:           Choose the "pgvector" variant — the standard Postgres
                    plugin does not have the vector extension pre-installed.

  Service 2 — voice-engine
    Type:           GitHub repo (connect this repository)
    Root Directory: apps/voice-engine
    Builder:        Dockerfile  (railway.json in apps/voice-engine/ configures this)
    Start command:  uvicorn src.main:app --host 0.0.0.0 --port $PORT

  Service 3 — web
    Type:           GitHub repo (connect this repository)
    Root Directory: (leave blank — needs the full pnpm workspace in scope)
    Builder:        Dockerfile → apps/web/Dockerfile
    Start command:  node apps/web/server.js

INFO

add_manual "Create three services in the Railway dashboard if not already present:
    1. postgres      — Plugin → Database → Postgres (pgvector variant)
    2. voice-engine  — GitHub repo, Root Directory: apps/voice-engine, Dockerfile builder
    3. web           — GitHub repo, Root Directory: (blank), Dockerfile: apps/web/Dockerfile
    Reference: docs/guides/deployed-setup.md §1"

# ═══════════════════════════════════════════════════════════════════════════════
section "5/6  Environment variables"
# ═══════════════════════════════════════════════════════════════════════════════

echo
echo "Enter API keys for the voice-engine service."
echo "Press Enter to skip any key you don't have yet (set it later in the Railway dashboard)."
echo "Input is hidden for secrets."
echo

prompt_secret() {
  local KEY="$1" DESC="$2" DEFAULT="${3:-}"
  printf "  %-22s (%s)" "$KEY" "$DESC"
  [ -n "$DEFAULT" ] && printf " [%s]" "$DEFAULT"
  printf ": "
  local val
  read -rs val
  echo
  if [ -n "$val" ]; then echo "$val"
  elif [ -n "$DEFAULT" ]; then echo "$DEFAULT"
  else echo ""
  fi
}

DAILY_API_KEY=$(prompt_secret      "DAILY_API_KEY"       "daily.co → Developers")
DAILY_DOMAIN=$(prompt_secret       "DAILY_DOMAIN"        "e.g. yourteam.daily.co")
DEEPGRAM_API_KEY=$(prompt_secret   "DEEPGRAM_API_KEY"    "deepgram.com → Projects → API keys")
ELEVENLABS_API_KEY=$(prompt_secret "ELEVENLABS_API_KEY"  "elevenlabs.io → Profile → API Keys")
ANTHROPIC_API_KEY=$(prompt_secret  "ANTHROPIC_API_KEY"   "console.anthropic.com")
ANTHROPIC_MODEL=$(prompt_secret    "ANTHROPIC_MODEL"     "Claude model ID" "claude-3-5-haiku-latest")
ELEVENLABS_VOICE_ID=$(prompt_secret "ELEVENLABS_VOICE_ID" "ElevenLabs voice ID (Rachel default)" "21m00Tcm4TlvDq8ikWAM")

echo

set_var() {
  local SERVICE="$1" KEY="$2" VAL="$3"
  if [ -n "$VAL" ]; then
    if railway variables set "${KEY}=${VAL}" --service "$SERVICE" 2>/dev/null; then
      ok "  $KEY → $SERVICE"
    else
      warn "  Could not set $KEY on $SERVICE — set it manually in the Railway dashboard"
      add_manual "Set $KEY on the $SERVICE service in Railway dashboard → Variables"
    fi
  else
    warn "  $KEY skipped (empty) — set it in Railway dashboard → $SERVICE → Variables"
    add_manual "Set $KEY on the voice-engine service in Railway dashboard → Variables"
  fi
}

info "Setting fixed defaults on voice-engine..."
railway variables set \
  "DIALING_METHOD=daily" \
  "DAILY_GEO=ap-southeast-1" \
  "DAILY_CALLER_ID=" \
  "DEEPGRAM_MODEL=nova-2-phonecall" \
  "BOT_NAME=Noa" \
  "BOT_ORG_NAME=Resonant" \
  "LOG_LEVEL=INFO" \
  "USE_IN_MEMORY_ADAPTERS=0" \
  --service voice-engine 2>/dev/null \
  && ok "Fixed defaults set on voice-engine" \
  || warn "Could not set fixed defaults — set them manually in the Railway dashboard"

info "Setting API keys on voice-engine..."
set_var voice-engine DAILY_API_KEY      "$DAILY_API_KEY"
set_var voice-engine DAILY_DOMAIN       "$DAILY_DOMAIN"
set_var voice-engine DEEPGRAM_API_KEY   "$DEEPGRAM_API_KEY"
set_var voice-engine ELEVENLABS_API_KEY "$ELEVENLABS_API_KEY"
set_var voice-engine ANTHROPIC_API_KEY  "$ANTHROPIC_API_KEY"
set_var voice-engine ANTHROPIC_MODEL    "$ANTHROPIC_MODEL"
set_var voice-engine ELEVENLABS_VOICE_ID "$ELEVENLABS_VOICE_ID"

info "Setting DATABASE_URL on voice-engine (Railway variable reference to postgres service)..."
# Single-quoted so bash does not expand ${{...}}
if railway variables set 'DATABASE_URL=${{postgres.DATABASE_URL}}' --service voice-engine 2>/dev/null; then
  ok "  DATABASE_URL → voice-engine (references postgres service)"
else
  warn "  Could not set DATABASE_URL via CLI"
  add_manual "In Railway dashboard → voice-engine → Variables, add:
     KEY:   DATABASE_URL
     VALUE: \${{postgres.DATABASE_URL}}
     (This is a Railway variable reference — Railway resolves it at runtime)"
fi

info "Setting VOICE_ENGINE_URL on web service..."
if railway variables set \
  "VOICE_ENGINE_URL=http://voice-engine.railway.internal:8000" \
  --service web 2>/dev/null; then
  ok "  VOICE_ENGINE_URL → web (private Railway network)"
else
  warn "  Could not set VOICE_ENGINE_URL on web"
  add_manual "In Railway dashboard → web → Variables, add:
     VOICE_ENGINE_URL=http://voice-engine.railway.internal:8000"
fi

# ═══════════════════════════════════════════════════════════════════════════════
section "6/6  Database migrations + deploy"
# ═══════════════════════════════════════════════════════════════════════════════

echo
echo "Prisma migrations need to run once against the Railway database."
echo "The recommended approach runs them locally with the Railway DATABASE_URL injected:"
echo
echo "  railway run --service voice-engine -- pnpm --filter @ai-skills-assessor/database run migrate"
echo
echo "This uses 'railway run' to inject env vars from the voice-engine service"
echo "into your local shell, then runs pnpm locally against the Railway database."
echo
echo "Alternatively, get the URL from the Railway dashboard → postgres → Variables"
echo "and export it manually:"
echo "  export DATABASE_URL=<railway-postgres-url>?sslmode=require"
echo "  pnpm --filter @ai-skills-assessor/database run generate"
echo "  pnpm --filter @ai-skills-assessor/database run migrate"
echo

read -rp "Run migrations now via 'railway run'? [y/N] " run_migrate
if [[ "$run_migrate" =~ ^[Yy]$ ]]; then
  info "Running Prisma generate..."
  pnpm --filter @ai-skills-assessor/database run generate
  info "Running Prisma migrate against Railway database..."
  railway run --service voice-engine -- pnpm --filter @ai-skills-assessor/database run migrate \
    && ok "Migrations applied" \
    || { warn "Migration failed — check that the postgres service is provisioned and DATABASE_URL is set"; \
         add_manual "Run migrations manually:
     railway run --service voice-engine -- pnpm --filter @ai-skills-assessor/database run migrate"; }
fi

echo
read -rp "Deploy voice-engine and web services now? [y/N] " do_deploy
if [[ "$do_deploy" =~ ^[Yy]$ ]]; then
  info "Deploying voice-engine..."
  railway up --service voice-engine \
    && ok "voice-engine deployed" \
    || warn "Deploy failed — check: railway logs --service voice-engine"

  info "Deploying web..."
  railway up --service web \
    && ok "web deployed" \
    || warn "Deploy failed — check: railway logs --service web"
fi

# ── Additional manual steps ──────────────────────────────────────────────────

add_manual "Verify pgvector is available on the Railway Postgres instance:
     railway connect postgres
     -- then inside psql:
     CREATE EXTENSION IF NOT EXISTS vector;
     -- If this fails, re-provision using the Railway 'Postgres (pgvector)' template"

add_manual "Set DIALING_METHOD in Railway → voice-engine → Variables:
     • daily (default) — telephone via Daily. Enable PSTN dial-out on your Daily
       workspace (daily.co support) and set DAILY_API_KEY / DAILY_DOMAIN.
     • browser — self-hosted LiveKit. Set LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET
       (and optionally LIVEKIT_MEET_URL). Omit or blank Daily keys when not used."

add_manual "If using Daily (DIALING_METHOD=daily), enable PSTN dial-out on your Daily workspace (required for outbound phone calls):
     Log in to daily.co → contact Daily support → request PSTN dial-out for your workspace.
     Set DAILY_DOMAIN in Railway dashboard → voice-engine → Variables."

add_manual "Add GitHub Actions secrets so the CI/CD deploy pipeline works
     (repo → Settings → Secrets and variables → Actions → New repository secret):
       RAILWAY_TOKEN             — project-scoped token: railway tokens create
       RAILWAY_ENVIRONMENT       — environment name, e.g. production
       RAILWAY_VOICE_ENGINE_ID   — Service ID: Railway dashboard → voice-engine → Settings
       RAILWAY_WEB_ID            — Service ID: Railway dashboard → web → Settings

     Add this as a repository variable (not a secret):
       SMOKE_TEST_URL  — public URL of the voice-engine service (enables the smoke-test job)
                         e.g. https://voice-engine-abc.up.railway.app"

add_manual "Set up the Railway deploy hook on voice-engine so migrations run on every deploy:
     Railway dashboard → voice-engine → Settings → Deploy → Deploy Command:
       pnpm --filter @ai-skills-assessor/database run migrate
     (This ensures migrations are applied before the new image starts)"

# ── Print manual steps ─────────────────────────────────────────────────────────

if [ ${#MANUAL_STEPS[@]} -gt 0 ]; then
  echo
  echo -e "${YELLOW}${BOLD}╔═══════════════════════════════════════════════════╗${RESET}"
  echo -e "${YELLOW}${BOLD}║  MANUAL STEPS REQUIRED                            ║${RESET}"
  echo -e "${YELLOW}${BOLD}╚═══════════════════════════════════════════════════╝${RESET}"
  i=1
  for step in "${MANUAL_STEPS[@]}"; do
    echo -e "\n${YELLOW}[$i]${RESET} $step"
    ((i++))
  done
  echo
fi

echo -e "${BOLD}Reference docs:${RESET}"
echo "  docs/guides/deployed-setup.md  — full Railway walkthrough"
echo "  docs/development/adr/ADR-006-deployment-platform.md  — Railway vs AWS trade-offs"
echo
