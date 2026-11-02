#!/usr/bin/env bash
# Reset the demo school: deletes demo_db.sqlite3, migrates, seeds the synthetic school (relative dates, or fixed with AS_OF=YYYY-MM-DD).
#   DEMO_PASSWORD=... scripts/reset_demo_school.sh     (random password printed if unset)
# Only ever touches django_core/demo_db.sqlite3 through config.settings.demo; never the real database.
set -euo pipefail
APP="$(cd "$(dirname "${BASH_SOURCE[0]}")/../django_core" && pwd)"
PY="$APP/.venv/bin/python"; [ -x "$PY" ] || PY="$(command -v python3)"
cd "$APP"
export DJANGO_SETTINGS_MODULE=config.settings.demo
rm -f "$APP/demo_db.sqlite3"
"$PY" manage.py migrate -v0
"$PY" manage.py seed_demo_school --i-know-this-is-synthetic ${DEMO_PASSWORD:+--password "$DEMO_PASSWORD"} ${AS_OF:+--as-of "$AS_OF"}
