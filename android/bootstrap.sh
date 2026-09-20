#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATA_DIR="${HOME}/.local/share/parsing2026"
VENV="${ROOT}/.venv"
ENV_FILE="${ROOT}/.env"

if [ -z "${TERMUX_VERSION:-}" ] || [ -z "${PREFIX:-}" ]; then
  echo "ERROR: run this script inside Termux."
  exit 1
fi

cd "$ROOT"
mkdir -p "$DATA_DIR"

echo "== Parsing2026 / Android bootstrap =="
echo "ROOT: $ROOT"
echo "DATA: $DATA_DIR"

echo "[1/6] Updating Termux packages..."
pkg update -y
pkg upgrade -y

echo "[2/6] Installing native runtime/build packages..."
pkg install -y git python python-pip python-cryptography python-pydantic-core clang make pkg-config openssl ca-certificates libffi curl termux-services

if [ ! -d "$VENV" ]; then
  echo "[3/6] Creating Python venv with Termux system packages visible..."
# pydantic-core is a Rust extension and must come from the Android-native Termux package.
# pip cannot build its generic Linux wheel for aarch64-unknown-linux-android.
  python -m venv --system-site-packages "$VENV"
else
  echo "[3/6] Reusing existing venv: $VENV"
fi

PYTHON="$VENV/bin/python"
echo "Python: $($PYTHON --version)"

echo "[4/6] Installing Python dependencies..."
"$PYTHON" -m pip install --upgrade pip setuptools wheel
"$PYTHON" -m pip install --no-cache-dir -r "$ROOT/requirements-android.txt"

echo "[5/6] Preparing runtime configuration..."
if [ ! -f "$ENV_FILE" ]; then
  read -r -s -p "Telegram bot token: " TELEGRAM_TOKEN
  echo
  read -r -p "Owner Telegram ID: " OWNER_ID

  if [ -z "$TELEGRAM_TOKEN" ]; then
    echo "ERROR: Telegram bot token cannot be empty."
    exit 1
  fi
  if ! [[ "$OWNER_ID" =~ ^[0-9]+$ ]] || [ "$OWNER_ID" -le 0 ]; then
    echo "ERROR: Owner Telegram ID must be a positive integer."
    exit 1
  fi

  KEY="$("$PYTHON" -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
  umask 077
  cat > "$ENV_FILE" <<EOF
API_TOKEN=$TELEGRAM_TOKEN
OWNER_ID=$OWNER_ID
ACCESS_MODE=closed
AUTOBUY_MODE=dry-run
CREDENTIAL_ENCRYPTION_KEY=$KEY
LZT_BASE_URL=https://api.lzt.market
LZT_BALANCE_ID=20212
DB_FILE=$DATA_DIR/bot_data.sqlite
AUTOBUY_LOG_FILE=$DATA_DIR/autobuy.log
HEALTH_HOST=127.0.0.1
HEALTH_PORT=0
LOG_LEVEL=INFO
LOG_FORMAT=plain
EOF
  chmod 600 "$ENV_FILE"
  unset TELEGRAM_TOKEN KEY OWNER_ID
else
  echo "Existing .env preserved: $ENV_FILE"
fi

mkdir -p "$DATA_DIR"
chmod 700 "$DATA_DIR"

echo "[6/6] Running Android runtime preflight..."
"$PYTHON" - <<'PY'
import importlib
mods = ["aiogram", "aiohttp", "aiosqlite", "dotenv", "cryptography", "pydantic", "pydantic_core"]
for name in mods:
    module = importlib.import_module(name)
    print(f"OK {name} {getattr(module, '__version__', '')}".rstrip())
from cryptography.fernet import Fernet
Fernet.generate_key()
print("OK Fernet")
PY

chmod +x "$ROOT/android/"*.sh 2>/dev/null || true

echo
echo "Bootstrap complete."
echo "Next: bash android/install-service.sh"
echo "Then: bash android/install-boot.sh"
echo "The initial AUTOBUY_MODE is dry-run."
