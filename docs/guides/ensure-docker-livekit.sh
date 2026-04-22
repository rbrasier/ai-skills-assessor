#!/usr/bin/env bash
# Ensure the local LiveKit server Docker container (browser / DIALING_METHOD=browser).
# Same pattern as the Postgres container: start existing, or create and run.
#
# Default image: livekit/livekit-server; override with LIVEKIT_DOCKER_IMAGE.
# Dev mode (--dev) uses the well-known key pair: devkey / secret
#   (https://github.com/livekit/livekit#starting-livekit)
# Voice engine: LIVEKIT_URL=ws://127.0.0.1:7880, LIVEKIT_API_KEY=devkey,
#               LIVEKIT_API_SECRET=secret
#
# Usage: from repo root (or any cwd):
#   source docs/guides/ensure-docker-livekit.sh
#   ensure_docker_livekit
#
# Or:  bash docs/guides/ensure-docker-livekit.sh

LIVEKIT_CONTAINER_NAME="${LIVEKIT_CONTAINER_NAME:-ai-skills-livekit}"
# Pin for reproducible local dev; override to pull latest: LIVEKIT_DOCKER_TAG=latest
LIVEKIT_DOCKER_IMAGE="${LIVEKIT_DOCKER_IMAGE:-livekit/livekit-server}"

ensure_docker_livekit() {
  if [ "${DOCKER_LIVEKIT_SKIP:-0}" = "1" ]; then
    echo "  (DOCKER_LIVEKIT_SKIP=1 — not starting LiveKit container)" 2>/dev/null || true
    return 0
  fi
  if ! command -v docker &>/dev/null || ! docker info &>/dev/null 2>&1; then
    return 0
  fi

  if docker ps -a --format '{{.Names}}' 2>/dev/null | grep -q "^${LIVEKIT_CONTAINER_NAME}\$"; then
    if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^${LIVEKIT_CONTAINER_NAME}\$"; then
      docker start "$LIVEKIT_CONTAINER_NAME" || return 1
    fi
  else
    # --dev: built-in devkey/secret; HTTP health on 7880 (see LiveKit local docs).
    # UDP 50000-50050: typical local WebRTC; expand if your client cannot connect.
    docker run --name "$LIVEKIT_CONTAINER_NAME" \
      -p 7880:7880 \
      -p 7881:7881 \
      -p 50000-50050:50000-50050/udp \
      -d "$LIVEKIT_DOCKER_IMAGE" \
      --dev \
      --bind 0.0.0.0 || return 1
  fi
  return 0
}

# Wait until TCP 7880 accepts connections (avoids flaking voice engine startup).
wait_for_livekit() {
  local i
  for i in $(seq 1 30); do
    if command -v nc &>/dev/null; then
      if nc -z 127.0.0.1 7880 2>/dev/null; then
        return 0
      fi
    elif command -v timeout &>/dev/null; then
      if timeout 1 bash -c "echo >/dev/tcp/127.0.0.1/7880" 2>/dev/null; then
        return 0
      fi
    elif (echo >/dev/tcp/127.0.0.1/7880) 2>/dev/null; then
      return 0
    fi
    sleep 1
  done
  return 1
}

# Run as a tiny CLI (e.g. bash docs/guides/ensure-docker-livekit.sh)
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
  set -euo pipefail
  if ensure_docker_livekit; then
    if wait_for_livekit; then
      echo "ok: LiveKit container $LIVEKIT_CONTAINER_NAME (ws://127.0.0.1:7880)"
    else
      echo "warn: LiveKit container started but :7880 not yet accepting connections" >&2
      exit 1
    fi
  else
    exit 0
  fi
fi
