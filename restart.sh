#!/usr/bin/env bash
# restart.sh — Stop all services and restart the AI Skills Assessor stack
#
# Usage (from repo root):
#   bash restart.sh           # native processes — uvicorn + pnpm dev (hot reload)
#   bash restart.sh --docker  # docker compose (exercises the full image-build path)
#
# Native mode writes logs to /tmp/ai-skills-logs/.
# Docker mode streams health status and exits; use `docker compose logs -f` for output.
#
# Run docs/guides/setup-local.sh first if this is a fresh clone.
#
# Voice engine reads apps/voice-engine/.env (see DIALING_METHOD=daily|browser).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

ok()   { echo -e "${GREEN}✓${RESET} $*"; }
warn() { echo -e "${YELLOW}⚠${RESET}  $*"; }
err()  { echo -e "${RED}✗${RESET} $*"; }
info() { echo -e "${CYAN}→${RESET} $*"; }

USE_DOCKER=false
for arg in "$@"; do [ "$arg" = "--docker" ] && USE_DOCKER=true; done

CONTAINER_NAME="ai-skills-pg"
LIVEKIT_CONTAINER_NAME="${LIVEKIT_CONTAINER_NAME:-ai-skills-livekit}"
LOCAL_DB_URL="postgresql://postgres:postgres@localhost:5432/ai_skills_assessor"
LOG_DIR="/tmp/ai-skills-logs"
mkdir -p "$LOG_DIR"

echo -e "\n${BOLD}AI Skills Assessor — Restart${RESET}"
[ "$USE_DOCKER" = true ] && echo "(docker compose mode)" || echo "(native process mode)"
echo

# ── helpers ────────────────────────────────────────────────────────────────────

kill_port() {
  local port=$1
  local pids=""
  if command -v lsof &>/dev/null; then
    pids=$(lsof -ti tcp:"$port" 2>/dev/null || true)
  elif command -v fuser &>/dev/null; then
    pids=$(fuser "${port}/tcp" 2>/dev/null | tr ' ' '\n' | grep -E '^[0-9]+$' || true)
  fi
  if [ -n "$pids" ]; then
    info "Clearing port $port (PIDs: $(echo "$pids" | tr '\n' ' '))"
    echo "$pids" | xargs kill -TERM 2>/dev/null || true
    sleep 1
    pids=$(lsof -ti tcp:"$port" 2>/dev/null || true)
    [ -n "$pids" ] && echo "$pids" | xargs kill -9 2>/dev/null || true
    ok "Port $port cleared"
  else
    ok "Port $port is free"
  fi
}

wait_http() {
  local url=$1 label=$2 retries=${3:-30}
  for i in $(seq 1 "$retries"); do
    if curl -sf "$url" &>/dev/null; then return 0; fi
    [ "$i" -eq "$retries" ] && return 1
    sleep 2
  done
}

ensure_postgres() {
  if ! command -v docker &>/dev/null || ! docker info &>/dev/null 2>&1; then
    warn "Docker unavailable — assuming Postgres is already running on :5432"
    return
  fi

  if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
      info "Starting existing Postgres container '$CONTAINER_NAME'..."
      docker start "$CONTAINER_NAME"
    fi
    ok "Postgres container '$CONTAINER_NAME' is running"
  else
    info "Creating Postgres container (pgvector/pgvector:pg16)..."
    docker run --name "$CONTAINER_NAME" \
      -e POSTGRES_USER=postgres \
      -e POSTGRES_PASSWORD=postgres \
      -e POSTGRES_DB=ai_skills_assessor \
      -p 5432:5432 \
      -d pgvector/pgvector:pg16
    ok "Postgres container created and started"
  fi

  info "Waiting for Postgres..."
  for i in $(seq 1 20); do
    if docker exec "$CONTAINER_NAME" pg_isready -U postgres -d ai_skills_assessor &>/dev/null 2>&1; then
      ok "Postgres ready"; return
    fi
    [ "$i" -eq 20 ] && { err "Postgres did not become ready — check: docker logs $CONTAINER_NAME"; exit 1; }
    sleep 1
  done
}

ensure_livekit() {
  if [ "${DOCKER_LIVEKIT_SKIP:-0}" = "1" ]; then
    return 0
  fi
  if [ ! -f "$REPO_ROOT/docs/guides/ensure-docker-livekit.sh" ]; then
    return 0
  fi
  # shellcheck source=/dev/null
  source "$REPO_ROOT/docs/guides/ensure-docker-livekit.sh"
  if ! ensure_docker_livekit; then
    warn "Could not start LiveKit container — check: docker logs $LIVEKIT_CONTAINER_NAME"
    return 0
  fi
  if ! wait_for_livekit; then
    warn "LiveKit :7880 not ready in time — check: docker logs $LIVEKIT_CONTAINER_NAME"
  else
    ok "LiveKit ready (WebSocket: ws://127.0.0.1:7880)"
  fi
}

# ═══════════════════════════════════════════════════════════════════════════════
# 1. Stop everything
# ═══════════════════════════════════════════════════════════════════════════════

info "Stopping existing services..."

# Stop docker compose stack if it is running
if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
  if docker compose ps -q 2>/dev/null | grep -q .; then
    info "Stopping docker compose stack..."
    docker compose down --remove-orphans 2>/dev/null || true
    ok "Docker compose stack stopped"
  fi
fi

# Kill any native processes holding the app ports
kill_port 8000   # voice engine
kill_port 3000   # web

# Kill previously backgrounded processes tracked by this script
for pidfile in "$LOG_DIR/voice-engine.pid" "$LOG_DIR/web.pid"; do
  if [ -f "$pidfile" ]; then
    pid=$(cat "$pidfile")
    kill -TERM "$pid" 2>/dev/null || true
    rm -f "$pidfile"
  fi
done

# ═══════════════════════════════════════════════════════════════════════════════
# 2a. Docker compose mode
# ═══════════════════════════════════════════════════════════════════════════════

if [ "$USE_DOCKER" = true ]; then
  info "Building and starting docker compose stack..."
  docker compose up --build -d

  info "Waiting for voice engine to be healthy..."
  if wait_http "http://localhost:8000/health" "voice engine" 40; then
    ok "Voice engine healthy: $(curl -s http://localhost:8000/health)"
  else
    err "Voice engine did not become healthy — check: docker compose logs voice-engine"
    exit 1
  fi

  info "Waiting for web app to be healthy..."
  if wait_http "http://localhost:3000/api/health" "web" 40; then
    ok "Web app healthy: $(curl -s http://localhost:3000/api/health)"
  else
    err "Web app did not become healthy — check: docker compose logs web"
    exit 1
  fi

  echo
  echo -e "${BOLD}Stack is running (docker compose):${RESET}"
  echo "  Voice engine:  http://localhost:8000"
  echo "  Web app:       http://localhost:3000"
  echo "  Admin dash:    http://localhost:3000/dashboard"
  echo
  echo "  Logs:          docker compose logs -f"
  echo "  Stop:          docker compose down"
  echo
  echo "  Note: run migrations from the host if schema has changed:"
  echo "    export DATABASE_URL=\"$LOCAL_DB_URL\""
  echo "    pnpm --filter @ai-skills-assessor/database run migrate"
  exit 0
fi

# ═══════════════════════════════════════════════════════════════════════════════
# 2b. Native process mode
# ═══════════════════════════════════════════════════════════════════════════════

# Postgres
ensure_postgres

# Self-hosted LiveKit (same as setup-local; docs/guides/ensure-docker-livekit.sh)
ensure_livekit

# Prisma migrate (apply any pending migrations; safe to run on every restart)
if [ -f "packages/database/prisma/schema.prisma" ]; then
  export DATABASE_URL="$LOCAL_DB_URL"
  info "Applying any pending migrations..."
  if pnpm --filter @ai-skills-assessor/database run migrate 2>/dev/null; then
    ok "Migrations up to date"
  else
    warn "Migration command failed — run 'bash docs/guides/setup-local.sh' if this is a fresh install"
  fi
fi

# Voice engine
VENV_UVICORN="$REPO_ROOT/apps/voice-engine/.venv/bin/uvicorn"
if [ ! -f "$VENV_UVICORN" ]; then
  err "Voice engine venv not found at apps/voice-engine/.venv"
  err "Run first:  bash docs/guides/setup-local.sh"
  exit 1
fi

VOICE_LOG="$LOG_DIR/voice-engine.log"
info "Starting voice engine (FastAPI + hot reload on :8000)..."
# cd into apps/voice-engine so pydantic-settings picks up .env and src.main resolves
# PYTHONUNBUFFERED=1 disables Python's block-buffering so logs appear immediately
nohup bash -c "cd '$REPO_ROOT/apps/voice-engine' && PYTHONUNBUFFERED=1 exec '$VENV_UVICORN' src.main:app --reload --port 8000" \
  > "$VOICE_LOG" 2>&1 &
VOICE_PID=$!
echo "$VOICE_PID" > "$LOG_DIR/voice-engine.pid"
ok "Voice engine started (PID $VOICE_PID)"

# Web app
WEB_LOG="$LOG_DIR/web.log"
info "Starting web app (Next.js on :3000)..."
nohup bash -c "cd '$REPO_ROOT' && exec pnpm --filter @ai-skills-assessor/web run dev" \
  > "$WEB_LOG" 2>&1 &
WEB_PID=$!
echo "$WEB_PID" > "$LOG_DIR/web.pid"
ok "Web app started (PID $WEB_PID)"

# Health checks
echo
info "Waiting for services to come up..."

if wait_http "http://localhost:8000/health" "voice engine" 35; then
  ok "Voice engine healthy: $(curl -s http://localhost:8000/health)"
else
  err "Voice engine did not start in time"
  err "  Check logs: tail -f $VOICE_LOG"
  exit 1
fi

if wait_http "http://localhost:3000/api/health" "web" 35; then
  ok "Web app healthy: $(curl -s http://localhost:3000/api/health)"
else
  err "Web app did not start in time"
  err "  Check logs: tail -f $WEB_LOG"
  exit 1
fi

echo
echo -e "${BOLD}Stack is running (native processes):${RESET}"
echo "  Voice engine:  http://localhost:8000"
echo "  Web app:       http://localhost:3000"
echo "  Admin dash:    http://localhost:3000/dashboard"
echo
echo -e "${BOLD}Streaming logs (press Ctrl+C to stop):${RESET}"
echo

# Colors for log prefixes
VOICE_COLOR='\033[0;36m'  # Cyan
WEB_COLOR='\033[0;35m'    # Magenta

# Tail logs with colored prefixes (filter status polls)
tail_with_prefix() {
  local logfile=$1 prefix=$2 color=$3
  tail -f "$logfile" 2>/dev/null | grep --line-buffered -v '/api.*assessment.*status' | while IFS= read -r line; do
    printf "${color}[%s]${RESET} %s\n" "$prefix" "$line"
  done &
}

# Start tail processes
tail_with_prefix "$VOICE_LOG" "voice" "$VOICE_COLOR"
tail_with_prefix "$WEB_LOG" "web" "$WEB_COLOR"

# Trap Ctrl+C to kill tail processes cleanly
trap 'kill $(jobs -p) 2>/dev/null; echo; info "Stopped"; exit 0' INT

# Wait for tail processes (will exit on Ctrl+C via trap)
wait
