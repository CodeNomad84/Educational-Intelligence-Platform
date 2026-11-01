#!/usr/bin/env bash
# Encrypted, rotated backup of the PostgreSQL database and the media folder (P3 C-K; decision pack 0028 P3-2; RUNBOOK §3).
# Provider-agnostic: pg_dump, tar, gpg, and optionally rsync or rclone. Meant for cron/systemd once per night.
#
#   scripts/backup.sh
#
# Configuration (environment; nothing secret is read by this script):
#   EIP_BACKUP_DIR        where encrypted backups live (default /var/backups/eip; refused inside the repository)
#   EIP_BACKUP_PUBKEY     REQUIRED: a GPG PUBLIC key file. The private key is never on this server (owner + deputy, offline),
#                         so a stolen server or backup disk does not reveal the data. Without it nothing is written.
#   EIP_PG_CONTAINER      dump through `docker exec <container>` using the container's own POSTGRES_USER/POSTGRES_DB
#                         (default postgres_db, the docker-compose name). Set EIP_PG_CONTAINER= (empty) to use a local
#                         pg_dump with the standard PGHOST/PGUSER/PGDATABASE/PGPASSFILE variables instead.
#   EIP_MEDIA_DIR         folder archived next to the dump (default <repo>/data/media; skipped if missing)
#   EIP_KEEP_DAILY / EIP_KEEP_WEEKLY / EIP_KEEP_MONTHLY   copies kept per tier (default 14 / 8 / 12)
#   EIP_OFFSITE_RSYNC     optional rsync target, e.g. backup@host.example:/srv/eip-backups/ (SSH key auth)
#   EIP_OFFSITE_RCLONE    optional rclone target, e.g. offsite:eip-backups (any S3-compatible storage or SFTP)
#   EIP_BACKUP_DATE       YYYY-MM-DD used for the name and the tier (default: today, UTC); for rehearsals
#
# Result: <dir>/daily/eip-<date>T<time>Z.tar.gpg (+ .sha256). Sundays are also kept in weekly/, the 1st of a month in
# monthly/ (hard links, no extra space). Inside the encrypted archive: db.dump (pg_dump custom format), media.tar (if any),
# MANIFEST (sha256 of each part, sizes, time). Plain parts exist only in a mode-700 work folder that is removed on exit.
# Exit codes: 0 done incl. off-site copy, 1 failure, 2 configuration error, 4 written locally but NO off-site copy (configure
# EIP_OFFSITE_*; a monitor should treat 4 as a warning).
set -euo pipefail
umask 077

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIR="${EIP_BACKUP_DIR:-/var/backups/eip}"
PUBKEY="${EIP_BACKUP_PUBKEY:-}"
CONTAINER="${EIP_PG_CONTAINER-postgres_db}"
MEDIA="${EIP_MEDIA_DIR:-$ROOT/data/media}"
KEEP_DAILY="${EIP_KEEP_DAILY:-14}"; KEEP_WEEKLY="${EIP_KEEP_WEEKLY:-8}"; KEEP_MONTHLY="${EIP_KEEP_MONTHLY:-12}"
DAY="${EIP_BACKUP_DATE:-$(date -u +%F)}"

die() { echo "backup: $1" >&2; exit "${2:-1}"; }

[ -n "$PUBKEY" ] || die "EIP_BACKUP_PUBKEY is not set: refusing to write an unencrypted backup" 2
[ -r "$PUBKEY" ] || die "public key file not readable: $PUBKEY" 2
[[ "$DAY" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] && date -u -d "$DAY" >/dev/null 2>&1 || die "EIP_BACKUP_DATE must be YYYY-MM-DD" 2
for n in "$KEEP_DAILY" "$KEEP_WEEKLY" "$KEEP_MONTHLY"; do [[ "$n" =~ ^[1-9][0-9]*$ ]] || die "EIP_KEEP_* must be positive integers" 2; done
command -v gpg >/dev/null || die "gpg is not installed" 2
mkdir -p "$DIR"
DIR="$(cd "$DIR" && pwd)"
case "$DIR/" in
    "$ROOT"/*) git -C "$ROOT" check-ignore -q "$DIR" || die "EIP_BACKUP_DIR is inside the repository and not git-ignored" 2 ;;
esac
chmod 700 "$DIR"; mkdir -p "$DIR/daily" "$DIR/weekly" "$DIR/monthly"

WORK="$(mktemp -d "$DIR/.work.XXXXXX")"
GNUPG_TMP="$(mktemp -d)"
cleanup() { rm -rf "$WORK" "$GNUPG_TMP"; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# 1. Dump (custom format: compressed, restorable table by table).
if [ -n "$CONTAINER" ]; then
    docker exec "$CONTAINER" sh -c 'pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB"' > "$WORK/db.dump" \
        || die "pg_dump through container $CONTAINER failed"
else
    pg_dump -Fc > "$WORK/db.dump" || die "local pg_dump failed"
fi
[ -s "$WORK/db.dump" ] || die "the dump is empty"

# 2. Media (uploaded documents), if present.
if [ -d "$MEDIA" ]; then
    tar -C "$MEDIA" -cf "$WORK/media.tar" . || die "archiving $MEDIA failed"
fi

# 3. Manifest: no content, only checksums, sizes and time.
STAMP="${DAY}T$(date -u +%H%M%S)Z"
{
    echo "created_utc=$STAMP"
    echo "commit=$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)"
    (cd "$WORK" && for f in db.dump media.tar; do [ -f "$f" ] && echo "sha256 $(sha256sum "$f" | cut -d' ' -f1) $(stat -c %s "$f") $f"; done; true)
} > "$WORK/MANIFEST"

# 4. Encrypt to the public key only (a throw-away keyring: nothing is imported into the operator's keyring).
NAME="eip-$STAMP.tar.gpg"
OUT="$DIR/daily/$NAME"
tar -C "$WORK" -cf - MANIFEST db.dump $( [ -f "$WORK/media.tar" ] && echo media.tar ) \
    | GNUPGHOME="$GNUPG_TMP" gpg --batch --quiet --no-tty --trust-model always --recipient-file "$PUBKEY" \
          --cipher-algo AES256 --compress-algo none --output "$OUT.part" --encrypt \
    || die "encryption failed"
mv "$OUT.part" "$OUT"
(cd "$DIR/daily" && sha256sum "$NAME" > "$NAME.sha256")

# 5. Tiers (hard links) and rotation: keep the newest N files of each tier.
[ "$(date -u -d "$DAY" +%u)" = 7 ] && ln -f "$OUT" "$DIR/weekly/$NAME" && ln -f "$OUT.sha256" "$DIR/weekly/$NAME.sha256"
[ "$(date -u -d "$DAY" +%d)" = 01 ] && ln -f "$OUT" "$DIR/monthly/$NAME" && ln -f "$OUT.sha256" "$DIR/monthly/$NAME.sha256"
rotate() {   # <folder> <keep>
    local f
    ls -1 "$1" | grep -E '^eip-.*\.tar\.gpg$' | sort -r | tail -n +"$(( $2 + 1 ))" | while read -r f; do
        rm -f "$1/$f" "$1/$f.sha256"
    done
}
rotate "$DIR/daily" "$KEEP_DAILY"; rotate "$DIR/weekly" "$KEEP_WEEKLY"; rotate "$DIR/monthly" "$KEEP_MONTHLY"

echo "backup: $OUT ($(stat -c %s "$OUT") bytes, encrypted)"

# 6. Off-site copy (only encrypted files leave the server). ADD-ONLY on purpose: nothing is ever deleted off-site from here, so
#    a compromised server cannot wipe the off-site copies. Expire them on the receiving side (object-storage lifecycle rule
#    or a cleanup job there), e.g. after 400 days.
OFFSITE=0
if [ -n "${EIP_OFFSITE_RSYNC:-}" ]; then
    rsync -a --include='*/' --include='eip-*.tar.gpg' --include='eip-*.tar.gpg.sha256' --exclude='*' \
        "$DIR/" "$EIP_OFFSITE_RSYNC" || die "off-site rsync failed (the local backup is fine)"
    OFFSITE=1; echo "backup: copied off-site with rsync"
fi
if [ -n "${EIP_OFFSITE_RCLONE:-}" ]; then
    command -v rclone >/dev/null || die "EIP_OFFSITE_RCLONE is set but rclone is not installed" 2
    rclone copy "$DIR" "$EIP_OFFSITE_RCLONE" --include '/daily/eip-*' --include '/weekly/eip-*' --include '/monthly/eip-*' \
        || die "off-site rclone failed (the local backup is fine)"
    OFFSITE=1; echo "backup: copied off-site with rclone"
fi
if [ "$OFFSITE" = 0 ]; then
    echo "backup: WARNING no off-site copy (set EIP_OFFSITE_RSYNC or EIP_OFFSITE_RCLONE); the backup is on this server only" >&2
    exit 4
fi
