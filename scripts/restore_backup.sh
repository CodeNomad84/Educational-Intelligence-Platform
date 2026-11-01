#!/usr/bin/env bash
# Restore one backup made by scripts/backup.sh into an EMPTY database (P3 C-K; RUNBOOK §3). Run it on the machine that holds
# the PRIVATE key (it is never on the production server), or on the server after copying the key in for the restore only.
#
#   scripts/restore_backup.sh <file.tar.gpg> <target database> [<media target folder>]
#
#   EIP_PG_CONTAINER   restore through `docker exec <container>` as the container's POSTGRES_USER (default postgres_db);
#                      empty = local pg_restore/psql with the standard PG* variables.
#   GNUPGHOME          keyring that holds the private key (gpg asks for its passphrase).
#
# Steps: checksum file (if next to the backup) > decrypt into a mode-700 temp folder > MANIFEST checksums > the target
# database must exist and contain NO tables (it is never overwritten) > pg_restore --no-owner --exit-on-error > media
# extracted only into an EMPTY or new folder. Then run `manage.py migrate --check` and `manage.py check` against it.
# Exit codes: 0 restored, 1 failure, 2 usage or refusal.
set -euo pipefail
umask 077

[ "$#" -ge 2 ] && [ "$#" -le 3 ] || { echo "usage: scripts/restore_backup.sh <file.tar.gpg> <target database> [<media folder>]" >&2; exit 2; }
FILE="$1"; TARGET="$2"; MEDIA_TARGET="${3:-}"
CONTAINER="${EIP_PG_CONTAINER-postgres_db}"
die() { echo "restore: $1" >&2; exit "${2:-1}"; }

[ -r "$FILE" ] || die "cannot read $FILE" 2
[[ "$TARGET" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]] || die "target database name must be a plain identifier" 2
if [ -f "$FILE.sha256" ]; then
    (cd "$(dirname "$FILE")" && sha256sum --quiet -c "$(basename "$FILE").sha256") || die "checksum of the encrypted file does not match"
else
    echo "restore: no .sha256 next to the file; continuing with the inner MANIFEST checks only" >&2
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
gpg --batch --quiet --decrypt "$FILE" | tar -C "$WORK" -xf - || die "decryption failed (is the private key in GNUPGHOME?)"
[ -f "$WORK/MANIFEST" ] && [ -f "$WORK/db.dump" ] || die "not a backup made by scripts/backup.sh"
while read -r kind sum size name; do
    [ "$kind" = sha256 ] || continue
    [ "$(sha256sum "$WORK/$name" | cut -d' ' -f1)" = "$sum" ] || die "MANIFEST checksum mismatch for $name"
done < "$WORK/MANIFEST"
echo "restore: $(grep '^created_utc=' "$WORK/MANIFEST") verified"

psql_target() {   # SQL on the target database, one value out
    if [ -n "$CONTAINER" ]; then docker exec -i "$CONTAINER" sh -c "psql -v ON_ERROR_STOP=1 -U \"\$POSTGRES_USER\" -d $TARGET -tA"
    else psql -v ON_ERROR_STOP=1 -d "$TARGET" -tA; fi
}
TABLES="$(echo "select count(*) from information_schema.tables where table_schema not in ('pg_catalog','information_schema');" | psql_target)" \
    || die "target database $TARGET does not exist or is not reachable; create it empty first" 2
[ "$TABLES" = 0 ] || die "target database $TARGET is not empty ($TABLES tables); refusing to restore over data" 2

if [ -n "$CONTAINER" ]; then
    docker exec -i "$CONTAINER" sh -c "pg_restore --no-owner --exit-on-error -U \"\$POSTGRES_USER\" -d $TARGET" < "$WORK/db.dump" \
        || die "pg_restore failed"
else
    pg_restore --no-owner --exit-on-error -d "$TARGET" "$WORK/db.dump" || die "pg_restore failed"
fi
echo "restore: database $TARGET restored"

if [ -n "$MEDIA_TARGET" ]; then
    if [ -f "$WORK/media.tar" ]; then
        mkdir -p "$MEDIA_TARGET"
        [ -z "$(ls -A "$MEDIA_TARGET")" ] || die "media folder $MEDIA_TARGET is not empty; refusing to overwrite" 2
        tar -C "$MEDIA_TARGET" -xf "$WORK/media.tar" || die "media extraction failed"
        echo "restore: media extracted into $MEDIA_TARGET"
    else
        echo "restore: the backup has no media archive" >&2
    fi
fi
