#!/usr/bin/env bash
# Backup -> restore into a SEPARATE EMPTY database -> app checks -> row counts compared. Synthetic demo data only.
#
#   scripts/backup_restore_check.sh            sqlite path, then the PostgreSQL path if Docker + the local images exist
#   scripts/backup_restore_check.sh sqlite     SQLite path only
#   scripts/backup_restore_check.sh pg         PostgreSQL path only (exit 3 when Docker or an image is missing)
#
# SQLite path: the source (default django_core/demo_db.sqlite3, override with SOURCE_DB) is opened READ-ONLY; its sha256 is
#   compared before and after (it must not change). Backup = online backup copy + SQL dump; restore = the SQL dump loaded
#   into a new empty file. Checks on the restored file: PRAGMA integrity_check and foreign_key_check, manage.py check,
#   manage.py migrate --check, and the row counts below read through the ORM.
# PostgreSQL path (the pg_dump / psql route of docs/RUNBOOK.md): a throw-away PostgreSQL 16 container on an INTERNAL network,
#   random password per run, nothing on disk but a temp dir that is removed on exit. The demo data is moved into database
#   eip_restore_src with dumpdata/loaddata, `pg_dump` takes the backup, it is restored with `psql` into the EMPTY database
#   eip_restore_dst, and the same checks run there (manage.py in the local image eip-test-django:local; never built or
#   pulled here).
# Compared tables (source vs restored; any difference fails): students_student, students_grade, students_recommendation,
#   schools_auditevent.
# Exit codes: 0 all passed, 1 a check failed, 2 usage error, 3 prerequisites for the pg path missing.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="$ROOT/django_core"
MODE="${1:-auto}"
SOURCE_DB="${SOURCE_DB:-$APP/demo_db.sqlite3}"
PY="${PYTHON:-$APP/.venv/bin/python}"; [ -x "$PY" ] || PY="$(command -v python3)"
PG_IMAGE="${PG_IMAGE:-pgvector/pgvector:pg16}"
DJANGO_IMAGE="${DJANGO_IMAGE:-eip-test-django:local}"
TABLES="students_student students_grade students_recommendation schools_auditevent"
WORK=""; PGC=""; NET=""

[ "$#" -le 1 ] || { echo "usage: scripts/backup_restore_check.sh [auto|sqlite|pg]" >&2; exit 2; }
case "$MODE" in auto|sqlite|pg) ;; *) echo "usage: scripts/backup_restore_check.sh [auto|sqlite|pg]" >&2; exit 2 ;; esac

cleanup() {
  [ -z "$PGC" ] || docker rm -f "$PGC" >/dev/null 2>&1 || true
  [ -z "$NET" ] || docker network rm "$NET" >/dev/null 2>&1 || true
  if [ -n "$WORK" ] && [ -d "$WORK" ]; then rm -rf -- "$WORK"; fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
WORK="$(mktemp -d)"
FAILED=0
compare() {   # compare LABEL "t n" lines of source vs restored
  local label="$1" src="$2" dst="$3"
  echo "-- row counts ($label)"; printf '%-28s %10s %10s\n' table source restored
  local t a b
  for t in $TABLES; do
    a="$(echo "$src" | awk -v t="$t" '$1==t{print $2}')"; b="$(echo "$dst" | awk -v t="$t" '$1==t{print $2}')"
    printf '%-28s %10s %10s %s\n' "$t" "$a" "$b" "$([ -n "$a" ] && [ "$a" = "$b" ] && echo OK || echo MISMATCH)"
    if [ -z "$a" ] || [ "$a" != "$b" ]; then FAILED=1; fi
  done
}
dj() {   # host manage.py against the restore_check settings (environment decides the database)
  ( cd "$APP" && DJANGO_SETTINGS_MODULE=config.settings.restore_check "$PY" -B manage.py "$@" )
}
ORM_COUNTS='
from django.apps import apps
for label in ("students.Student", "students.Grade", "students.Recommendation", "schools.AuditEvent"):
    m = apps.get_model(label); print(m._meta.db_table, m.objects.count())'

run_sqlite() {
  [ -f "$SOURCE_DB" ] || { echo "source database not found: $SOURCE_DB" >&2; exit 1; }
  echo "== SQLite path: $(basename "$SOURCE_DB") -> backup -> restore into an empty file =="
  local before after; before="$(sha256sum "$SOURCE_DB" | cut -d' ' -f1)"
  "$PY" -I - "$SOURCE_DB" "$WORK/backup.sqlite3" "$WORK/backup.sql" <<'PYEOF'
import sqlite3, sys
src_path, copy_path, dump_path = sys.argv[1:4]
src = sqlite3.connect(f'file:{src_path}?mode=ro', uri=True)
copy = sqlite3.connect(copy_path); src.backup(copy); copy.close()          # online backup copy
with open(dump_path, 'w', encoding='utf-8') as out:                         # SQL dump = the portable backup
    for line in src.iterdump():
        out.write(line + '\n')
PYEOF
  echo "backup: $(wc -c < "$WORK/backup.sql") bytes of SQL"
  "$PY" -I - "$WORK/backup.sql" "$WORK/restored.sqlite3" <<'PYEOF'
import sqlite3, sys
db = sqlite3.connect(sys.argv[2])                                           # a NEW empty file
assert db.execute("select count(*) from sqlite_master").fetchone()[0] == 0
db.executescript(open(sys.argv[1], encoding='utf-8').read()); db.commit(); db.close()
PYEOF
  echo "restored into an empty file"
  "$PY" -I - "$WORK/restored.sqlite3" <<'PYEOF'
import sqlite3, sys
db = sqlite3.connect(sys.argv[1])
ok = db.execute('pragma integrity_check').fetchone()[0]; fk = db.execute('pragma foreign_key_check').fetchall()
print('integrity_check:', ok, '| foreign_key_check violations:', len(fk)); sys.exit(0 if ok == 'ok' and not fk else 1)
PYEOF
  export RC_SQLITE_PATH="$WORK/restored.sqlite3"
  dj check --database default && echo "manage.py check: OK"
  dj migrate --check && echo "manage.py migrate --check: OK (no unapplied migration)"
  local src dst
  src="$("$PY" -I -c "
import sqlite3,sys
c=sqlite3.connect('file:$SOURCE_DB?mode=ro',uri=True)
for t in '$TABLES'.split(): print(t, c.execute('select count(*) from '+t).fetchone()[0])")"
  dst="$(dj shell -c "$ORM_COUNTS" 2>/dev/null)"
  compare sqlite "$src" "$dst"
  after="$(sha256sum "$SOURCE_DB" | cut -d' ' -f1)"
  if [ "$before" = "$after" ]; then echo "source database unchanged (sha256 equal)"; else echo "SOURCE DATABASE CHANGED" >&2; FAILED=1; fi
  unset RC_SQLITE_PATH
}

pg_prereqs() {
  command -v docker >/dev/null 2>&1 || { echo "pg path: docker is not installed"; return 1; }
  docker info >/dev/null 2>&1 || { echo "pg path: the Docker daemon is not reachable"; return 1; }
  docker image inspect "$PG_IMAGE" >/dev/null 2>&1 || { echo "pg path: image $PG_IMAGE is not available locally (never pulled here)"; return 1; }
  docker image inspect "$DJANGO_IMAGE" >/dev/null 2>&1 || { echo "pg path: image $DJANGO_IMAGE is not available locally (run scripts/run_tests.sh pg once)"; return 1; }
}

run_pg() {
  [ -f "$SOURCE_DB" ] || { echo "source database not found: $SOURCE_DB" >&2; exit 1; }
  echo "== PostgreSQL path: pg_dump -> psql into an empty database =="
  local suffix pw; suffix="$$-$(date +%s)"; NET="eip-rc-net-$suffix"; PGC="eip-rc-pg-$suffix"
  pw="$(head -c 16 /dev/urandom | od -An -tx1 | tr -d ' \n')"; export POSTGRES_PASSWORD="$pw" RC_PG_PASSWORD="$pw"
  # synthetic demo rows -> fixture (from a read-only COPY of the source, in the temp dir)
  "$PY" -I -c "
import sqlite3,sys
s=sqlite3.connect('file:$SOURCE_DB?mode=ro',uri=True); d=sqlite3.connect('$WORK/fixture-source.sqlite3'); s.backup(d); d.close()"
  RC_SQLITE_PATH="$WORK/fixture-source.sqlite3" dj dumpdata --natural-foreign --natural-primary \
    -e contenttypes -e auth.permission -e sessions -e admin.logentry --output "$WORK/fixture.json"
  docker network create --internal "$NET" >/dev/null
  docker run -d --rm --name "$PGC" --network "$NET" --tmpfs /var/lib/postgresql/data -e POSTGRES_DB=eip_restore_src \
    -e POSTGRES_USER=eip_restore -e POSTGRES_PASSWORD "$PG_IMAGE" >/dev/null
  local i ready=0
  for i in $(seq 1 60); do docker exec "$PGC" pg_isready -U eip_restore -d eip_restore_src >/dev/null 2>&1 && { ready=1; break; }; sleep 1; done
  [ "$ready" = 1 ] || { echo "PostgreSQL did not become ready in 60 s" >&2; exit 1; }
  pdj() {   # manage.py in the local image, source mounted read-only, fixture dir read-only
    local db="$1"; shift
    docker run --rm --network "$NET" -v "$APP:/repo/django_core:ro" -v "$WORK:/rc:ro" -w /repo/django_core \
      -e DJANGO_SETTINGS_MODULE=config.settings.restore_check -e RC_PG_HOST="$PGC" -e RC_PG_NAME="$db" -e RC_PG_PASSWORD \
      "$DJANGO_IMAGE" python -B manage.py "$@"
  }
  psqlc() { docker exec -e PGPASSWORD="$pw" "$PGC" psql -U eip_restore -d "$1" -tAq -c "$2"; }
  pdj eip_restore_src migrate --noinput >/dev/null
  pdj eip_restore_src loaddata /rc/fixture.json
  docker exec -e PGPASSWORD="$pw" "$PGC" pg_dump -U eip_restore -d eip_restore_src > "$WORK/backup.pg.sql"
  echo "backup: $(wc -c < "$WORK/backup.pg.sql") bytes (pg_dump)"
  psqlc postgres "CREATE DATABASE eip_restore_dst"
  docker exec -i -e PGPASSWORD="$pw" "$PGC" psql -U eip_restore -d eip_restore_dst -v ON_ERROR_STOP=1 -q < "$WORK/backup.pg.sql" >/dev/null
  echo "restored into the empty database eip_restore_dst"
  pdj eip_restore_dst check --database default && echo "manage.py check: OK"
  pdj eip_restore_dst migrate --check && echo "manage.py migrate --check: OK (no unapplied migration)"
  local t src="" dst="" orm
  for t in $TABLES; do
    src+="$t $(psqlc eip_restore_src "select count(*) from $t")"$'\n'
    dst+="$t $(psqlc eip_restore_dst "select count(*) from $t")"$'\n'
  done
  orm="$(pdj eip_restore_dst shell -c "$ORM_COUNTS" 2>/dev/null)"
  compare "postgresql, SQL" "$src" "$dst"
  compare "postgresql, ORM on the restored database" "$src" "$orm"
}

case "$MODE" in
  sqlite) run_sqlite ;;
  pg)     pg_prereqs || exit 3; run_pg ;;
  auto)   run_sqlite
          if pg_prereqs; then run_pg; else echo "PostgreSQL path SKIPPED (not verified)"; fi ;;
esac
echo
if [ "$FAILED" = 0 ]; then echo "BACKUP/RESTORE CHECK PASSED"; else echo "BACKUP/RESTORE CHECK FAILED" >&2; exit 1; fi
