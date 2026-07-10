#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

ENV_FILE=".env"
IMAGE="otp-magic"
CONTAINER_NAME="otp-magic"
DATA_DIR="$HOME/.otp_magic"

# ── colours ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[deploy]${NC} $*"; }
warn()  { echo -e "${YELLOW}[deploy]${NC} $*"; }
error() { echo -e "${RED}[deploy]${NC} $*" >&2; }

# ── 1. Container runtime ──────────────────────────────────────────────────────
RUNTIME=""
if command -v container &>/dev/null; then
    RUNTIME="container"
elif command -v docker &>/dev/null; then
    RUNTIME="docker"
elif [[ "$OSTYPE" == darwin* ]] && [[ "$(uname -m)" == arm64 ]] && command -v brew &>/dev/null; then
    info "No container runtime found — installing Apple Container via Homebrew..."
    brew install container
    RUNTIME="container"
else
    error "No container runtime found."
    error "Install Apple Container (brew install container, Apple Silicon + macOS 26+)"
    error "or Docker (https://docs.docker.com/get-docker/) and re-run."
    exit 1
fi
info "Using runtime: $RUNTIME"

if [[ "$RUNTIME" == "container" ]]; then
    container system start   # idempotent — no-op if already running
elif ! docker info &>/dev/null; then
    error "Docker daemon not running. Start Docker Desktop and re-run."
    exit 1
fi

# ── 2. .env setup ─────────────────────────────────────────────────────────────
if [[ ! -f "$ENV_FILE" ]]; then
    info "No .env found — running first-time setup."

    echo ""
    echo "  Get a bot token from @BotFather on Telegram."
    echo -n "  Enter BOT_TOKEN: "
    read -r BOT_TOKEN
    if [[ -z "$BOT_TOKEN" ]]; then
        error "BOT_TOKEN cannot be empty."
        exit 1
    fi

    info "Generating encryption key..."
    # Fernet key = urlsafe base64 of 32 random bytes — no Python needed on host
    ENCRYPTION_KEY=$(openssl rand -base64 32 | tr '+/' '-_')

    cat > "$ENV_FILE" <<EOF
BOT_TOKEN=${BOT_TOKEN}
ENCRYPTION_KEY=${ENCRYPTION_KEY}
EOF

    info ".env written. Keep it safe — it holds your encryption key."
    echo ""
else
    info ".env already exists — skipping setup."
fi

# ── 3. Data dir (SQLite DB lives here, survives rebuilds) ─────────────────────
mkdir -p "$DATA_DIR"
info "Data dir: $DATA_DIR"

# ── 4. Build image ────────────────────────────────────────────────────────────
info "Building image '$IMAGE'..."
"$RUNTIME" build -t "$IMAGE" .

# ── 5. Replace old container ──────────────────────────────────────────────────
"$RUNTIME" stop "$CONTAINER_NAME" &>/dev/null || true
"$RUNTIME" rm "$CONTAINER_NAME" &>/dev/null || true

# ── 6. Run ────────────────────────────────────────────────────────────────────
info "Starting container '$CONTAINER_NAME'..."
"$RUNTIME" run -d --name "$CONTAINER_NAME" \
    --env-file "$ENV_FILE" \
    -v "$DATA_DIR":/data \
    "$IMAGE"

echo ""
info "Deployed. Useful commands:"
echo "  $RUNTIME logs $CONTAINER_NAME     # watch bot output"
echo "  $RUNTIME stop $CONTAINER_NAME     # stop the bot"
echo "  ./deploy_container.sh             # rebuild + redeploy (data survives)"
