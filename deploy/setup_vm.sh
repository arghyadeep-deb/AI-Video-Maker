#!/usr/bin/env bash
# Idempotent provisioning for the Oracle Always Free ARM VM (Ubuntu, aarch64).
# specs/04-tasks/task-20-deployment.md, specs/02-research/08-free-hosting.md.
#
# Safe to re-run: every step checks whether it's already done before acting.
# Run as a user with sudo (not necessarily root):
#   curl -fsSL https://raw.githubusercontent.com/<owner>/<repo>/main/deploy/setup_vm.sh | bash
# or, after cloning the repo onto the VM directly:
#   bash deploy/setup_vm.sh
#
# This script does NOT create the Oracle VM itself, register a domain, or
# create the systemd service's actual secrets file (deploy/.env) - those
# are one-time, credential-requiring steps documented in docs/RUNBOOK.md.
set -euo pipefail

APP_DIR="/opt/aivideomaker"
APP_USER="aivideomaker"
REPO_URL="${AIVIDEOMAKER_REPO_URL:-}"  # set this env var before running, or clone manually first

log() { echo "[setup_vm] $*"; }

# --- 1. System packages -----------------------------------------------------

log "Installing system packages..."
sudo apt-get update -y
sudo apt-get install -y \
    python3 python3-venv python3-pip \
    ffmpeg \
    fonts-noto-core fonts-noto-cjk \
    sqlite3 \
    git curl gzip \
    rclone

# Devanagari specifically - fonts-noto-core doesn't always include it on
# older Ubuntu package sets, so pull it explicitly too (idempotent, apt
# no-ops if already satisfied by fonts-noto-core on newer releases).
sudo apt-get install -y fonts-noto-devanagari || true

# Caddy: not in default apt repos, needs its own key+repo (one-time, idempotent).
if ! command -v caddy >/dev/null 2>&1; then
    log "Installing Caddy..."
    sudo apt-get install -y debian-keyring debian-archive-keyring apt-transport-https
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
        | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
        | sudo tee /etc/apt/sources.list.d/caddy-stable.list
    sudo apt-get update -y
    sudo apt-get install -y caddy
else
    log "Caddy already installed, skipping."
fi

# --- 2. App user + directories ----------------------------------------------

if ! id "$APP_USER" >/dev/null 2>&1; then
    log "Creating system user $APP_USER..."
    sudo useradd --system --create-home --shell /usr/sbin/nologin "$APP_USER"
else
    log "User $APP_USER already exists, skipping."
fi

sudo mkdir -p "$APP_DIR" "$APP_DIR/data" "$APP_DIR/data/media" "$APP_DIR/data/backups"

# --- 3. Application code -----------------------------------------------------

if [ ! -d "$APP_DIR/.git" ]; then
    if [ -z "$REPO_URL" ]; then
        log "ERROR: $APP_DIR has no code yet and AIVIDEOMAKER_REPO_URL isn't set."
        log "Either 'export AIVIDEOMAKER_REPO_URL=https://github.com/<you>/<repo>.git' and re-run,"
        log "or clone/rsync the repo into $APP_DIR yourself before running this script."
        exit 1
    fi
    log "Cloning $REPO_URL into $APP_DIR..."
    sudo git clone "$REPO_URL" "$APP_DIR"
else
    log "Repo already present at $APP_DIR, pulling latest..."
    sudo -u "$APP_USER" git -C "$APP_DIR" pull --ff-only
fi

sudo chown -R "$APP_USER:$APP_USER" "$APP_DIR"

# --- 4. Backend Python environment -------------------------------------------

log "Setting up backend virtualenv..."
sudo -u "$APP_USER" python3 -m venv "$APP_DIR/backend/.venv"
sudo -u "$APP_USER" "$APP_DIR/backend/.venv/bin/pip" install --upgrade pip
sudo -u "$APP_USER" "$APP_DIR/backend/.venv/bin/pip" install -r "$APP_DIR/backend/requirements.txt"

log "Fetching model weights (Wav2Lip, OpenVoice converter - idempotent, sha256-verified)..."
sudo -u "$APP_USER" "$APP_DIR/backend/.venv/bin/python" "$APP_DIR/backend/scripts/setup_models.py"

# --- 5. Secrets file (must exist before the service can start) --------------

ENV_FILE="$APP_DIR/deploy/.env"
if [ ! -f "$ENV_FILE" ]; then
    log "No $ENV_FILE yet - creating a template. Fill in real values before starting the service."
    sudo -u "$APP_USER" tee "$ENV_FILE" >/dev/null <<'EOF'
# Real values only - this file is gitignored and lives only on the VM.
GEMINI_API_KEY=
PEXELS_API_KEY=
PIXABAY_API_KEY=
DB_PATH=/opt/aivideomaker/data/app.db
MEDIA_ROOT=/opt/aivideomaker/data/media
FRONTEND_ORIGIN=https://your-frontend.vercel.app
JWT_SECRET=
RETENTION_DAYS=14
EOF
    log "Edit $ENV_FILE now (JWT_SECRET especially - generate with: python3 -c 'import secrets; print(secrets.token_hex(32))'), then re-run this script."
    exit 1
fi

# --- 6. systemd units --------------------------------------------------------

log "Installing systemd units..."
sudo cp "$APP_DIR"/deploy/systemd/aivideomaker-*.service /etc/systemd/system/
sudo cp "$APP_DIR"/deploy/systemd/aivideomaker-*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now aivideomaker-api.service
sudo systemctl enable --now aivideomaker-retention.timer
sudo systemctl enable --now aivideomaker-backup.timer

# --- 7. Caddy ----------------------------------------------------------------

log "Installing Caddyfile..."
sudo cp "$APP_DIR/deploy/Caddyfile" /etc/caddy/Caddyfile
sudo systemctl reload caddy || sudo systemctl restart caddy

log "Done. Check status with: sudo systemctl status aivideomaker-api"
log "Logs: sudo journalctl -u aivideomaker-api -f"
