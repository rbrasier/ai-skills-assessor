#!/usr/bin/env bash
# Run an AI mock SFIA skills assessment interview.
#
# Usage:
#   ./scripts/mock-interview.sh --role "Senior Software Engineer" --sfia-level 5
#   ./scripts/mock-interview.sh --role "Junior dev" --sfia-level 2 --honesty 2 --model claude-haiku-4-5-20251001
#
# Required environment variable:
#   ANTHROPIC_API_KEY
#
# All other arguments are passed through to src.testing.cli.

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
