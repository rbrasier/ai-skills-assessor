#!/bin/bash

# AI Skills Assessor — Validation Script
#
# Validates that all checks pass and architectural rules are enforced across
# both the TypeScript monorepo (apps/web, packages/*) and the Python voice
# engine (apps/voice-engine).
#
# ADR coverage:
#   ADR-001 — Hexagonal Architecture (Ports & Adapters)
#   ADR-002 — Monorepo Structure with pnpm Workspaces + Turborepo
#   ADR-004 — Voice Engine Technology (Pipecat, Daily, FastAPI)
#   ADR-005 — RAG & Vector Store Strategy (pgvector, framework_type metadata)
#
# This script is safe to run repeatedly. Heavy operations (pnpm install,
# prisma generate, pip install) short-circuit when nothing has changed.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

PASS_COUNT=0
FAIL_COUNT=0

# Flags
#   --smoke     hit a live SMOKE_TEST_URL (requires SMOKE_TEST_URL env var)
#   --extended  include mypy typecheck (Check 9b); pipecat's type stubs evolve
#               frequently so mypy is not gated in the standard run
RUN_SMOKE=0
RUN_EXTENDED=0
for _arg in "$@"; do
  [[ "$_arg" == "--smoke" ]]    && RUN_SMOKE=1
  [[ "$_arg" == "--extended" ]] && RUN_EXTENDED=1
done

TOTAL_CHECKS=13   # 10 original + 3 provider-swap checks (v0.5.0)
[[ $RUN_EXTENDED -eq 1 ]] && TOTAL_CHECKS=14   # +1 for mypy typecheck (Check 9b)

# Helper functions
pass() {
  echo -e "${GREEN}✓ $1${NC}"
  ((PASS_COUNT++))
}

fail() {
  echo -e "${RED}✗ $1${NC}"
  ((FAIL_COUNT++))
}

warn() {
  echo -e "${YELLOW}! $1${NC}"
}

print_header() {
  echo ""
  echo "=========================================="
  echo "$1"
  echo "=========================================="
}

# Resolve the voice-engine Python interpreter. Prefer the local venv at
# apps/voice-engine/.venv/bin/python (created by `python3 -m venv .venv`
# inside that package) so we don't pollute the system interpreter. Fall back
# to whatever `python3` is on PATH.
VOICE_ENGINE_DIR="apps/voice-engine"
VENV_PY="$SCRIPT_DIR/$VOICE_ENGINE_DIR/.venv/bin/python"
if [ -x "$VENV_PY" ]; then
  PY="$VENV_PY"
else
  PY="$(command -v python3 || true)"
fi

# ──────────────────────────────────────────────────────────────
# Check 1: pnpm install
# ──────────────────────────────────────────────────────────────
print_header "Check 1 / ${TOTAL_CHECKS}: pnpm install"
if pnpm install > /dev/null 2>&1; then
  pass "pnpm install"
else
  fail "pnpm install"
  pnpm install 2>&1 | tail -20
fi

# ──────────────────────────────────────────────────────────────
# Check 2: prisma generate — must run before any TS build/typecheck that
# depends on @ai-skills-assessor/database (the generated client lives at
# packages/database/src/generated/client and is referenced by src/index.ts).
# ──────────────────────────────────────────────────────────────
print_header "Check 2 / ${TOTAL_CHECKS}: Prisma client generation"
if pnpm --filter @ai-skills-assessor/database run generate > /dev/null 2>&1; then
  pass "prisma generate (packages/database)"
else
  fail "prisma generate"
  pnpm --filter @ai-skills-assessor/database run generate 2>&1 | tail -20
fi

# ──────────────────────────────────────────────────────────────
# Check 3: pnpm build — no TypeScript errors across the workspace.
# Turbo may exit 0 but still print TS errors — guard against both.
# ──────────────────────────────────────────────────────────────
print_header "Check 3 / ${TOTAL_CHECKS}: TypeScript build (turbo build)"
# NODE_TLS_REJECT_UNAUTHORIZED=0 is required in this environment because
# next/font/google fetches font manifests at build time and the network uses
# a self-signed certificate. This flag is scoped to this one subprocess only.
BUILD_OUTPUT=$(NODE_TLS_REJECT_UNAUTHORIZED=0 pnpm build 2>&1)
BUILD_EXIT=$?
if [ $BUILD_EXIT -eq 0 ] && ! echo "$BUILD_OUTPUT" | grep -qE "error TS[0-9]+|Build failed"; then
  pass "pnpm build (0 TS errors)"
else
  fail "pnpm build"
  echo "$BUILD_OUTPUT" | grep -E "error TS[0-9]+|Build failed|\.tsx?:[0-9]+" | tail -20
fi

# ──────────────────────────────────────────────────────────────
# Check 4: pnpm lint — ESLint across all TS packages, plus next lint.
# ──────────────────────────────────────────────────────────────
print_header "Check 4 / ${TOTAL_CHECKS}: TypeScript lint (turbo lint)"
if pnpm lint > /dev/null 2>&1; then
  pass "pnpm lint (0 violations)"
else
  fail "pnpm lint"
  pnpm lint 2>&1 | tail -20
fi

# ──────────────────────────────────────────────────────────────
# Check 5: pnpm test — TypeScript test suites (placeholder in Phase 1).
# ──────────────────────────────────────────────────────────────
print_header "Check 5 / ${TOTAL_CHECKS}: TypeScript tests (turbo test)"
TEST_OUTPUT=$(pnpm test 2>&1)
if [ $? -eq 0 ]; then
  pass "pnpm test"
else
  fail "pnpm test"
  echo "$TEST_OUTPUT" | tail -20
fi

# ──────────────────────────────────────────────────────────────
# Check 6: ADR-001 — Voice-engine hexagonal isolation (grep belt-and-suspenders).
#
# `apps/voice-engine/src/domain/` is the pure domain layer: models, ports,
# and orchestration services. It must not import from:
#   - src.adapters         (concrete infrastructure)
#   - src.api / src.flows  (delivery + Pipecat-specific glue)
#   - fastapi              (HTTP framework — adapter-side)
#   - pipecat / pipecat_ai (voice framework — adapter-side)
#   - daily / daily_python (telephony — adapter-side)
#   - asyncpg / psycopg / sqlalchemy / pgvector (DB drivers — adapter-side)
#   - anthropic / openai   (LLM SDKs — adapter-side)
#   - prisma               (Node-side, never imported from Python)
# ──────────────────────────────────────────────────────────────
print_header "Check 6 / ${TOTAL_CHECKS}: ADR-001 — voice-engine domain isolation"
DOMAIN_DIR="$VOICE_ENGINE_DIR/src/domain"
if [ -d "$DOMAIN_DIR" ]; then
  DOMAIN_LEAKS=$(grep -rEn \
    --include="*.py" \
    "^[[:space:]]*(from|import)[[:space:]]+(src\.adapters|src\.api|src\.flows|fastapi|pipecat|pipecat_ai|daily|daily_python|asyncpg|psycopg|sqlalchemy|pgvector|anthropic|openai|prisma)([[:space:]]|\.|$)" \
    "$DOMAIN_DIR" 2>/dev/null | grep -v "/__pycache__/" || true)

  if [ -z "$DOMAIN_LEAKS" ]; then
    pass "ADR-001: apps/voice-engine/src/domain has no adapter or framework imports"
  else
    fail "ADR-001: Illegal imports found in apps/voice-engine/src/domain"
    echo "$DOMAIN_LEAKS"
  fi
else
  fail "ADR-001: $DOMAIN_DIR not found"
fi

# ──────────────────────────────────────────────────────────────
# Check 7: ADR-001 / ADR-004 / ADR-005 — Required ports and adapters exist.
# These files are structural anchors for the hexagonal architecture; if they
# disappear, the architecture is broken regardless of what compiles.
# ──────────────────────────────────────────────────────────────
print_header "Check 7 / ${TOTAL_CHECKS}: ADR-001/004/005 — Required ports and adapters present"
MISSING_FILES=()

REQUIRED_PORTS=(
  "$VOICE_ENGINE_DIR/src/domain/ports/assessment_trigger.py"
  "$VOICE_ENGINE_DIR/src/domain/ports/voice_transport.py"
  "$VOICE_ENGINE_DIR/src/domain/ports/persistence.py"
  "$VOICE_ENGINE_DIR/src/domain/ports/knowledge_base.py"
  "$VOICE_ENGINE_DIR/src/domain/ports/llm_provider.py"
)

REQUIRED_ADAPTERS=(
  "$VOICE_ENGINE_DIR/src/adapters/daily_transport.py"
  "$VOICE_ENGINE_DIR/src/adapters/livekit_transport.py"
  "$VOICE_ENGINE_DIR/src/adapters/postgres_persistence.py"
  "$VOICE_ENGINE_DIR/src/adapters/pgvector_knowledge_base.py"
  "$VOICE_ENGINE_DIR/src/adapters/anthropic_llm_provider.py"
)

REQUIRED_SCHEMA=(
  "packages/database/prisma/schema.prisma"
)

for f in "${REQUIRED_PORTS[@]}" "${REQUIRED_ADAPTERS[@]}" "${REQUIRED_SCHEMA[@]}"; do
  [ ! -f "$f" ] && MISSING_FILES+=("$f")
done

if [ ${#MISSING_FILES[@]} -eq 0 ]; then
  TOTAL_FILES=$(( ${#REQUIRED_PORTS[@]} + ${#REQUIRED_ADAPTERS[@]} + ${#REQUIRED_SCHEMA[@]} ))
  pass "ADR-001/004/005: All $TOTAL_FILES required ports / adapters / schema files present"
else
  fail "ADR-001/004/005: Missing required files:"
  for f in "${MISSING_FILES[@]}"; do
    echo "  - $f"
  done
fi

# ──────────────────────────────────────────────────────────────
# Check 8: ADR-002 — Every Prisma model declares an explicit @@map table
# name. We map to snake_case so table groupings are obvious in the database
# (e.g. assessment_sessions, candidates) and so future renames don't silently
# break SQL written by hand.
# ──────────────────────────────────────────────────────────────
print_header "Check 8 / ${TOTAL_CHECKS}: ADR-002 — Prisma models all have @@map"
SCHEMA_FILE="packages/database/prisma/schema.prisma"
MODELS_WITHOUT_MAP=()

if [ -f "$SCHEMA_FILE" ]; then
  while IFS= read -r model_name; do
    if ! awk "/^model ${model_name} \{/,/^\}/" "$SCHEMA_FILE" | grep -q "@@map"; then
      MODELS_WITHOUT_MAP+=("$model_name")
    fi
  done < <(grep "^model " "$SCHEMA_FILE" | awk '{print $2}')

  if [ ${#MODELS_WITHOUT_MAP[@]} -eq 0 ]; then
    MODEL_COUNT=$(grep -c "^model " "$SCHEMA_FILE")
    pass "ADR-002: All $MODEL_COUNT Prisma models have @@map directives"
  else
    fail "ADR-002: Models missing @@map (table name) directives:"
    for m in "${MODELS_WITHOUT_MAP[@]}"; do
      echo "  - $m"
    done
  fi
else
  fail "ADR-002: schema.prisma not found at $SCHEMA_FILE"
fi

# ──────────────────────────────────────────────────────────────
# Check 9: ADR-004 — Python lint (ruff).
#
# Requires the voice-engine venv with the [dev] extras installed:
#   cd apps/voice-engine && python3 -m venv .venv \
#     && .venv/bin/pip install -e ".[dev]"
# ──────────────────────────────────────────────────────────────
print_header "Check 9 / ${TOTAL_CHECKS}: ADR-004 — Python lint (ruff)"

if [ -z "$PY" ]; then
  fail "Python interpreter not found (need apps/voice-engine/.venv or python3 on PATH)"
elif ! "$PY" -m ruff --version > /dev/null 2>&1; then
  fail "ruff not installed in $PY — run: cd $VOICE_ENGINE_DIR && python3 -m venv .venv && .venv/bin/pip install -e \".[dev]\""
else
  RUFF_OUTPUT=$(cd "$VOICE_ENGINE_DIR" && "$PY" -m ruff check . 2>&1)
  RUFF_EXIT=$?

  if [ $RUFF_EXIT -eq 0 ]; then
    pass "ADR-004: ruff clean ($VOICE_ENGINE_DIR)"
  else
    fail "ADR-004: ruff lint failed"
    echo "$RUFF_OUTPUT" | tail -20
  fi
fi

# ──────────────────────────────────────────────────────────────
# Check 9b (extended only): ADR-004 — Python typecheck (mypy).
#
# Pipecat's type stubs evolve with each upstream release, so mypy errors
# here often reflect pipecat API churn rather than bugs in our code.
# Excluded from the standard run; include with --extended for CI / releases.
# ──────────────────────────────────────────────────────────────
if [ $RUN_EXTENDED -eq 1 ]; then
  print_header "Check 9b / ${TOTAL_CHECKS}: ADR-004 — Python typecheck (mypy) [extended]"

  if [ -z "$PY" ]; then
    fail "Python interpreter not found"
  elif ! "$PY" -m mypy --version > /dev/null 2>&1; then
    fail "mypy not installed in $PY — run: cd $VOICE_ENGINE_DIR && .venv/bin/pip install -e \".[dev]\""
  else
    MYPY_OUTPUT=$(cd "$VOICE_ENGINE_DIR" && "$PY" -m mypy src/ 2>&1)
    MYPY_EXIT=$?

    if [ $MYPY_EXIT -eq 0 ]; then
      pass "ADR-004: mypy clean ($VOICE_ENGINE_DIR)"
    else
      fail "ADR-004: mypy typecheck failed"
      echo "$MYPY_OUTPUT" | tail -20
    fi
  fi
fi

# ──────────────────────────────────────────────────────────────
# Check 10: ADR-004 — Python tests (pytest).
# ──────────────────────────────────────────────────────────────
print_header "Check 10 / ${TOTAL_CHECKS}: ADR-004 — Python tests (pytest)"

if [ -z "$PY" ]; then
  fail "Python interpreter not found"
elif ! "$PY" -m pytest --version > /dev/null 2>&1; then
  fail "pytest not installed in $PY — run: cd $VOICE_ENGINE_DIR && .venv/bin/pip install -e \".[dev]\""
else
  PYTEST_OUTPUT=$(cd "$VOICE_ENGINE_DIR" && "$PY" -m pytest --maxfail=1 --disable-warnings -q 2>&1)
  if [ $? -eq 0 ]; then
    PYTEST_COUNT=$(echo "$PYTEST_OUTPUT" | grep -oE "[0-9]+ passed" | head -1)
    pass "ADR-004: pytest ($PYTEST_COUNT)"
  else
    fail "ADR-004: pytest failed"
    echo "$PYTEST_OUTPUT" | tail -30
  fi
fi

# ──────────────────────────────────────────────────────────────
# Check 11: Phase 3 Revision 3 — STT/TTS provider factory unit tests
# ──────────────────────────────────────────────────────────────
print_header "Check 11 / ${TOTAL_CHECKS}: Provider factory unit tests (test_stt_factory + test_tts_factory)"

STT_FACTORY_TEST="$VOICE_ENGINE_DIR/tests/test_stt_factory.py"
TTS_FACTORY_TEST="$VOICE_ENGINE_DIR/tests/test_tts_factory.py"

if [ -z "$PY" ]; then
  fail "Python interpreter not found"
elif ! "$PY" -m pytest --version > /dev/null 2>&1; then
  fail "pytest not installed in $PY"
elif [ ! -f "$STT_FACTORY_TEST" ] || [ ! -f "$TTS_FACTORY_TEST" ]; then
  fail "Provider factory test files not found (expected tests/test_stt_factory.py + test_tts_factory.py)"
else
  PROVIDER_PYTEST=$(cd "$VOICE_ENGINE_DIR" && "$PY" -m pytest \
    tests/test_stt_factory.py tests/test_tts_factory.py \
    -v --tb=short 2>&1)
  if [ $? -eq 0 ]; then
    PROVIDER_COUNT=$(echo "$PROVIDER_PYTEST" | grep -oE "[0-9]+ passed" | head -1)
    pass "Provider factory tests ($PROVIDER_COUNT)"
  else
    fail "Provider factory tests failed"
    echo "$PROVIDER_PYTEST" | tail -30
  fi
fi

# ──────────────────────────────────────────────────────────────
# Check 12: Phase 3 Revision 3 — New adapter files exist
# ──────────────────────────────────────────────────────────────
print_header "Check 12 / ${TOTAL_CHECKS}: Provider adapter files present (v0.5.0)"

REQUIRED_PROVIDER_FILES=(
  "$VOICE_ENGINE_DIR/src/adapters/stt/__init__.py"
  "$VOICE_ENGINE_DIR/src/adapters/stt/factory.py"
  "$VOICE_ENGINE_DIR/src/adapters/stt/whisper_stt_service.py"
  "$VOICE_ENGINE_DIR/src/adapters/tts/__init__.py"
  "$VOICE_ENGINE_DIR/src/adapters/tts/factory.py"
  "$VOICE_ENGINE_DIR/src/adapters/tts/kokoro_tts_service.py"
  "apps/whisper-stt/main.py"
  "apps/whisper-stt/Dockerfile"
  "apps/whisper-stt/railway.json"
)

MISSING_PROVIDER_FILES=()
for f in "${REQUIRED_PROVIDER_FILES[@]}"; do
  [ ! -f "$f" ] && MISSING_PROVIDER_FILES+=("$f")
done

if [ ${#MISSING_PROVIDER_FILES[@]} -eq 0 ]; then
  pass "All ${#REQUIRED_PROVIDER_FILES[@]} provider adapter files present"
else
  fail "Missing provider adapter files:"
  for f in "${MISSING_PROVIDER_FILES[@]}"; do
    echo "  - $f"
  done
fi

# ──────────────────────────────────────────────────────────────
# Check 13: Phase 3 Revision 3 — Smoke tests against live URL (optional)
# ──────────────────────────────────────────────────────────────
print_header "Check 13 / ${TOTAL_CHECKS}: Provider smoke tests (optional — requires --smoke + SMOKE_TEST_URL)"

if [ $RUN_SMOKE -eq 0 ]; then
  warn "Skipped — pass --smoke and set SMOKE_TEST_URL to enable"
  ((PASS_COUNT++))  # non-failure skip
elif [ -z "${SMOKE_TEST_URL:-}" ]; then
  warn "SMOKE_TEST_URL is not set — skipping smoke tests"
  ((PASS_COUNT++))
elif [ -z "$PY" ] || ! "$PY" -m pytest --version > /dev/null 2>&1; then
  fail "pytest not available for smoke tests"
else
  SMOKE_OUT=$(cd "$VOICE_ENGINE_DIR" && SMOKE_TEST_URL="$SMOKE_TEST_URL" \
    "$PY" -m pytest tests/test_providers_smoke.py tests/smoke_test.py \
    --run-smoke -v --tb=short 2>&1)
  if [ $? -eq 0 ]; then
    pass "Provider smoke tests passed"
  else
    fail "Provider smoke tests failed"
    echo "$SMOKE_OUT" | tail -30
  fi
fi

# ──────────────────────────────────────────────────────────────
# Summary
# ──────────────────────────────────────────────────────────────
print_header "Validation Summary"
echo "Passed: $PASS_COUNT / $TOTAL_CHECKS"
echo "Failed: $FAIL_COUNT / $TOTAL_CHECKS"

if [ $FAIL_COUNT -eq 0 ]; then
  echo -e "\n${GREEN}✓ All validations passed!${NC}"
  exit 0
else
  echo -e "\n${RED}✗ Some validations failed. See details above.${NC}"
  exit 1
fi
