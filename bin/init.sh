#!/usr/bin/env bash
set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

ok()      { echo -e "${GREEN}[OK]${NC} $1"; }
err()     { echo -e "${RED}[ERROR]${NC} $1"; }
waiting() { echo -e "${YELLOW}[WAIT]${NC} $1"; }

# Resolve project root (parent of bin/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# ─── Step 1: Check Docker is running ─────────────────────────────────────────
waiting "Checking Docker is running..."
if ! docker info > /dev/null 2>&1; then
    err "Docker is not running. Please start Docker and try again."
    exit 1
fi
ok "Docker is running."

# ─── Step 2: Start db and redis via docker-compose (detached) ────────────────
waiting "Starting db and redis containers..."
docker compose up -d db redis
ok "db and redis containers started."

# ─── Step 3: Wait for PostgreSQL to be ready ─────────────────────────────────
waiting "Waiting for PostgreSQL to be ready..."
MAX_RETRIES=30
RETRY=0
until docker compose exec -T db pg_isready -U dms -d dms > /dev/null 2>&1; do
    RETRY=$((RETRY + 1))
    if [ "$RETRY" -ge "$MAX_RETRIES" ]; then
        err "PostgreSQL did not become ready after ${MAX_RETRIES} attempts. Aborting."
        exit 1
    fi
    waiting "PostgreSQL not ready yet (attempt ${RETRY}/${MAX_RETRIES})... retrying in 2s"
    sleep 2
done
ok "PostgreSQL is ready."

# ─── Step 4: Activate venv ───────────────────────────────────────────────────
waiting "Activating virtual environment..."
if [ ! -f "$PROJECT_ROOT/venv/bin/activate" ]; then
    err "Virtual environment not found at $PROJECT_ROOT/venv. Please create it first."
    exit 1
fi
# shellcheck source=/dev/null
source "$PROJECT_ROOT/venv/bin/activate"
ok "Virtual environment activated."

# ─── Step 5: Run migrations ──────────────────────────────────────────────────
waiting "Running database migrations..."
python manage.py migrate --noinput
ok "Migrations complete."

# ─── Step 6: Create superuser (idempotent) ───────────────────────────────────
waiting "Creating superuser (if not exists)..."
python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
user, created = User.objects.get_or_create(username='admin', defaults={'email': 'admin@dms.local', 'is_staff': True, 'is_superuser': True})
if created:
    user.set_password('admin1234')
user.role = 'superadmin'
user.save()
print('Superuser created.' if created else 'Superuser role updated to superadmin.')
"
ok "Superuser step done."

# ─── Step 7: Collect static files ────────────────────────────────────────────
waiting "Collecting static files..."
python manage.py collectstatic --noinput
ok "Static files collected."

# ─── Step 8: Start runserver ─────────────────────────────────────────────────
ok "Starting Django development server on 0.0.0.0:8000..."
exec python manage.py runserver 0.0.0.0:8000
