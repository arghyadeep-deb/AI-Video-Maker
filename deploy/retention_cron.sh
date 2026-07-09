#!/usr/bin/env bash
# Nightly media retention — resolves open decision #13 (14-day MP4 pruning).
# Invoked by systemd/aivideomaker-retention.timer; safe to run manually too.
set -euo pipefail

APP_DIR="/opt/aivideomaker"
cd "$APP_DIR/backend"

# shellcheck disable=SC1091
source .venv/bin/activate
python scripts/prune_old_renders.py --days "${RETENTION_DAYS:-14}"
