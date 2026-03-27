#!/usr/bin/env bash
# Run Playwright E2E tests against a running DMS server.
# Usage: ./bin/run_e2e.sh [--url http://host:port]
#   Default BASE_URL: http://localhost:8000
#
# Prerequisites:
#   - Server is running (docker-compose up, or python manage.py runserver)
#   - Seed data loaded (./bin/seed_data.sh)
#   - Playwright installed: pip install playwright && playwright install chromium
set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

ok()      { echo -e "${GREEN}[OK]${NC} $1"; }
err()     { echo -e "${RED}[ERROR]${NC} $1"; }
info()    { echo -e "${CYAN}[INFO]${NC} $1"; }
waiting() { echo -e "${YELLOW}[WAIT]${NC} $1"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# ─── Parse --url flag ─────────────────────────────────────────────────────────
BASE_URL="http://localhost:8000"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --url)
            BASE_URL="$2"
            shift 2
            ;;
        *)
            shift
            ;;
    esac
done

# ─── Activate venv ───────────────────────────────────────────────────────────
if [ ! -f "$PROJECT_ROOT/venv/bin/activate" ]; then
    err "Virtual environment not found at $PROJECT_ROOT/venv"
    exit 1
fi
source "$PROJECT_ROOT/venv/bin/activate"

# ─── Check Playwright is installed ───────────────────────────────────────────
if ! python -c "import playwright" 2>/dev/null; then
    err "Playwright not installed. Run: pip install playwright && playwright install chromium"
    exit 1
fi

# ─── Wait for server to be ready ─────────────────────────────────────────────
waiting "Waiting for server at $BASE_URL (or auto-detecting ports 8000, 18000)..."
MAX_WAIT=30
WAITED=0
until curl -sf "$BASE_URL/login/" -o /dev/null 2>/dev/null; do
    # Auto-detect if using default
    if [[ "$BASE_URL" == "http://localhost:8000" ]]; then
        if curl -sf "http://localhost:18000/login/" -o /dev/null 2>/dev/null; then
            BASE_URL="http://localhost:18000"
            info "Auto-switched to running server at $BASE_URL"
            break
        fi
    fi

    if [ $WAITED -ge $MAX_WAIT ]; then
        err "Server did not become ready within ${MAX_WAIT}s. Is it running?"
        err "Hint: docker-compose up -d  OR  python manage.py runserver"
        exit 1
    fi
    sleep 1
    WAITED=$((WAITED + 1))
done
ok "Server is ready at $BASE_URL."

# ─── Run E2E tests ───────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}══════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}   DMS E2E Tests  (${BASE_URL})${NC}"
echo -e "${CYAN}══════════════════════════════════════════════════════════${NC}"
info "Screenshots → $PROJECT_ROOT/screenshots/"
info "Results     → $PROJECT_ROOT/e2e_results.txt"
echo ""

set +e
BASE_URL="$BASE_URL" python e2e_test.py
EXIT_CODE=$?
set -e

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    ok "All E2E tests passed."
else
    err "Some E2E tests failed (exit code $EXIT_CODE). Check e2e_results.txt and screenshots/."
fi

exit $EXIT_CODE
