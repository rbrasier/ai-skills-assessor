#!/usr/bin/env bash
# Run an AI mock SFIA skills assessment interview.
#
# Usage:
#   ./scripts/mock-interview.sh
#
# You will be prompted for:
#   - Candidate role / context
#   - SFIA level (1–7)
#   - Honesty scale (1–10)
#
# Required environment variable:
#   ANTHROPIC_API_KEY

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VOICE_ENGINE_DIR="$SCRIPT_DIR/../apps/voice-engine"

if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
  echo "ERROR: ANTHROPIC_API_KEY is not set." >&2
  exit 1
fi

if [[ ! -d "$VOICE_ENGINE_DIR" ]]; then
  echo "ERROR: voice-engine directory not found at $VOICE_ENGINE_DIR" >&2
  exit 1
fi

cd "$VOICE_ENGINE_DIR"

# Activate virtual environment if present
if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
elif [[ -f "venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source venv/bin/activate
fi

exec python -m src.testing.cli "$@"
