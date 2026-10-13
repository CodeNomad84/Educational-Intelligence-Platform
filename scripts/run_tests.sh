#!/usr/bin/env bash
# Single Django test command (Phase 2.0). Django only: FastAPI, PostgreSQL and Docker are NOT covered
# (deferred verification gate, see docs/TESTING.md).
#
#   scripts/run_tests.sh
#
# Runs, in order, and stops at the first failure:
#   1. manage.py check                           (config.settings.development)
#   2. manage.py makemigrations --check --dry-run
#   3. manage.py test students dashboard schools (config.settings.development)
#   4. manage.py test demo_intel                 (config.settings.demo)
# Tests use throw-away in-memory SQLite databases; no .env file is read and no seed/reset runs.
# Environment: PYTHON (interpreter; default django_core/.venv/bin/python, else python3).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="$ROOT/django_core"
PY="${PYTHON:-$APP/.venv/bin/python}"
[ -x "$PY" ] || PY="$(command -v python3)"

cd "$APP"

run() {
  local settings="$1"; shift
  echo
  echo ">> [$settings] manage.py $*"
  DJANGO_SETTINGS_MODULE="$settings" "$PY" manage.py "$@"
}

run config.settings.development check
run config.settings.development makemigrations --check --dry-run
run config.settings.development test students dashboard schools
run config.settings.demo test demo_intel

echo
echo "ALL DJANGO CHECKS AND TESTS PASSED (FastAPI / PostgreSQL / Docker not covered)"
