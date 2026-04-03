#!/usr/bin/env bash
set -e

# ── Colors & helpers ──────────────────────────────────────────────────────────
BOLD='\033[1m'
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
DIM='\033[2m'
NC='\033[0m'

info()    { echo -e "${CYAN}${BOLD}$1${NC}"; }
ok()      { echo -e "${GREEN}[OK]${NC} $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()     { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }
dim()     { echo -e "${DIM}$1${NC}"; }

# ── Resolve project root ──────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo ""
info "Starting DMS release process..."
echo ""

# ── Check git repo ────────────────────────────────────────────────────────────
git rev-parse --git-dir > /dev/null 2>&1 || err "Not a git repository."

# ── Get current version from latest tag ──────────────────────────────────────
CURRENT_TAG=$(git tag --sort=-version:refname | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' | head -1)
if [ -z "$CURRENT_TAG" ]; then
    CURRENT_TAG="v0.0.0"
    warn "No version tag found — starting from v0.0.0"
fi

# Strip leading 'v'
VERSION="${CURRENT_TAG#v}"
MAJOR=$(echo "$VERSION" | cut -d. -f1)
MINOR=$(echo "$VERSION" | cut -d. -f2)
PATCH=$(echo "$VERSION" | cut -d. -f3)

# ── Compute next versions ─────────────────────────────────────────────────────
NEXT_PATCH="v${MAJOR}.${MINOR}.$((PATCH + 1))"
NEXT_MINOR="v${MAJOR}.$((MINOR + 1)).0"
NEXT_MAJOR="v$((MAJOR + 1)).0.0"

# ── Show menu ─────────────────────────────────────────────────────────────────
dim "Current Version: ${CURRENT_TAG}"
echo ""
echo -e "  Version Management:"
echo -e "  [1] No Change  (Stay at ${CURRENT_TAG})"
echo -e "  [2] Patch      (${CURRENT_TAG} -> ${NEXT_PATCH})"
echo -e "  [3] Minor      (${CURRENT_TAG} -> ${NEXT_MINOR})"
echo -e "  [4] Major      (${CURRENT_TAG} -> ${NEXT_MAJOR})"
echo ""
read -r -p "$(echo -e "${YELLOW}${BOLD}  Choose an option [1-4] (default 1): ${NC}")" CHOICE
CHOICE="${CHOICE:-1}"

case "$CHOICE" in
    1) NEW_TAG="$CURRENT_TAG" ;;
    2) NEW_TAG="$NEXT_PATCH" ;;
    3) NEW_TAG="$NEXT_MINOR" ;;
    4) NEW_TAG="$NEXT_MAJOR" ;;
    *) err "Invalid choice: $CHOICE" ;;
esac

echo ""

# ── Check for uncommitted changes ─────────────────────────────────────────────
if ! git diff --quiet || ! git diff --cached --quiet; then
    warn "You have uncommitted changes."
    git status --short
    echo ""
    read -r -p "$(echo -e "${YELLOW}${BOLD}  Commit message (leave empty for default): ${NC}")" COMMIT_MSG
    [ -z "$COMMIT_MSG" ] && COMMIT_MSG="chore: bump version to ${NEW_TAG}"

    git add -A
    git commit -m "$COMMIT_MSG"
    ok "Changes committed."
else
    ok "Working tree is clean."
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
info "Release complete!"
dim "  Version : ${NEW_TAG}"
dim "  Commit  : $(git log -1 --format='%h %s')"
echo ""
