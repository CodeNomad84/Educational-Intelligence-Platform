#!/usr/bin/env bash
# Single test command for the Django side.
#
#   scripts/run_tests.sh            same as "sqlite" (the original behaviour, unchanged)
#   scripts/run_tests.sh sqlite     check, makemigrations --check, tests (SQLite, in memory) + demo_intel (demo settings)
#   scripts/run_tests.sh pg         check, makemigrations --check, tests on PostgreSQL 16 in a DISPOSABLE container
#   scripts/run_tests.sh all        sqlite, then pg; stops at the first failure
#
# sqlite mode runs, in order, and stops at the first failure:
#   1. manage.py check                           (config.settings.development)
#   2. manage.py makemigrations --check --dry-run
#   3. manage.py test students dashboard schools (config.settings.development)
#   4. manage.py test demo_intel                 (config.settings.demo)
# Tests use throw-away in-memory SQLite databases; no .env file is read and no seed/reset runs.
# Environment: PYTHON (interpreter; default django_core/.venv/bin/python, else python3).
#
# pg mode (FastAPI is still NOT covered). It FAILS HARD (exit 3, nothing started) when Docker, the daemon or an image is
# missing; it never pulls an image and never falls back to SQLite, so "PostgreSQL passed" cannot be claimed without
# running it.
#   PG_IMAGE      PostgreSQL image, default pgvector/pgvector:pg16; must already exist locally
#   DJANGO_IMAGE  image to run the tests in. Unset: the script BUILDS eip-test-django:local from django_core/Dockerfile and
#                 requirements.txt only; if that build fails (e.g. the registry is unreachable) an EXISTING local eip-test-django:local
#                 is used with a warning, and without one it is a hard failure. The build uses
#                 requirements.txt only (the source is mounted read-only at run time). Set: that image must exist locally.
# It creates an INTERNAL private network (no route to the outside: the test containers have no internet access) and a
# throw-away PostgreSQL container (tmpfs data, name suffix from the process id and the time), generates a random
# password per run (passed to the containers through the environment, never written to disk or to the command line),
# runs steps 1-3 with config.settings.test_postgres, and removes the container, the network and the temporary build
# context on exit (also on error, Ctrl-C or SIGTERM: INT exits 130, TERM exits 143). The real database, data/postgres, .env
# and docker-compose are never touched. django_core is mounted read-only, with the local-only files hidden from the
# container (bind-mounted /dev/null over db.sqlite3, demo_db.sqlite3, data.xlsx, data.ods and every .env*, an empty tmpfs over
# .venv); only files that exist on the host are overlaid. The image BUILD (the only step that may need the network, for
# uncached layers) runs before the internal network exists, on Docker's default network.
# KNOWN LIMIT: "internal" removes every route to the outside, but the network's gateway address is on-link, so a service
# the host binds to ALL interfaces is reachable from the test container (observed: the host's Ollama on *:11434). The
# container-only test records what answers; EIP_TEST_STRICT_GATEWAY=1 (set on the host) makes it fail if anything does.
#
# Exit codes: 0 all passed, 1 a check or test failed, 2 usage error, 3 PostgreSQL mode prerequisites missing.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="$ROOT/django_core"
MODE="${1:-sqlite}"
# Names of the disposable resources are GLOBAL on purpose: the EXIT trap must still see them when set -e ends the script
# inside a function (a bash-version-dependent behaviour for "local" variables, which left resources behind).
PGC=""
NET=""
CTX=""

usage() { echo "usage: scripts/run_tests.sh [sqlite|pg|all]" >&2; exit 2; }
[ "$#" -le 1 ] || usage
case "$MODE" in sqlite|pg|all) ;; *) usage ;; esac

fail_prereq() { echo "PostgreSQL mode cannot run: $1" >&2; exit 3; }

run_sqlite() {
  local PY="${PYTHON:-$APP/.venv/bin/python}"
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
}

cleanup_pg() {
  [ -z "${PGC:-}" ] || docker rm -f "$PGC" >/dev/null 2>&1 || true
  [ -z "${NET:-}" ] || docker network rm "$NET" >/dev/null 2>&1 || true
  if [ -n "${CTX:-}" ] && [ -d "$CTX" ]; then rm -rf -- "$CTX"; fi
  CTX=""
}

run_pg() {
  command -v docker >/dev/null 2>&1 || fail_prereq "the docker command is not installed"
  docker info >/dev/null 2>&1 || fail_prereq "the Docker daemon is not reachable"
  local PG_IMAGE="${PG_IMAGE:-pgvector/pgvector:pg16}"
  docker image inspect "$PG_IMAGE" >/dev/null 2>&1 \
    || fail_prereq "image $PG_IMAGE is not available locally (docker pull $PG_IMAGE); the script never pulls on its own"
  local IMAGE="${DJANGO_IMAGE:-}"
  trap cleanup_pg EXIT           # armed before anything is created, so the temporary build context is always removed
  trap 'exit 130' INT
  trap 'exit 143' TERM
  if [ -n "$IMAGE" ]; then
    docker image inspect "$IMAGE" >/dev/null 2>&1 || fail_prereq "DJANGO_IMAGE $IMAGE does not exist locally"
  else
    IMAGE="eip-test-django:local"
    echo ">> building $IMAGE from django_core/Dockerfile and requirements.txt"
    CTX="$(mktemp -d)"
    cp "$APP/Dockerfile" "$APP/requirements.txt" "$CTX/"
    if ! docker build -q -t "$IMAGE" "$CTX" >/dev/null; then
      # registry unreachable (or any build failure): an image that already exists locally is used, with a warning
      # (it may be older than requirements.txt); with no local image this is still a hard failure.
      docker image inspect "$IMAGE" >/dev/null 2>&1 || fail_prereq "building $IMAGE failed and no local $IMAGE exists"
      echo ">> WARNING: building $IMAGE failed; using the existing local image (it may not match requirements.txt)" >&2
    fi
    rm -rf -- "$CTX"; CTX=""
  fi

  local suffix; suffix="$$-$(date +%s)"
  NET="eip-test-net-$suffix"
  PGC="eip-test-pg-$suffix"
  local pw; pw="$(head -c 16 /dev/urandom | od -An -tx1 | tr -d ' \n')"
  export POSTGRES_PASSWORD="$pw" TEST_PG_PASSWORD="$pw"   # values reach the containers via the environment only

  docker network create --internal "$NET" >/dev/null
  docker run -d --rm --name "$PGC" --network "$NET" --tmpfs /var/lib/postgresql/data \
    -e POSTGRES_DB=eip_test -e POSTGRES_USER=eip_test -e POSTGRES_PASSWORD "$PG_IMAGE" >/dev/null
  local ready=0 i
  for i in $(seq 1 60); do
    if docker exec "$PGC" pg_isready -U eip_test -d eip_test >/dev/null 2>&1; then ready=1; break; fi
    sleep 1
  done
  [ "$ready" = 1 ] || { echo "PostgreSQL container did not become ready in 60 s" >&2; exit 1; }

  # Local-only files of django_core are HIDDEN from the container (only those that exist on the host are overlaid):
  # /dev/null bind-mounted over files, an empty tmpfs over .venv.
  local hide=() f
  for f in db.sqlite3 demo_db.sqlite3 data.xlsx data.ods; do
    if [ -e "$APP/$f" ]; then hide+=(-v "/dev/null:/repo/django_core/$f:ro"); fi
  done
  for f in "$APP"/.env*; do
    if [ -e "$f" ]; then hide+=(-v "/dev/null:/repo/django_core/${f##*/}:ro"); fi
  done
  if [ -d "$APP/.venv" ]; then hide+=(--tmpfs "/repo/django_core/.venv:ro,size=64k"); fi

  dj() {
    # django_core and scripts/ only (read-only), laid out like the repository so that the tooling tests find both;
    # the repository root (.env, data/, ...) is never mounted
    docker run --rm --network "$NET" -v "$APP:/repo/django_core:ro" -v "$ROOT/scripts:/repo/scripts:ro" \
      ${hide[@]+"${hide[@]}"} -w /repo/django_core -e EIP_TEST_CONTAINER=1 -e EIP_TEST_STRICT_GATEWAY \
      -e DJANGO_SETTINGS_MODULE=config.settings.test_postgres \
      -e TEST_PG_HOST="$PGC" -e TEST_PG_NAME=eip_test -e TEST_PG_USER=eip_test -e TEST_PG_PASSWORD \
      "$IMAGE" python -B manage.py "$@"
  }
  echo
  echo ">> [PostgreSQL 16 container] manage.py check";                    dj check
  echo ">> [PostgreSQL 16 container] manage.py makemigrations --check --dry-run"; dj makemigrations --check --dry-run
  echo ">> [PostgreSQL 16 container] manage.py test students dashboard schools"; dj test students dashboard schools --noinput
  cleanup_pg
  trap - EXIT INT TERM
}

case "$MODE" in
  sqlite)
    run_sqlite
    echo
    echo "ALL DJANGO CHECKS AND TESTS PASSED (FastAPI / PostgreSQL / Docker not covered)"
    ;;
  pg)
    run_pg
    echo
    echo "POSTGRESQL CHECKS AND TESTS PASSED (PostgreSQL 16 in a disposable container; FastAPI not covered)"
    ;;
  all)
    run_sqlite
    run_pg
    echo
    echo "ALL DJANGO CHECKS AND TESTS PASSED ON SQLITE AND POSTGRESQL (FastAPI not covered)"
    ;;
esac
