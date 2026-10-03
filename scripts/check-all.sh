#!/usr/bin/env bash
# The local gate before every push (GitHub Actions is blocked; PRODUCTION_READINESS_PLAN.md §11.2).
#
#   bash scripts/check-all.sh          backend + frontend checks, migration tests, a pytest subset
#   bash scripts/check-all.sh --full   ...and the whole pytest suite (~8 min) instead of the subset
#
# Needs `docker compose up -d` for the tests. Stops at the first failure.
set -euo pipefail
cd "$(dirname "$0")/.."

export TEST_DATABASE_URL="${TEST_DATABASE_URL:-postgresql+asyncpg://ridematch:ridematch@127.0.0.1:5434/ridematch_test}"
export TEST_REDIS_URL="${TEST_REDIS_URL:-redis://127.0.0.1:6379/15}"

step() { printf '\n== %s\n' "$*"; }

step "backend: ruff, format, import"
(cd backend && uv run ruff check . && uv run ruff format --check . && uv run python -c "import app.main")

step "frontend: typecheck, lint, test, build"
(cd frontend && npm run typecheck && npm run lint && npm run test -- --run && npm run build)

step "tests: lint"
(cd tests && uv run ruff check . && uv run ruff format --check .)

if [ "${1:-}" = "--full" ]; then
  step "tests: full suite"
  (cd tests && uv run pytest -q -rs)
else
  step "tests: unit, migrations, and a cross-section of the API"
  (cd tests && uv run pytest -q -rs unit migrations \
    api/test_health.py api/test_auth.py api/test_onboarding.py api/test_websocket.py \
    api/test_request_lifecycle.py api/test_body_limit.py api/test_sentry_scrubbing.py)
fi

printf '\nAll checks passed. Read the pytest summary above for skips: an unreachable DB skips.\n'
