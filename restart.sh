#!/usr/bin/env bash
# restart.sh — Stop all services and restart the AI Skills Assessor stack
#
# Usage (from repo root):
#   bash restart.sh           # native processes — uvicorn + pnpm dev (hot reload)
#   bash restart.sh --docker  # docker compose (exercises the full image-build path)
#   bash restart.sh --debug   # native processes with DEBUG log level (verbose)
#
# Default log level is INFO — connections to external services and all bot
# dialog (TTS sent, STT received, LLM responses) are logged at this level.
# Use --debug for full Pipecat frame-level traces.
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
USE_DEBUG=false
for arg in "$@"; do
  [ "$arg" = "--docker" ] && USE_DOCKER=true
  [ "$arg" = "--debug" ] && USE_DEBUG=true
done

# Logging level for the voice engine (uvicorn + Python root logger)
LOG_LEVEL="info"
UVICORN_LOG_LEVEL="info"
if [ "$USE_DEBUG" = true ]; then
  LOG_LEVEL="debug"
  UVICORN_LOG_LEVEL="debug"
  warn "Debug mode enabled — verbose Pipecat frame traces will appear in voice-engine.log"
fi

CONTAINER_NAME="ai-skills-pg"
LIVEKIT_CONTAINER_NAME="${LIVEKIT_CONTAINER_NAME:-ai-skills-livekit}"
WHISPER_CONTAINER_NAME="${WHISPER_CONTAINER_NAME:-ai-skills-whisper}"
WHISPER_IMAGE_NAME="${WHISPER_IMAGE_NAME:-ghcr.io/collabora/whisperlive-cpu:latest}"
KOKORO_CONTAINER_NAME="${KOKORO_CONTAINER_NAME:-ai-skills-kokoro}"
LOCAL_DB_URL="postgresql://postgres:postgres@localhost:5432/ai_skills_assessor"
LOG_DIR="/tmp/ai-skills-logs"
mkdir -p "$LOG_DIR"

echo -e "\n${BOLD}AI Skills Assessor — Restart${RESET}"
[ "$USE_DOCKER" = true ] && echo "(docker compose mode)" || echo "(native process mode)"
echo

# ── helpers ────────────────────────────────────────────────────────────────────

# docker info can hang indefinitely if Docker Desktop is starting or unresponsive.
# This wrapper enforces a 5-second timeout using a portable background-kill approach.
docker_available() {
  command -v docker &>/dev/null || return 1
  # Check the socket before invoking docker.  On macOS, running any docker
  # command when Docker Desktop is stopped triggers its auto-start sequence
  # (30–90 s), even after the child process is killed.
  local sock="${DOCKER_HOST:-unix:///var/run/docker.sock}"
  sock="${sock#unix://}"
  [ -S "$sock" ] || return 1
  # Socket is present; confirm the daemon responds within 5 s
  docker info &>/dev/null 2>&1 &
  local dpid=$!
  ( sleep 5; kill "$dpid" 2>/dev/null ) &
  local killer=$!
  wait "$dpid" 2>/dev/null
  local status=$?
  kill "$killer" 2>/dev/null
  wait "$killer" 2>/dev/null
  return $status
}

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

# Read a single value from apps/voice-engine/.env (last match wins, strips quotes)
read_env_var() {
  local key=$1 envfile="$REPO_ROOT/apps/voice-engine/.env"
  [ -f "$envfile" ] || { echo ""; return; }
  grep -E "^${key}=" "$envfile" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '"' || echo ""
}

ensure_postgres() {
  if ! docker_available; then
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

ensure_whisper() {
  if [ "${DOCKER_WHISPER_SKIP:-0}" = "1" ]; then
    return 0
  fi
  local stt_provider
  stt_provider=$(read_env_var STT_PROVIDER)
  if [ "$stt_provider" != "whisper" ]; then
    return 0
  fi
  if ! docker_available; then
    warn "Docker unavailable — assuming WhisperLive is already running on :9090"
    return
  fi

  # Pull the pre-built WhisperLive CPU image if not already present locally.
  # This replaces the former custom docker build step (apps/whisper-stt/Dockerfile).
  if ! docker image inspect "$WHISPER_IMAGE_NAME" &>/dev/null 2>&1; then
    info "Pulling WhisperLive image '$WHISPER_IMAGE_NAME' (first run — downloads model layers, allow a few minutes)..."
    docker pull --platform linux/amd64 "$WHISPER_IMAGE_NAME"
    ok "WhisperLive image pulled"
  fi

  if docker ps -a --format '{{.Names}}' | grep -q "^${WHISPER_CONTAINER_NAME}$"; then
    if ! docker ps --format '{{.Names}}' | grep -q "^${WHISPER_CONTAINER_NAME}$"; then
      info "Starting existing WhisperLive container '$WHISPER_CONTAINER_NAME'..."
      docker start "$WHISPER_CONTAINER_NAME"
    fi
    info "WhisperLive container '$WHISPER_CONTAINER_NAME' is up — checking readiness..."
  else
    info "Creating WhisperLive container (port 9090)..."
    docker run --platform linux/amd64 --name "$WHISPER_CONTAINER_NAME" \
      -e OMP_NUM_THREADS="${OMP_NUM_THREADS:-4}" \
      --memory 4g \
      --restart on-failure:3 \
      -p 9090:9090 \
      -d "$WHISPER_IMAGE_NAME"
    info "WhisperLive container created — checking readiness..."
  fi

  # WhisperLive has no HTTP health endpoint; poll the WebSocket port via TCP.
  # The server accepts TCP connections once the model is loaded (~15–60 s on CPU).
  info "Waiting for WhisperLive to load (TCP :9090)..."
  local whisper_ready=false
  for i in $(seq 1 60); do
    if python3 -c "import socket; s=socket.socket(); s.settimeout(1); s.connect(('127.0.0.1', 9090)); s.close()" &>/dev/null 2>&1; then
      whisper_ready=true
      break
    fi
    printf "\r  → WhisperLive: waiting for port 9090 (attempt %d/60)..." "$i"
    sleep 2
  done
  echo  # newline after the progress line

  if [ "$whisper_ready" = true ]; then
    ok "WhisperLive ready (port 9090 accepting connections)"

    # Show recent container logs
    info "WhisperLive container initialization logs:"
    if docker logs "$WHISPER_CONTAINER_NAME" 2>/dev/null | tail -30; then
      :
    else
      warn "Could not retrieve logs from $WHISPER_CONTAINER_NAME"
    fi
  else
    warn "WhisperLive did not become ready in time"
    warn "  Container logs: docker logs $WHISPER_CONTAINER_NAME"
    warn "  Watch logs live: docker logs -f $WHISPER_CONTAINER_NAME"
  fi
}

ensure_localstt() {
  local stt_provider
  stt_provider=$(read_env_var STT_PROVIDER)
  if [ "$stt_provider" != "local" ]; then
    return 0
  fi

  local venv_pip="$REPO_ROOT/apps/voice-engine/.venv/bin/pip"
  if [ ! -f "$venv_pip" ]; then
    warn "Voice engine venv not found — skipping faster-whisper install check"
    return 0
  fi

  info "STT_PROVIDER=local — checking faster-whisper installation..."
  if "$venv_pip" show faster-whisper &>/dev/null 2>&1; then
    ok "faster-whisper already installed"
  else
    info "Installing faster-whisper into voice engine venv..."
    if "$venv_pip" install faster-whisper; then
      ok "faster-whisper installed"
    else
      err "faster-whisper install failed — check pip output above"
      err "  Manual install: cd apps/voice-engine && .venv/bin/pip install faster-whisper"
    fi
  fi
}

ensure_kokoro() {
  if [ "${DOCKER_KOKORO_SKIP:-0}" = "1" ]; then
    return 0
  fi
  local tts_provider
  tts_provider=$(read_env_var TTS_PROVIDER)
  if [ "$tts_provider" != "kokoro" ]; then
    return 0
  fi
  if ! docker_available; then
    warn "Docker unavailable — assuming Kokoro TTS is already running on :8880"
    return
  fi

  if docker ps -a --format '{{.Names}}' | grep -q "^${KOKORO_CONTAINER_NAME}$"; then
    if ! docker ps --format '{{.Names}}' | grep -q "^${KOKORO_CONTAINER_NAME}$"; then
      info "Starting existing Kokoro TTS container '$KOKORO_CONTAINER_NAME'..."
      docker start "$KOKORO_CONTAINER_NAME"
    fi
    ok "Kokoro TTS container '$KOKORO_CONTAINER_NAME' is running"
  else
    info "Creating Kokoro TTS container (ghcr.io/remsky/kokoro-fastapi-cpu:latest)..."
    docker run --name "$KOKORO_CONTAINER_NAME" \
      -e PORT=8880 \
      --memory 2g \
      -p 8880:8880 \
      -d ghcr.io/remsky/kokoro-fastapi-cpu:latest
    ok "Kokoro TTS container created and started"
  fi

  info "Waiting for Kokoro TTS (:8880)..."
  # generous retries — model loads on first boot (~20 s)
  if wait_http "http://localhost:8880/health" "kokoro-tts" 40; then
    ok "Kokoro TTS ready"
  else
    warn "Kokoro TTS did not become ready in time — check: docker logs $KOKORO_CONTAINER_NAME"
  fi
}

# ═══════════════════════════════════════════════════════════════════════════════
# 1. Stop everything
# ═══════════════════════════════════════════════════════════════════════════════

info "Stopping existing services..."

# Stop docker compose stack if it is running
if docker_available; then
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

# Self-hosted STT (only when STT_PROVIDER=whisper in apps/voice-engine/.env)
ensure_whisper

# Local STT (only when STT_PROVIDER=local — installs faster-whisper into venv)
ensure_localstt

# Self-hosted TTS (only when TTS_PROVIDER=kokoro in apps/voice-engine/.env)
ensure_kokoro

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
info "Starting voice engine (FastAPI + hot reload on :8000, log-level=$LOG_LEVEL)..."
# cd into apps/voice-engine so pydantic-settings picks up .env and src.main resolves
# PYTHONUNBUFFERED=1 disables Python's block-buffering so logs appear immediately
# LOG_LEVEL is read by main.py to configure the Python root logger
nohup bash -c "cd '$REPO_ROOT/apps/voice-engine' && PYTHONUNBUFFERED=1 LOG_LEVEL='$LOG_LEVEL' exec '$VENV_UVICORN' src.main:app --reload --port 8000 --log-level '$UVICORN_LOG_LEVEL'" \
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
