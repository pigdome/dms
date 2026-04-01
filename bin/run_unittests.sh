#!/usr/bin/env bash
# Run Django unit tests for all DMS apps.
# Usage: ./bin/run_unittests.sh [extra manage.py test args]
#   e.g. ./bin/run_unittests.sh --verbosity=2
#        ./bin/run_unittests.sh apps.billing
set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

ok()   { echo -e "${GREEN}[OK]${NC} $1"; }
err()  { echo -e "${RED}[ERROR]${NC} $1"; }
info() { echo -e "${CYAN}[INFO]${NC} $1"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# ─── Activate venv ───────────────────────────────────────────────────────────
if [ ! -f "$PROJECT_ROOT/venv/bin/activate" ]; then
    err "Virtual environment not found at $PROJECT_ROOT/venv"
    exit 1
fi
source "$PROJECT_ROOT/venv/bin/activate"

# ─── Default test labels (all apps) ──────────────────────────────────────────
DEFAULT_APPS=(
    apps.core
    apps.billing
    apps.tenants
    apps.rooms
    apps.maintenance
    apps.notifications
    apps.dashboard
)

if [ $# -gt 0 ]; then
    TEST_TARGETS=("$@")
else
    TEST_TARGETS=("${DEFAULT_APPS[@]}")
fi

echo ""
echo -e "${CYAN}══════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}   DMS Unit Tests${NC}"
echo -e "${CYAN}══════════════════════════════════════════════════════════${NC}"
info "Running: python manage.py test ${TEST_TARGETS[*]} --no-input"
echo ""

set +e
python manage.py test "${TEST_TARGETS[@]}" --no-input
EXIT_CODE=$?
set -e

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    ok "All tests passed."
else
    err "Some tests failed (exit code $EXIT_CODE)."
fi

exit $EXIT_CODE
