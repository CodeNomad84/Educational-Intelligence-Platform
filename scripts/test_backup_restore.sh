#!/usr/bin/env bash
# Rehearsal of scripts/backup.sh + scripts/restore_backup.sh (P3 C-K). Synthetic data only, nothing real is touched:
# a throw-away PostgreSQL container with NO network (--network none, data on tmpfs), a throw-away GPG key in a temp keyring,
# backups in a temp folder; everything is removed on exit.
#
#   scripts/test_backup_restore.sh        (PG_IMAGE, default pgvector/pgvector:pg16, must exist locally; never pulled)
#
# Checks: refuses without a public key; encrypted output (a marker string is not readable in it); tiers on a Sunday that is
# also the 1st; exit 4 without off-site and 0 with an rsync off-site copy; rotation keeps N; restore into an empty database
# gives identical row counts and checksums; media restored byte-identical; restore over a non-empty database is refused;
# a tampered file is refused. Exit codes: 0 passed, 1 a check failed, 3 Docker or the image missing.
set -euo pipefail
umask 077

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PG_IMAGE="${PG_IMAGE:-pgvector/pgvector:pg16}"
command -v docker >/dev/null && docker info >/dev/null 2>&1 || { echo "SKIPPED: Docker not available (not verified)" >&2; exit 3; }
docker image inspect "$PG_IMAGE" >/dev/null 2>&1 || { echo "SKIPPED: image $PG_IMAGE missing locally (not verified)" >&2; exit 3; }
command -v gpg >/dev/null && command -v rsync >/dev/null || { echo "SKIPPED: gpg or rsync missing" >&2; exit 3; }

T="$(mktemp -d)"; C="eip-backup-test-$$-$(date +%s)"
cleanup() { docker rm -f "$C" >/dev/null 2>&1 || true; rm -rf "$T"; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
FAIL=0
ok()   { echo "  ok   $1"; }
bad()  { echo "  FAIL $1"; FAIL=1; }
expect_exit() {   # <expected> <label> <command...>
    local want="$1" label="$2"; shift 2
    set +e; "$@" >"$T/last.log" 2>&1; local got=$?; set -e
    [ "$got" = "$want" ] && ok "$label (exit $got)" || { bad "$label: exit $got, expected $want"; sed 's/^/       /' "$T/last.log"; }
}

echo "== setup"
export GNUPGHOME="$T/gnupg"; mkdir -p "$GNUPGHOME"
gpg --batch --quiet --passphrase '' --quick-gen-key "eip backup rehearsal <rehearsal@invalid>" default default never 2>/dev/null
gpg --batch --quiet --export --armor rehearsal@invalid > "$T/backup-public.asc"
docker run -d --name "$C" --network none --tmpfs /var/lib/postgresql/data -e POSTGRES_USER=eip \
    -e POSTGRES_PASSWORD="$(head -c 18 /dev/urandom | base64 | tr -dc A-Za-z0-9)" -e POSTGRES_DB=eip_src "$PG_IMAGE" >/dev/null
for _ in $(seq 60); do docker exec "$C" pg_isready -U eip -d eip_src >/dev/null 2>&1 && break; sleep 1; done
sleep 2; docker exec "$C" pg_isready -U eip -d eip_src >/dev/null
docker exec -i "$C" psql -q -v ON_ERROR_STOP=1 -U eip -d eip_src >/dev/null <<'SQL'
create table person (id int primary key, label text not null);
insert into person select g, 'SYNTHETIC-MARKER-' || g from generate_series(1, 500) g;
create table mark (id serial primary key, person_id int references person(id), value numeric(4,2));
insert into mark (person_id, value) select (g % 500) + 1, (g % 20) from generate_series(1, 2000) g;
SQL
mkdir -p "$T/media/docs"; head -c 4096 /dev/urandom > "$T/media/docs/a.bin"; echo "SYNTHETIC-MARKER-media" > "$T/media/docs/b.txt"
export EIP_PG_CONTAINER="$C" EIP_MEDIA_DIR="$T/media"
B="$ROOT/scripts/backup.sh"; R="$ROOT/scripts/restore_backup.sh"

echo "== backup"
expect_exit 2 "refuses without a public key" env EIP_BACKUP_DIR="$T/b0" "$B"
[ -z "$(find "$T/b0" -name 'eip-*' 2>/dev/null)" ] && ok "nothing written without a key" || bad "files written without a key"
expect_exit 4 "local backup without off-site copy" env EIP_BACKUP_DIR="$T/b" EIP_BACKUP_PUBKEY="$T/backup-public.asc" EIP_BACKUP_DATE=2026-11-01 "$B"
F="$(ls "$T/b/daily/"eip-2026-11-01T*.tar.gpg)"
[ -f "$F" ] && [ -f "$F.sha256" ] && ok "daily file and checksum" || bad "daily file missing"
[ -n "$(ls "$T/b/weekly" | grep -c '\.tar\.gpg$' | grep -x 1)" ] && ok "weekly copy on a Sunday" || bad "weekly copy missing"
[ -n "$(ls "$T/b/monthly" | grep -c '\.tar\.gpg$' | grep -x 1)" ] && ok "monthly copy on the 1st" || bad "monthly copy missing"
grep -aq "SYNTHETIC-MARKER" "$F" && bad "plain text readable in the backup" || ok "encrypted (marker not readable)"
[ "$(stat -c %a "$T/b")" = 700 ] && [ "$(stat -c %a "$F")" = 600 ] && ok "modes 700/600" || bad "modes $(stat -c %a "$T/b")/$(stat -c %a "$F")"
[ -z "$(ls -A "$T/b" | grep '^\.work')" ] && ok "work folder removed" || bad "work folder left behind"
mkdir -p "$T/off"
expect_exit 0 "off-site copy with rsync" env EIP_BACKUP_DIR="$T/b" EIP_BACKUP_PUBKEY="$T/backup-public.asc" EIP_BACKUP_DATE=2026-11-02 EIP_OFFSITE_RSYNC="$T/off/" "$B"
[ "$(find "$T/off" -name 'eip-*.tar.gpg' | wc -l)" -ge 2 ] && ok "encrypted files off-site" || bad "off-site copy missing"
for d in 03 04 05; do env EIP_BACKUP_DIR="$T/b" EIP_BACKUP_PUBKEY="$T/backup-public.asc" EIP_BACKUP_DATE=2026-11-$d EIP_KEEP_DAILY=2 "$B" >/dev/null 2>&1 || true; done
[ "$(ls "$T/b/daily" | grep -c '\.tar\.gpg$')" = 2 ] && ls "$T/b/daily" | grep -q '2026-11-05' && ok "rotation keeps the newest 2" \
    || bad "rotation: $(ls "$T/b/daily" | tr '\n' ' ')"
[ "$(ls "$T/b/monthly" | grep -c '\.tar\.gpg$')" = 1 ] && ok "rotation leaves the monthly copy" || bad "monthly copy rotated away"

echo "== restore"
F="$T/b/monthly/$(basename "$F")"     # the daily copy was rotated away above; the monthly hard link remains
[ -f "$F" ] && [ -f "$F.sha256" ] || bad "monthly copy to restore from is missing"
docker exec "$C" createdb -U eip eip_dst
expect_exit 0 "restore into an empty database" "$R" "$F" eip_dst "$T/media_restored"
q() { docker exec "$C" psql -U eip -d "$1" -tAc "$2"; }
for sql in "select count(*) from person" "select count(*) from mark" "select md5(string_agg(label, ',' order by id)) from person" \
           "select sum(value) from mark"; do
    [ "$(q eip_src "$sql")" = "$(q eip_dst "$sql")" ] && ok "same: $sql" || bad "differs: $sql"
done
diff -r "$T/media" "$T/media_restored" >/dev/null && ok "media byte-identical" || bad "media differs"
expect_exit 2 "refuses a non-empty database" "$R" "$F" eip_dst
docker exec "$C" createdb -U eip eip_dst2
cp "$F" "$T/tampered.tar.gpg"; printf '\x00' | dd of="$T/tampered.tar.gpg" bs=1 seek=200 conv=notrunc 2>/dev/null
expect_exit 1 "refuses a tampered file" "$R" "$T/tampered.tar.gpg" eip_dst2
[ "$(q eip_dst2 "select count(*) from information_schema.tables where table_schema='public'")" = 0 ] && ok "nothing restored from the tampered file" \
    || bad "tampered file restored tables"

[ "$FAIL" = 0 ] && echo "BACKUP/RESTORE REHEARSAL PASSED" || { echo "BACKUP/RESTORE REHEARSAL FAILED"; exit 1; }
