#!/usr/bin/env bash
# Nightly encrypted backup of what git can't restore: the SQLite databases (through SQLite's backup
# API, so a write mid-copy can't corrupt them), .env files, the admin's JSON and uploads. One copy
# stays on the server; with BACKUP_REMOTE set, rclone keeps 30 days off it. Setup and restore are
# in the README under "Backups".
set -euo pipefail
umask 077

SITE_DIR=${SITE_DIR:-/home/jzay/personal_website}
BACKUP_DIR=${BACKUP_DIR:-/home/jzay/personal_website_data/backups}
PASSPHRASE_FILE=${PASSPHRASE_FILE:-/home/jzay/.config/site-backup/passphrase}
BACKUP_REMOTE=${BACKUP_REMOTE-r2:jeremyzay-backups/site}
KEEP_LOCAL_DAYS=${KEEP_LOCAL_DAYS:-7}
KEEP_REMOTE_DAYS=${KEEP_REMOTE_DAYS:-30}

STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$BACKUP_DIR" "$STAGE/instance"

python3 - "$SITE_DIR/instance" "$STAGE/instance" <<'PY'
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

source_dir, target_dir = map(Path, sys.argv[1:])
for path in source_dir.glob("*.sqlite3"):
    with closing(sqlite3.connect(path)) as source, closing(sqlite3.connect(target_dir / path.name)) as target:
        source.backup(target)
PY

# Paths a fresh server doesn't have yet are skipped.
PATHS=()
for path in .env app/data/portfolio.json app/data/site_settings.json \
            app/static/files app/static/game app/static/img/posters app/static/img/uploads \
            app/static/video app/static/zaychess \
            projects/ear/.env projects/attack_target_network/.env.deltalab; do
  if [ -e "$SITE_DIR/$path" ]; then PATHS+=("$path"); fi
done

ARCHIVE="$BACKUP_DIR/site-$(date -u +%Y%m%dT%H%M%SZ).tar.gz.gpg"
tar -czf - -C "$STAGE" instance -C "$SITE_DIR" "${PATHS[@]}" \
  | gpg --batch --yes --pinentry-mode loopback --passphrase-file "$PASSPHRASE_FILE" \
        --symmetric --cipher-algo AES256 --output "$ARCHIVE"
find "$BACKUP_DIR" -name 'site-*.tar.gz.gpg' -mtime "+$KEEP_LOCAL_DAYS" -delete

if [ -n "$BACKUP_REMOTE" ]; then
  rclone copy "$ARCHIVE" "$BACKUP_REMOTE"
  rclone delete --min-age "${KEEP_REMOTE_DAYS}d" "$BACKUP_REMOTE"
fi
echo "Backed up to $ARCHIVE"
