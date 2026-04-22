#!/usr/bin/env bash
# docs/guides/setup-local.sh — One-shot local environment bootstrap
#
# Usage (from repo root):
#   bash docs/guides/setup-local.sh
#
# What it does:
#   1. Checks all prerequisites (Node, pnpm, Python, Docker)
#   2. Creates .env files from .env.example templates
#   3. Installs pnpm workspace dependencies
#   4. Creates the Python virtual environment and installs the voice engine
#   5. Starts (or creates) the pgvector Postgres container
#   6. Starts (or creates) the self-hosted LiveKit server container (see docs/guides/ensure-docker-livekit.sh)
#   7. Runs Prisma generate + migrate
#
# Manual steps that cannot be automated are printed at the end.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

# ── colours ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

ok()      { echo -e "${GREEN}✓${RESET} $*"; }
warn()    { echo -e "${YELLOW}⚠${RESET}  $*"; }
err()     { echo -e "${RED}✗${RESET} $*"; }
info()    { echo -e "${CYAN}→${RESET} $*"; }
section() { echo -e "\n${BOLD}── $* ──${RESET}"; }

MANUAL_STEPS=()
add_manual() { MANUAL_STEPS+=("$*"); }

version_gte() {
  # Returns 0 (true) if $1 >= $2 in semver order
  printf '%s\n%s\n' "$2" "$1" | sort -V -C
}

LOCAL_DB_URL="postgresql://postgres:postgres@localhost:5432/ai_skills_assessor"
CONTAINER_NAME="ai-skills-pg"

echo -e "\n${BOLD}AI Skills Assessor — Local Setup${RESET}"
echo "Working directory: $REPO_ROOT"

# ═══════════════════════════════════════════════════════════════════════════════
section "1/8  Prerequisites"
# ═══════════════════════════════════════════════════════════════════════════════

PREREQ_OK=true

# Node.js ≥ 20
if command -v node &>/dev/null; then
  NODE_VER=$(node --version | sed 's/v//')
  if version_gte "$NODE_VER" "20.0.0"; then
    ok "Node.js $NODE_VER"
  else
    err "Node.js $NODE_VER — need ≥20"
    add_manual "Upgrade Node.js to ≥20. Use nvm: nvm install 20 && nvm use 20"
    PREREQ_OK=false
  fi
else
  err "Node.js not found"
  add_manual "Install Node.js ≥20: https://nodejs.org or via nvm (https://github.com/nvm-sh/nvm)"
  PREREQ_OK=false
fi

# pnpm — install if missing, warn if old
if command -v pnpm &>/dev/null; then
  PNPM_VER=$(pnpm --version)
  if version_gte "$PNPM_VER" "10.0.0"; then
    ok "pnpm $PNPM_VER"
  else
    warn "pnpm $PNPM_VER — upgrading to latest..."
    npm install -g pnpm@latest 2>/dev/null || add_manual "Run: npm install -g pnpm@latest"
  fi
else
  info "pnpm not found — installing..."
  if npm install -g pnpm@latest 2>/dev/null; then
    ok "pnpm installed"
  else
    err "Could not install pnpm automatically"
    add_manual "Install pnpm: npm install -g pnpm@latest"
    PREREQ_OK=false
  fi
fi

# Python ≥ 3.11
PYTHON_BIN=""
for py in python3.13 python3.12 python3.11 python3 python; do
  if command -v "$py" &>/dev/null; then
    PY_VER=$("$py" --version 2>&1 | awk '{print $2}')
    if version_gte "$PY_VER" "3.11.0"; then
      PYTHON_BIN="$py"
      ok "Python $PY_VER ($py)"
      break
    fi
  fi
done
if [ -z "$PYTHON_BIN" ]; then
  err "Python ≥3.11 not found"
  add_manual "Install Python 3.11+: https://www.python.org/downloads/ or pyenv (https://github.com/pyenv/pyenv)"
  PREREQ_OK=false
fi

# Docker
DOCKER_OK=false
if command -v docker &>/dev/null; then
  DOCKER_VER=$(docker --version | awk '{print $3}' | tr -d ',')
  if docker info &>/dev/null 2>&1; then
    ok "Docker $DOCKER_VER (daemon running)"
    DOCKER_OK=true
  else
    warn "Docker $DOCKER_VER installed but daemon is not running"
    add_manual "Start Docker Desktop or the Docker daemon, then re-run this script"
  fi
else
  warn "Docker not found — Postgres must be provided externally on port 5432"
  add_manual "Install Docker: https://docs.docker.com/get-docker/  (needed for the Postgres container)"
fi

# curl (used for health probes at the end)
if command -v curl &>/dev/null; then
  ok "curl $(curl --version | head -1 | awk '{print $2}')"
else
  warn "curl not found — health-check probes will be skipped"
fi

if [ "$PREREQ_OK" = false ]; then
  echo
  err "Fix the prerequisites above, then re-run:  bash docs/guides/setup-local.sh"
  exit 1
fi

# ═══════════════════════════════════════════════════════════════════════════════
section "2/8  Environment files"
# ═══════════════════════════════════════════════════════════════════════════════

# apps/voice-engine/.env
if [ ! -f "apps/voice-engine/.env" ]; then
  cp apps/voice-engine/.env.example apps/voice-engine/.env
  # Patch the placeholder DATABASE_URL to the local default
  sed -i '' "s|DATABASE_URL=.*|DATABASE_URL=${LOCAL_DB_URL}|" apps/voice-engine/.env
  ok "Created apps/voice-engine/.env (patched DATABASE_URL)"
  add_manual "Open apps/voice-engine/.env and set DIALING_METHOD and the keys for that mode:
     DIALING_METHOD    — 'daily' (default, telephone) or 'browser' (self-hosted LiveKit)
     If daily:  DAILY_API_KEY, DAILY_DOMAIN  (daily.co → Developers)
     If browser: LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET  (your LiveKit server)
     DEEPGRAM_API_KEY  — deepgram.com  (required for the Pipecat pipeline in both modes)
     ELEVENLABS_API_KEY — elevenlabs.io  (required for the pipeline in both modes)
     ANTHROPIC_API_KEY — console.anthropic.com  (optional; bot falls back to hard-coded ack)
   Without STT/TTS keys the service boots, but trigger will fail with
   failureReason='missing_provider_credentials'."
else
  ok "apps/voice-engine/.env already exists"
  DM=$(grep -E '^DIALING_METHOD=' apps/voice-engine/.env 2>/dev/null | cut -d= -f2- | tr -d ' \r' || true)
  if [ -z "$DM" ] || [ "$DM" = "daily" ]; then
    for KEY in DAILY_API_KEY DEEPGRAM_API_KEY ELEVENLABS_API_KEY; do
      VAL=$(grep "^${KEY}=" apps/voice-engine/.env | cut -d= -f2-)
      [ -z "$VAL" ] && warn "  $KEY is blank in apps/voice-engine/.env (calls will fail in daily mode)"
    done
  else
    for KEY in LIVEKIT_URL LIVEKIT_API_KEY LIVEKIT_API_SECRET DEEPGRAM_API_KEY ELEVENLABS_API_KEY; do
      VAL=$(grep "^${KEY}=" apps/voice-engine/.env | cut -d= -f2-)
      [ -z "$VAL" ] && warn "  $KEY is blank in apps/voice-engine/.env (browser mode will fail)"
    done
  fi
fi

# apps/web/.env.local
if [ ! -f "apps/web/.env.local" ]; then
  cp apps/web/.env.example apps/web/.env.local
  ok "Created apps/web/.env.local"
else
  ok "apps/web/.env.local already exists"
fi

# packages/database/.env
if [ ! -f "packages/database/.env" ]; then
  if [ -f "packages/database/.env.example" ]; then
    cp packages/database/.env.example packages/database/.env
    sed -i '' "s|DATABASE_URL=.*|DATABASE_URL=\"${LOCAL_DB_URL}\"|" packages/database/.env
  else
    echo "DATABASE_URL=\"${LOCAL_DB_URL}\"" > packages/database/.env
  fi
  ok "Created packages/database/.env"
else
  ok "packages/database/.env already exists"
fi

# ═══════════════════════════════════════════════════════════════════════════════
section "3/8  Node.js dependencies (pnpm install)"
# ═══════════════════════════════════════════════════════════════════════════════

pnpm install --frozen-lockfile
ok "pnpm workspace installed"

# ═══════════════════════════════════════════════════════════════════════════════
section "4/8  Python virtual environment"
# ═══════════════════════════════════════════════════════════════════════════════

VENV_DIR="apps/voice-engine/.venv"

if [ ! -d "$VENV_DIR" ]; then
  info "Creating virtual environment at $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
  ok "Virtual environment created"
else
  ok "Virtual environment already exists at $VENV_DIR"
fi

PIP="$VENV_DIR/bin/pip"
PY_VENV="$VENV_DIR/bin/python"

# Detect whether Pipecat (voice extras) is already installed
if "$PY_VENV" -c "import pipecat" 2>/dev/null; then
  ok "Pipecat (voice extras) already installed"
else
  info "Installing voice engine with full voice extras [voice,dev] — this may take a few minutes..."
  if "$PIP" install -e "apps/voice-engine[voice,dev]" -q 2>&1; then
    ok "Voice engine installed (full voice extras — Pipecat, asyncpg, Deepgram, ElevenLabs)"
  else
    warn "Full [voice,dev] install failed — falling back to lean [dev] install (no call runtime)"
    "$PIP" install -e "apps/voice-engine[dev]" -q
    ok "Voice engine installed (lean — no Pipecat; intake and admin endpoints work)"
    add_manual "Install full voice extras when ready to test real calls:
     cd apps/voice-engine && .venv/bin/pip install -e '.[voice,dev]'"
  fi
fi

# ═══════════════════════════════════════════════════════════════════════════════
section "5/8  PostgreSQL (pgvector Postgres container)"
# ═══════════════════════════════════════════════════════════════════════════════

if [ "$DOCKER_OK" = false ]; then
  warn "Docker unavailable — skipping Postgres setup"
  add_manual "Start a PostgreSQL instance using image pgvector/pgvector:pg16 on port 5432:
     docker run --name ai-skills-pg \\
       -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres \\
       -e POSTGRES_DB=ai_skills_assessor \\
       -p 5432:5432 -d pgvector/pgvector:pg16"
else
  if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
      ok "Postgres container '$CONTAINER_NAME' is already running"
    else
      info "Starting existing Postgres container '$CONTAINER_NAME'..."
      docker start "$CONTAINER_NAME"
      ok "Postgres container started"
    fi
  else
    info "Creating Postgres container with pgvector (image: pgvector/pgvector:pg16)..."
    docker run --name "$CONTAINER_NAME" \
      -e POSTGRES_USER=postgres \
      -e POSTGRES_PASSWORD=postgres \
      -e POSTGRES_DB=postgres \
      -p 5432:5432 \
      -d pgvector/pgvector:pg16
    ok "Postgres container '$CONTAINER_NAME' created and started"

    # Create the application database as the superuser to avoid permission issues
    info "Creating application database..."
    for i in $(seq 1 10); do
      if docker exec "$CONTAINER_NAME" psql -U postgres -d postgres -c "CREATE DATABASE ai_skills_assessor OWNER postgres; GRANT ALL PRIVILEGES ON DATABASE ai_skills_assessor TO postgres;" 2>/dev/null; then
        ok "Application database created"
        break
      fi
      if [ "$i" -eq 10 ]; then
        err "Could not create database — check: docker logs $CONTAINER_NAME"
        exit 1
      fi
      sleep 1
    done
  fi

  info "Waiting for Postgres to be ready..."
  for i in $(seq 1 25); do
    if docker exec "$CONTAINER_NAME" pg_isready -U postgres -d ai_skills_assessor &>/dev/null 2>&1; then
      ok "Postgres is ready"
      break
    fi
    if [ "$i" -eq 25 ]; then
      err "Postgres did not become ready — check: docker logs $CONTAINER_NAME"
      exit 1
    fi
    sleep 1
  done
fi

# ═══════════════════════════════════════════════════════════════════════════════
section "6/8  LiveKit (self-hosted, Docker; browser mode / DIALING_METHOD=browser)"
# ═══════════════════════════════════════════════════════════════════════════════
# Same pattern as Postgres: image livekit/livekit-server --dev (devkey/secret);
#   see docs/guides/ensure-docker-livekit.sh. Skip with DOCKER_LIVEKIT_SKIP=1.

if [ "$DOCKER_OK" = false ]; then
  warn "Docker unavailable — skipping LiveKit server container"
  add_manual "Start LiveKit yourself or use LiveKit Cloud; set LIVEKIT_URL / API keys in apps/voice-engine/.env"
else
  # shellcheck source=/dev/null
  source "$REPO_ROOT/docs/guides/ensure-docker-livekit.sh"
  if ensure_docker_livekit; then
    if wait_for_livekit; then
      ok "LiveKit container '$LIVEKIT_CONTAINER_NAME' is up (WebSocket: ws://127.0.0.1:7880)"
    else
      warn "LiveKit container exists but :7880 did not become ready in time — check: docker logs $LIVEKIT_CONTAINER_NAME"
    fi
  else
    warn "Could not start LiveKit container — is port 7880 in use?"
  fi

  # If using browser mode but LIVEKIT_URL is still blank, add local --dev credentials (matches container).
  if [ -f "apps/voice-engine/.env" ]; then
    _dm_v=$(grep -E '^DIALING_METHOD=' apps/voice-engine/.env 2>/dev/null | head -1 | cut -d= -f2- | tr -d ' \r' || true)
    if [ "$_dm_v" = "browser" ] && ! grep -qE '^LIVEKIT_URL=.' apps/voice-engine/.env 2>/dev/null; then
      {
        echo ""
        echo "# Local Docker LiveKit (livekit-server --dev; see docs/guides/ensure-docker-livekit.sh)"
        echo "LIVEKIT_URL=ws://127.0.0.1:7880"
        echo "LIVEKIT_API_KEY=devkey"
        echo "LIVEKIT_API_SECRET=secret"
      } >> "apps/voice-engine/.env"
      ok "Appended local LiveKit dev credentials to apps/voice-engine/.env (browser mode)"
    fi
  fi
fi

# ═══════════════════════════════════════════════════════════════════════════════
section "7/8  Prisma generate + migrate"
# ═══════════════════════════════════════════════════════════════════════════════

export DATABASE_URL="$LOCAL_DB_URL"

info "Generating Prisma client..."
pnpm --filter @ai-skills-assessor/database run generate
ok "Prisma client generated"

info "Applying database migrations (3 phases)..."
pnpm --filter @ai-skills-assessor/database run migrate
ok "All migrations applied:
     v0_2_0_init_schema (Phase 1 — baseline tables)
     v0_3_0_phase_2_voice_engine (Phase 2 — candidates + sessions reshape)
     v0_4_0_phase_3_infrastructure (Phase 3 — pgvector + skill_embeddings + assessment_reports)"

# ═══════════════════════════════════════════════════════════════════════════════
section "8/8  Done"
# ═══════════════════════════════════════════════════════════════════════════════

echo
ok "Local environment is ready."
echo
echo -e "${BOLD}Start the stack (three terminals):${RESET}"
echo
echo "  Terminal 1 — Voice engine (FastAPI, hot reload)"
echo "  cd apps/voice-engine && .venv/bin/uvicorn src.main:app --reload --port 8000"
echo
echo "  Terminal 2 — Web app (Next.js)"
echo "  pnpm --filter @ai-skills-assessor/web run dev"
echo
echo -e "  ${BOLD}Or start both in the background with:${RESET}"
echo "  bash restart.sh"
echo
echo -e "  ${BOLD}Or run the full image-build stack (docker compose):${RESET}"
echo "  docker compose up --build"
echo
echo "  Health checks once running:"
echo "    curl http://localhost:8000/health   # voice engine + DB probe"
echo "    curl http://localhost:3000/api/health"
echo "  Web UI:"
echo "    http://localhost:3000          — candidate portal"
echo "    http://localhost:3000/dashboard — admin dashboard"
echo

# ── Print manual steps ──────────────────────────────────────────────────────
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
