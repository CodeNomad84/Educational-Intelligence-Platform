#!/usr/bin/env bash
# DEMO SCOPE — whole file. Safe launcher for the school-meeting demo.
#
#   scripts/start_demo.sh            preflight + start server (127.0.0.1:${DEMO_PORT:-8000}, --noreload)
#   scripts/start_demo.sh --reseed   delete demo_db.sqlite3, migrate, seed_demo --reset (use on the day of the meeting)
#   scripts/start_demo.sh --check    preflight only
#
# Always uses config.settings.demo (demo_db.sqlite3). It can not start against the real db.sqlite3.
# Environment: DEMO_PASSWORD (password for demo users on --reseed; random if unset), DEMO_PORT,
#              DEMO_SECRET_KEY (otherwise generated once into django_core/.env.demo, gitignored),
#              DEMO_ALLOW_STALE=1 (start even if the seed is older than 1 day).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="$ROOT/django_core"
PY="$APP/.venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"
PORT="${DEMO_PORT:-8000}"
MODE="serve"
RESEED=0
for arg in "$@"; do
  case "$arg" in
    --reseed) RESEED=1 ;;
    --check)  MODE="check" ;;
    -h|--help) sed -n '2,14p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

# --- fail fast on a wrong settings module ------------------------------------------------------
if [ -n "${DJANGO_SETTINGS_MODULE:-}" ] && [ "$DJANGO_SETTINGS_MODULE" != "config.settings.demo" ]; then
  echo "REFUSING TO START: DJANGO_SETTINGS_MODULE=$DJANGO_SETTINGS_MODULE (expected config.settings.demo)." >&2
  echo "Unset it and run this script again." >&2
  exit 1
fi
export DJANGO_SETTINGS_MODULE=config.settings.demo

# --- fixed demo secret (sessions survive restarts); generated once, never committed ------------
if [ -z "${DEMO_SECRET_KEY:-}" ]; then
  KEYFILE="$APP/.env.demo"
  if [ ! -s "$KEYFILE" ]; then
    umask 077
    "$PY" -c 'import secrets; print("DEMO_SECRET_KEY=" + secrets.token_urlsafe(50))' > "$KEYFILE"
  fi
  DEMO_SECRET_KEY="$(grep '^DEMO_SECRET_KEY=' "$KEYFILE" | head -n1 | cut -d= -f2-)"
fi
export SECRET_KEY="$DEMO_SECRET_KEY"

cd "$APP"

if [ "$RESEED" = 1 ]; then
  echo ">> Re-seeding demo database (demo_db.sqlite3 only): the old file is deleted first, then recreated"
  # Only this one file (fixed name, inside django_core). An old demo DB must never block --reseed: a stale seed can
  # contain students that a newer migration (students.0015, school NOT NULL) refuses to carry over.
  DEMO_DB="$APP/demo_db.sqlite3"
  [ "$(basename "$DEMO_DB")" = "demo_db.sqlite3" ] || { echo "REFUSING: unexpected demo database name." >&2; exit 1; }
  rm -f -- "$DEMO_DB" "$DEMO_DB-journal" "$DEMO_DB-wal" "$DEMO_DB-shm"
  if ! "$PY" manage.py migrate --noinput; then
    echo >&2
    echo "MIGRATE FAILED on a fresh demo database. Check the error above (missing dependency or a broken migration)." >&2
    echo "Fix: from django_core run '$PY manage.py migrate' to see the error, then rerun: scripts/start_demo.sh --reseed" >&2
    exit 1
  fi
  SEED_ARGS=(--reset)
  [ -n "${DEMO_PASSWORD:-}" ] && SEED_ARGS+=(--password "$DEMO_PASSWORD")
  "$PY" manage.py seed_demo "${SEED_ARGS[@]}"
fi

CHECK_ARGS=()
[ "${DEMO_ALLOW_STALE:-0}" = 1 ] && CHECK_ARGS+=(--allow-stale)
"$PY" manage.py demo_check "${CHECK_ARGS[@]}"

[ "$MODE" = "check" ] && exit 0

if (exec 3<>"/dev/tcp/127.0.0.1/$PORT") 2>/dev/null; then
  echo "Port $PORT is already in use (another server or the Docker stack?). Set DEMO_PORT or stop it." >&2
  exit 1
fi

echo
echo "Starting on http://127.0.0.1:$PORT/  (no auto-reload; Ctrl-C to stop)"
exec "$PY" manage.py runserver "127.0.0.1:$PORT" --noreload
