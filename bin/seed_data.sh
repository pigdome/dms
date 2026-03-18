#!/usr/bin/env bash
set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

ok()      { echo -e "${GREEN}[OK]${NC} $1"; }
err()     { echo -e "${RED}[ERROR]${NC} $1"; }
waiting() { echo -e "${YELLOW}[WAIT]${NC} $1"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# ─── Activate venv ───────────────────────────────────────────────────────────
if [ ! -f "$PROJECT_ROOT/venv/bin/activate" ]; then
    err "Virtual environment not found at $PROJECT_ROOT/venv. Please create it first."
    exit 1
fi
source "$PROJECT_ROOT/venv/bin/activate"
ok "Virtual environment activated."

# ─── Run seed data ───────────────────────────────────────────────────────────
waiting "Seeding development data..."
python manage.py seed_data
ok "Seed data complete."

# ─── Fix admin role ───────────────────────────────────────────────────────────
waiting "Fixing admin role to superadmin..."
python manage.py shell -c "
from apps.core.models import CustomUser
updated = CustomUser.objects.filter(is_superuser=True).exclude(role='superadmin').update(role='superadmin')
print(f'Updated {updated} superuser(s) role to superadmin')
"
ok "Admin role fixed."

# ─── Print credentials ───────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║                  DMS Test Credentials                   ║${NC}"
echo -e "${CYAN}╠══════════════════════════════════════════════════════════╣${NC}"
echo -e "${CYAN}║${NC}  Superadmin : admin        / admin1234                  ${CYAN}║${NC}"
echo -e "${CYAN}║${NC}  Owner      : owner1       / test1234  → /dashboard/    ${CYAN}║${NC}"
echo -e "${CYAN}║${NC}  Staff      : staff1       / test1234  → /dashboard/    ${CYAN}║${NC}"
echo -e "${CYAN}║${NC}  Tenant     : tenant101    / test1234  → /tenants/home/ ${CYAN}║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""
