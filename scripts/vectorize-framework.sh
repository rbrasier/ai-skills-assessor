#!/usr/bin/env bash
# vectorize-framework.sh — Generate or regenerate embeddings for a framework.
#
# Usage:
#   ./scripts/vectorize-framework.sh \
#     --framework-type sfia-9 \
#     --framework-version 9.0 \
#     [--embedder sentence-transformers|lsa] \
#     [--excel PATH_TO_XLSX] \
#     [--lsa-model PATH_TO_MODEL]
#
# Options:
#   --framework-type     Framework type identifier (default: sfia-9)
#   --framework-version  Framework version string (default: 9.0)
#   --embedder           'sentence-transformers' (default, requires internet once)
#                        or 'lsa' (fully offline, uses pre-fitted model)
#   --excel              Path to the source Excel file
#                        (default: docs/development/contracts/sfia-9.xlsx)
#   --lsa-model          Path to sfia_lsa_model.joblib (lsa embedder only)
#                        (default: apps/voice-engine/data/sfia_lsa_model.joblib)
#
# Environment variables:
#   DATABASE_URL   PostgreSQL connection string (required)
#
# The script re-embeds all skill levels in the database for the given framework.
# Levels whose content has not changed keep their existing embedding untouched
# (the database upsert preserves the embedding when content is unchanged).
# Levels whose content changed (or whose embedding is NULL) are re-embedded.
#
# This is safe to run repeatedly — it is fully idempotent.
#
# Example (offline LSA):
#   DATABASE_URL=postgres://user:pass@localhost/ai_skills \
#   ./scripts/vectorize-framework.sh --embedder lsa
#
# Example (neural, requires internet the first time):
#   DATABASE_URL=postgres://user:pass@localhost/ai_skills \
#   ./scripts/vectorize-framework.sh --embedder sentence-transformers

set -euo pipefail

# ── Defaults ────────────────────────────────────────────────────────────────
FRAMEWORK_TYPE="sfia-9"
FRAMEWORK_VERSION="9.0"
EMBEDDER="sentence-transformers"
EXCEL="docs/development/contracts/sfia-9.xlsx"
LSA_MODEL="apps/voice-engine/data/sfia_lsa_model.joblib"

# ── Parse arguments ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --framework-type)    FRAMEWORK_TYPE="$2";    shift 2 ;;
    --framework-version) FRAMEWORK_VERSION="$2"; shift 2 ;;
    --embedder)          EMBEDDER="$2";          shift 2 ;;
    --excel)             EXCEL="$2";             shift 2 ;;
    --lsa-model)         LSA_MODEL="$2";         shift 2 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

# ── Validate ─────────────────────────────────────────────────────────────────
if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "ERROR: DATABASE_URL environment variable is not set." >&2
  echo "  Export it before running this script:" >&2
  echo "    export DATABASE_URL=postgres://user:pass@host/dbname" >&2
  exit 1
fi

if [[ ! -f "$EXCEL" ]]; then
  echo "ERROR: Excel file not found: $EXCEL" >&2
  exit 1
fi

if [[ "$EMBEDDER" == "lsa" && ! -f "$LSA_MODEL" ]]; then
  echo "ERROR: LSA model not found: $LSA_MODEL" >&2
  echo "  Regenerate it with:" >&2
  echo "    python scripts/generate_sfia_embeddings_migration.py --embedder lsa" >&2
  exit 1
fi

# ── Locate the voice-engine package ──────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VOICE_ENGINE_DIR="$REPO_ROOT/apps/voice-engine"

if [[ ! -d "$VOICE_ENGINE_DIR" ]]; then
  echo "ERROR: voice-engine directory not found: $VOICE_ENGINE_DIR" >&2
  exit 1
fi

# ── Check Python ──────────────────────────────────────────────────────────────
PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" &>/dev/null; then
  echo "ERROR: Python 3 not found. Install Python 3.11+ and try again." >&2
  exit 1
fi

# ── Validate embedder choice ──────────────────────────────────────────────────
if [[ "$EMBEDDER" != "sentence-transformers" && "$EMBEDDER" != "lsa" ]]; then
  echo "ERROR: --embedder must be 'sentence-transformers' or 'lsa' (got: $EMBEDDER)" >&2
  exit 1
fi

# ── Run ingestion ─────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  Vectorize framework: $FRAMEWORK_TYPE v$FRAMEWORK_VERSION"
echo "  Embedder:  $EMBEDDER"
echo "  Excel:     $EXCEL"
echo "  Database:  ${DATABASE_URL%%@*}@***"
echo "═══════════════════════════════════════════════════════════"
echo ""

EXTRA_ARGS=()
if [[ "$EMBEDDER" == "lsa" ]]; then
  EXTRA_ARGS+=("--lsa-model-path" "$LSA_MODEL")
fi

cd "$VOICE_ENGINE_DIR"

"$PYTHON" -m src.scripts.ingest_sfia_skills \
  --excel "$REPO_ROOT/$EXCEL" \
  --framework-type "$FRAMEWORK_TYPE" \
  --framework-version "$FRAMEWORK_VERSION" \
  --database-url "$DATABASE_URL" \
  --embedder "$EMBEDDER" \
  "${EXTRA_ARGS[@]}"

echo ""
echo "Done. Check the Skills library page for updated sync status."
