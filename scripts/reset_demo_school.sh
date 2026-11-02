#!/usr/bin/env bash
# Reset the demo school: deletes demo_db.sqlite3, migrates, seeds the synthetic school (relative dates, or fixed with AS_OF=YYYY-MM-DD).
#   DEMO_PASSWORD=... scripts/reset_demo_school.sh     (random password printed if unset)
# Only ever touches the demo database file (default django_core/demo_db.sqlite3; EIP_DEMO_DB=<path> for another file, e.g. a temporary one)
# through config.settings.demo; refuses a file named db.sqlite3 (the real database).
set -euo pipefail
APP="$(cd "$(dirname "${BASH_SOURCE[0]}")/../django_core" && pwd)"
PY="$APP/.venv/bin/python"; [ -x "$PY" ] || PY="$(command -v python3)"
cd "$APP"
export DJANGO_SETTINGS_MODULE=config.settings.demo
export EIP_DEMO_DB="${EIP_DEMO_DB:-$APP/demo_db.sqlite3}"
case "$(basename "$EIP_DEMO_DB")" in db.sqlite3|*.env) echo "refusing: $EIP_DEMO_DB" >&2; exit 2;; esac
rm -f "$EIP_DEMO_DB"
"$PY" manage.py migrate -v0
"$PY" manage.py seed_demo_school --i-know-this-is-synthetic ${DEMO_PASSWORD:+--password "$DEMO_PASSWORD"} ${AS_OF:+--as-of "$AS_OF"}
