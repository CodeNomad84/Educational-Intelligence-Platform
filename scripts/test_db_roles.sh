#!/usr/bin/env bash
# Rehearsal of the R-04 least-privilege roles (P9). Synthetic only, nothing real is touched: throw-away PostgreSQL containers with NO
# network, data on tmpfs, random passwords, removed on exit.  Checks:
#   fresh install  deploy/postgres/10-roles.sh run by the image's own init mechanism; the roles are not superusers; school_app does DML but
#                  cannot CREATE/ALTER/DROP/TRUNCATE, create roles or extensions, read pg_authid; PUBLIC cannot create in the schema;
#                  tables created LATER by school_owner are usable by school_app (default privileges); weak/equal passwords are refused.
#   conversion     an existing database used by a superuser (school_user) is converted with deploy/postgres-maintenance/r04-convert-existing.sql; data
#                  survives, ownership moves, the same privilege checks hold.
#   django         (only if the image eip-test-django:local exists) `migrate` as school_owner, then a DML smoke and a refused DDL as school_app.
#   scripts/test_db_roles.sh      (PG_IMAGE default pgvector/pgvector:pg16, never pulled).  Exit 0 passed, 1 failed, 3 Docker/image missing.
set -euo pipefail
umask 077
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PG_IMAGE="${PG_IMAGE:-pgvector/pgvector:pg16}"
command -v docker >/dev/null && docker info >/dev/null 2>&1 || { echo "SKIPPED: Docker not available (not verified)" >&2; exit 3; }
docker image inspect "$PG_IMAGE" >/dev/null 2>&1 || { echo "SKIPPED: image $PG_IMAGE missing locally (not verified)" >&2; exit 3; }
STAMP="$$-$(date +%s)"; C1="eip-roles-fresh-$STAMP"; C2="eip-roles-conv-$STAMP"; C3="eip-roles-weak-$STAMP"; NET="eip-roles-net-$STAMP"
cleanup() { docker rm -f "$C1" "$C2" "$C3" >/dev/null 2>&1 || true; docker network rm "$NET" >/dev/null 2>&1 || true; }
trap cleanup EXIT; trap 'exit 130' INT; trap 'exit 143' TERM
FAIL=0; ok() { echo "  ok   $1"; }; bad() { echo "  FAIL $1"; FAIL=1; }
pw() { head -c 24 /dev/urandom | base64 | tr -dc A-Za-z0-9 | head -c 24; }
ADMIN_PW="$(pw)"; OWNER_PW="$(pw)"; APP_PW="$(pw)"; OLD_PW="$(pw)"
docker network create --internal "$NET" >/dev/null

start() {   # <name> <extra docker args...>
    local name="$1"; shift
    docker run -d --name "$name" --network "$NET" --tmpfs /var/lib/postgresql/data "$@" "$PG_IMAGE" >/dev/null
    for _ in $(seq 90); do docker exec "$name" pg_isready -q >/dev/null 2>&1 && break; sleep 1; done; sleep 3
    docker exec "$name" pg_isready -q
}
sql() {     # <container> <user> <db> <sql> -> prints output, nonzero exit on error
    docker exec -i -e PGPASSWORD="$PGPW" "$1" psql -X -q -t -A -v ON_ERROR_STOP=1 -h 127.0.0.1 -U "$2" -d "$3" -c "$4"
}
allowed()  { local out; if out="$(sql "$@" 2>&1)"; then ok "$LABEL"; else bad "$LABEL: refused: $out"; fi; }
refused()  { local out; if out="$(sql "$@" 2>&1)"; then bad "$LABEL: was allowed"; else ok "$LABEL (refused)"; fi; }
checks() {  # <container> <db>
    local c="$1" db="$2"
    PGPW="$OWNER_PW" LABEL="owner can create a table"            allowed "$c" school_owner "$db" "create table zz_owner (id serial primary key, v text); insert into zz_owner(v) values ('x');"
    PGPW="$APP_PW"   LABEL="app can read, insert, update, delete" allowed "$c" school_app "$db" "insert into zz_owner(v) values ('y'); update zz_owner set v='z'; select count(*) from zz_owner; delete from zz_owner where v='z';"
    PGPW="$APP_PW"   LABEL="app cannot create a table"           refused "$c" school_app "$db" "create table zz_app (i int);"
    PGPW="$APP_PW"   LABEL="app cannot alter a table"            refused "$c" school_app "$db" "alter table zz_owner add column w int;"
    PGPW="$APP_PW"   LABEL="app cannot drop a table"             refused "$c" school_app "$db" "drop table zz_owner;"
    PGPW="$APP_PW"   LABEL="app cannot truncate"                 refused "$c" school_app "$db" "truncate zz_owner;"
    PGPW="$APP_PW"   LABEL="app cannot create a role"            refused "$c" school_app "$db" "create role zz_evil login;"
    PGPW="$APP_PW"   LABEL="app cannot create an extension"      refused "$c" school_app "$db" "create extension pg_trgm;"
    PGPW="$APP_PW"   LABEL="app cannot read pg_authid"           refused "$c" school_app "$db" "select rolpassword from pg_authid;"
    PGPW="$APP_PW"   LABEL="app cannot alter itself to superuser" refused "$c" school_app "$db" "alter role school_app superuser;"
    PGPW="$OWNER_PW" LABEL="owner cannot create a role"          refused "$c" school_owner "$db" "create role zz_evil2 login;"
    PGPW="$OWNER_PW" LABEL="owner cannot read pg_authid"         refused "$c" school_owner "$db" "select rolpassword from pg_authid;"
    local flags; flags="$(PGPW="$OWNER_PW" sql "$c" school_owner "$db" "select string_agg(rolname || ':' || rolsuper::text || rolcreatedb::text || rolcreaterole::text || rolbypassrls::text, ',' order by rolname) from pg_roles where rolname in ('school_owner','school_app');")"
    [ "$flags" = "school_app:falsefalsefalsefalse,school_owner:falsefalsefalsefalse" ] && ok "neither role is superuser/createdb/createrole/bypassrls" || bad "role flags: $flags"
    local pub; pub="$(PGPW="$OWNER_PW" sql "$c" school_owner "$db" "select has_schema_privilege('public','public','CREATE')::text;")"
    [ "$pub" = "false" ] && ok "PUBLIC cannot create in schema public" || bad "PUBLIC can create in public"
}

echo "== fresh install (the image's own init mechanism runs deploy/postgres/10-roles.sh)"
start "$C1" -e POSTGRES_USER=school_admin -e POSTGRES_PASSWORD="$ADMIN_PW" -e POSTGRES_DB=eip_test_roles \
    -e DB_OWNER_PASSWORD="$OWNER_PW" -e DB_APP_PASSWORD="$APP_PW" -v "$ROOT/deploy/postgres:/docker-entrypoint-initdb.d:ro"
checks "$C1" eip_test_roles
PGPW="$ADMIN_PW" LABEL="the bootstrap role stays a superuser (maintenance only)" allowed "$C1" school_admin eip_test_roles "select 1 where (select rolsuper from pg_roles where rolname='school_admin');"

echo "== weak or equal role passwords are refused at initialisation"
if docker run --rm --network none -e POSTGRES_USER=a -e POSTGRES_DB=d -e DB_OWNER_PASSWORD=short -e DB_APP_PASSWORD=short2 --entrypoint bash \
     -v "$ROOT/deploy/postgres:/s:ro" "$PG_IMAGE" -c 'bash /s/10-roles.sh' >/dev/null 2>&1; then bad "short passwords accepted"; else ok "short passwords refused"; fi
SAME="$(pw)$(pw)"
if docker run --rm --network none -e POSTGRES_USER=a -e POSTGRES_DB=d -e DB_OWNER_PASSWORD="$SAME" -e DB_APP_PASSWORD="$SAME" --entrypoint bash \
     -v "$ROOT/deploy/postgres:/s:ro" "$PG_IMAGE" -c 'bash /s/10-roles.sh' >/dev/null 2>&1; then bad "equal passwords accepted"; else ok "equal passwords refused"; fi

echo "== conversion of an existing superuser-owned database"
start "$C2" -e POSTGRES_USER=school_user -e POSTGRES_PASSWORD="$OLD_PW" -e POSTGRES_DB=eip_test_roles
PGPW="$OLD_PW" LABEL="legacy database prepared" allowed "$C2" school_user eip_test_roles "create table legacy (id serial primary key, label text); insert into legacy(label) select 'SYNTHETIC-'||g from generate_series(1,50) g;"
docker exec -i -e PGPASSWORD="$OLD_PW" "$C2" psql -X -q -v ON_ERROR_STOP=1 -h 127.0.0.1 -U school_user -d eip_test_roles \
    -v owner_pw="$OWNER_PW" -v app_pw="$APP_PW" -v old_role=school_user < "$ROOT/deploy/postgres-maintenance/r04-convert-existing.sql" >/dev/null && ok "conversion script ran" || bad "conversion script failed"
PGPW="$APP_PW" LABEL="after conversion the app role reads the legacy rows" allowed "$C2" school_app eip_test_roles "select 1 where (select count(*) from legacy)=50;"
PGPW="$APP_PW" LABEL="after conversion the app role writes the legacy table" allowed "$C2" school_app eip_test_roles "insert into legacy(label) values ('new');"
owner="$(PGPW="$OWNER_PW" sql "$C2" school_owner eip_test_roles "select tableowner from pg_tables where tablename='legacy';")"
[ "$owner" = "school_owner" ] && ok "legacy table now owned by school_owner" || bad "legacy owner is $owner"
checks "$C2" eip_test_roles

echo "== Django: migrate as owner, DML as app, DDL refused (needs the image eip-test-django:local)"
if docker image inspect eip-test-django:local >/dev/null 2>&1; then
    run_dj() {   # <user> <password> <python code or manage args...>
        local user="$1" pass="$2"; shift 2
        docker run --rm --network "$NET" -e TEST_PG_HOST="$C1" -e TEST_PG_USER="$user" -e TEST_PG_PASSWORD="$pass" -e TEST_PG_NAME=eip_test_roles \
            -e DJANGO_SETTINGS_MODULE=config.settings.test_postgres -v "$ROOT/django_core:/app:ro" -w /app eip-test-django:local "$@"
    }
    if run_dj school_owner "$OWNER_PW" python manage.py migrate --noinput >/dev/null 2>&1; then ok "migrate as school_owner"; else bad "migrate as school_owner failed"; fi
    if run_dj school_app "$APP_PW" python manage.py shell -c "from schools.models import School; School.objects.create(name='Rehearsal', code='rehearsal'); assert School.objects.filter(code='rehearsal').exists()" >/dev/null 2>&1; then ok "Django DML as school_app"; else bad "Django DML as school_app failed"; fi
    if run_dj school_app "$APP_PW" python manage.py shell -c "from django.db import connection; connection.cursor().execute('create table zz_django (i int)')" >/dev/null 2>&1; then bad "Django DDL as school_app was allowed"; else ok "Django DDL as school_app refused"; fi
else
    echo "  SKIPPED (not verified): image eip-test-django:local not built (scripts/run_tests.sh builds it)"
fi
echo
[ "$FAIL" = 0 ] && { echo "R-04 roles rehearsal: PASSED"; exit 0; } || { echo "R-04 roles rehearsal: FAILED"; exit 1; }
