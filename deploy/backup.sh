#!/usr/bin/env bash
# Nightly SQLite snapshot (DB holds consent records too - selfie/voice
# consent timestamps live in the same tables as everything else, no
# separate consent store to back up) to a second free location
# (Cloudflare R2, free 10GB tier) — specs/04-tasks/task-20-deployment.md.
#
# Requires `rclone` configured with a remote named `r2` pointing at an R2
# bucket (one-time setup: `rclone config`, type "Amazon S3", provider
# "Cloudflare" - see docs/RUNBOOK.md's backup section). This script does
# NOT create the R2 bucket or rclone remote itself - that's a one-time,
# owner-authenticated setup step, same class as everything else in this
# task that needs real account credentials.
set -euo pipefail

APP_DIR="/opt/aivideomaker"
DATA_DIR="$APP_DIR/data"
DB_PATH="$DATA_DIR/app.db"
BACKUP_DIR="$DATA_DIR/backups"
DATE_TAG="$(date -u +%Y-%m-%dT%H-%M-%SZ)"
SNAPSHOT_PATH="$BACKUP_DIR/app-$DATE_TAG.db"
LOCAL_RETENTION_DAYS=7
R2_REMOTE="${R2_REMOTE_NAME:-r2}:${R2_BUCKET:-aivideomaker-backups}"

mkdir -p "$BACKUP_DIR"

# `sqlite3 .backup` is safe against a concurrently-open DB (unlike a raw
# `cp`, which can copy a torn write mid-transaction).
sqlite3 "$DB_PATH" ".backup '$SNAPSHOT_PATH'"
gzip -f "$SNAPSHOT_PATH"

# Off-VM copy is best-effort: an unconfigured/unreachable remote must not
# fail the whole backup - the local snapshot above already succeeded, and
# that's the more important half. `set -e` would otherwise abort the script
# here (and skip local retention cleanup below) on the very first night
# rclone isn't set up yet - found live 2026-07-16 when the remote had never
# been configured at all and the service had been silently failing since.
if command -v rclone >/dev/null 2>&1; then
    if ! rclone copy "$SNAPSHOT_PATH.gz" "$R2_REMOTE/db/" --quiet; then
        echo "[backup] rclone copy to $R2_REMOTE failed (remote not configured?) - snapshot kept locally only at $SNAPSHOT_PATH.gz" >&2
    fi
else
    echo "[backup] rclone not found - snapshot kept locally only at $SNAPSHOT_PATH.gz" >&2
fi

# Local retention: keep a week of snapshots on the VM itself as a fast
# fallback even if R2 is unreachable.
find "$BACKUP_DIR" -name "app-*.db.gz" -mtime "+$LOCAL_RETENTION_DAYS" -delete

echo "[backup] snapshot complete: $SNAPSHOT_PATH.gz"
