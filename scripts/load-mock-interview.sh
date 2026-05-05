#!/usr/bin/env bash
# Reload a mock-interview JSON export into Postgres so it appears in the admin dashboard.
#
# Usage:
#   ./scripts/load-mock-interview.sh
#
# Lists JSON files in scripts/mock-results/, prompts for a selection, then runs
# the voice-engine loader module.
#
# Requires: DATABASE_URL (and same venv setup as mock-interview.sh)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="$SCRIPT_DIR/mock-results"
VOICE_ENGINE_DIR="$SCRIPT_DIR/../apps/voice-engine"

if [[ ! -d "$VOICE_ENGINE_DIR" ]]; then
  echo "ERROR: voice-engine directory not found at $VOICE_ENGINE_DIR" >&2
  exit 1
fi

mkdir -p "$RESULTS_DIR"
FILES=()
while IFS= read -r line; do FILES+=("$line"); done < <(find "$RESULTS_DIR" -maxdepth 1 -name 'mock-interview-*.json' -type f | sort)

if [[ ${#FILES[@]} -eq 0 ]]; then
  echo "No mock-interview-*.json files in $RESULTS_DIR" >&2
  echo "Run ./scripts/mock-interview.sh first to generate one." >&2
  exit 1
fi

echo "Select a file to load:"
i=1
for f in "${FILES[@]}"; do
  echo "  $i) $(basename "$f")"
  ((i++)) || true
done
read -r -p "Enter number (1-${#FILES[@]}): " choice
if ! [[ "$choice" =~ ^[0-9]+$ ]] || (( choice < 1 || choice > ${#FILES[@]} )); then
  echo "Invalid selection." >&2
  exit 1
fi

SELECTED="${FILES[$((choice - 1))]}"

cd "$VOICE_ENGINE_DIR"

if [[ -f ".env" ]]; then
  # shellcheck disable=SC1091
  set -a; source .env; set +a
fi

if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
elif [[ -f "venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source venv/bin/activate
fi

exec python -m src.testing.load_mock_interview "$SELECTED"
