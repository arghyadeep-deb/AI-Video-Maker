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

# --- 3. Application code -----------------------------------------------------
# NOTE: directories under $APP_DIR are created *after* the clone (below) -
# `git clone` refuses to clone into a non-empty directory, so $APP_DIR must
# stay untouched (or not yet exist) until the repo is checked out.

if [ ! -d "$APP_DIR/.git" ]; then
    if [ -z "$REPO_URL" ]; then
        log "ERROR: $APP_DIR has no code yet and AIVIDEOMAKER_REPO_URL isn't set."
        log "Either 'export AIVIDEOMAKER_REPO_URL=https://github.com/<you>/<repo>.git' and re-run,"
        log "or clone/rsync the repo into $APP_DIR yourself before running this script."
        exit 1
    fi
    log "Cloning $REPO_URL into $APP_DIR..."
    sudo mkdir -p "$APP_DIR"
    sudo git clone "$REPO_URL" "$APP_DIR"
    sudo chown -R "$APP_USER:$APP_USER" "$APP_DIR"
else
    log "Repo already present at $APP_DIR, pulling latest..."
    # chown first - git refuses to operate as $APP_USER on a repo it doesn't
    # own ("detected dubious ownership"), which bites on the very first re-run
    # if the initial clone above ran as root (e.g. a manual clone before this
    # script's first pass ever completed).
    sudo chown -R "$APP_USER:$APP_USER" "$APP_DIR"
    sudo -u "$APP_USER" git -C "$APP_DIR" pull --ff-only
fi

sudo mkdir -p "$APP_DIR/data" "$APP_DIR/data/media" "$APP_DIR/data/backups"
sudo chown -R "$APP_USER:$APP_USER" "$APP_DIR"

# --- 4. Backend Python environment -------------------------------------------

log "Setting up backend virtualenv..."
sudo -u "$APP_USER" python3 -m venv "$APP_DIR/backend/.venv"
sudo -u "$APP_USER" "$APP_DIR/backend/.venv/bin/pip" install --upgrade pip

# CPU-only torch/torchvision first: this VM has no GPU (GPU inference lives
# entirely on the owner's home worker, task-20a) - the backend only needs
# torch for OpenVoice's CPU-floor voice conversion. Installing these before
# requirements.txt keeps pip from pulling PyPI's default CUDA build (multiple
# GB of nvidia-*/cuda-toolkit wheels that would never be used and can take
# a very long time on a small free-tier instance).
sudo -u "$APP_USER" "$APP_DIR/backend/.venv/bin/pip" install \
    --index-url https://download.pytorch.org/whl/cpu \
    torch torchvision
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
# Home GPU worker (task-20a): same string as worker-agent/config.toml's
# `token` on the owner's PC. Leave empty to keep worker endpoints disabled.
WORKER_TOKEN=
EOF
    log "Edit $ENV_FILE now (JWT_SECRET especially - generate with: python3 -c 'import secrets; print(secrets.token_hex(32))'), then re-run this script."
    exit 1
fi

# The systemd unit loads $ENV_FILE via EnvironmentFile=, but app/core/config.py's
# pydantic-settings looks for a plain ".env" at the repo root (REPO_ROOT/.env) -
# any script run by hand (create_user.py, reset_password.py, a one-off shell)
# without going through systemd never sees deploy/.env's values and silently
# falls back to defaults, including a DIFFERENT db_path. This symlink makes
# both paths resolve to the exact same file so manual scripts and the live
# service always agree on which database (and which secrets) they're using.
sudo ln -sf "$ENV_FILE" "$APP_DIR/.env"

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
