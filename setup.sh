#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

VENV_DIR=".venv"
ENV_FILE=".env"
MIN_PY_MAJOR=3
MIN_PY_MINOR=14

# ── colours ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[setup]${NC} $*"; }
warn()  { echo -e "${YELLOW}[setup]${NC} $*"; }
error() { echo -e "${RED}[setup]${NC} $*" >&2; }

# ── 1. Python ─────────────────────────────────────────────────────────────────
install_python() {
    if [[ "$OSTYPE" == darwin* ]]; then
        if command -v brew &>/dev/null; then
            info "Installing/upgrading Python via Homebrew..."
            brew install python3 || true
            brew upgrade python3 || true
        else
            error "Homebrew not found. Install it from https://brew.sh then re-run setup."
            exit 1
        fi
    elif command -v apt-get &>/dev/null; then
        info "Installing Python via apt..."
        sudo apt-get update -qq
        sudo apt-get install -y python3 python3-venv python3-pip
    elif command -v dnf &>/dev/null; then
        info "Installing Python via dnf..."
        sudo dnf install -y python3 python3-pip
    else
        error "Cannot install Python automatically on this system."
        error "Install Python ${MIN_PY_MAJOR}.${MIN_PY_MINOR}+ manually: https://python.org/downloads"
        exit 1
    fi
}

version_ok() {
    local maj min
    maj=$(python3 -c "import sys; print(sys.version_info.major)")
    min=$(python3 -c "import sys; print(sys.version_info.minor)")
    [[ "$maj" -gt "$MIN_PY_MAJOR" ]] || { [[ "$maj" -eq "$MIN_PY_MAJOR" ]] && [[ "$min" -ge "$MIN_PY_MINOR" ]]; }
}

if ! command -v python3 &>/dev/null; then
    warn "Python 3 not found."
    install_python
elif ! version_ok; then
    warn "Python $(python3 -c 'import sys;print(f"{sys.version_info.major}.{sys.version_info.minor}")') too old (need ${MIN_PY_MAJOR}.${MIN_PY_MINOR}+). Upgrading automatically..."
    install_python
fi

if ! version_ok; then
    error "Auto-upgrade failed — still $(python3 -c 'import sys;print(f"{sys.version_info.major}.{sys.version_info.minor}")'), need ${MIN_PY_MAJOR}.${MIN_PY_MINOR}+."
    exit 1
fi

info "Python $(python3 -c 'import sys;print(f"{sys.version_info.major}.{sys.version_info.minor}")') OK."

# ── 2. Virtualenv ─────────────────────────────────────────────────────────────
if [[ ! -d "$VENV_DIR" ]]; then
    info "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
info "Virtualenv activated."

# ── 3. Dependencies ───────────────────────────────────────────────────────────
info "Installing dependencies..."
pip install --upgrade pip -q
pip install -r requirements.txt -q
info "Dependencies installed."

# ── 4. .env setup ─────────────────────────────────────────────────────────────
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
    ENCRYPTION_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")

    cat > "$ENV_FILE" <<EOF
BOT_TOKEN=${BOT_TOKEN}
ENCRYPTION_KEY=${ENCRYPTION_KEY}
EOF

    info ".env written. Keep it safe — it holds your encryption key."
    echo ""
else
    info ".env already exists — skipping setup."
fi

# ── 5. Run ────────────────────────────────────────────────────────────────────
info "Starting bot..."
echo ""
python bot.py
