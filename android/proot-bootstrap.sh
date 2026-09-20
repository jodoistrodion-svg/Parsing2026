#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE_NAME="parsing2026"
SERVICE_DIR="$PREFIX/var/service/$SERVICE_NAME"
LOG_DIR="$PREFIX/var/log/sv/$SERVICE_NAME"
BOOT_DIR="$HOME/.termux/boot"
PROOT="$PREFIX/bin/proot-distro"

if [ -z "${TERMUX_VERSION:-}" ] || [ -z "${PREFIX:-}" ]; then
  echo "ERROR: this script must run inside Termux."
  exit 1
fi

cd "$ROOT"

echo "== Parsing2026 / Android Linux (PRoot-Distro) setup =="

echo "[1/8] Installing Termux host tools..."
pkg update -y
pkg install -y git curl ca-certificates proot-distro termux-services

echo "[2/8] Installing Debian container if necessary..."
if ! "$PROOT" login debian -- /bin/true >/dev/null 2>&1; then
  "$PROOT" install debian
fi

echo "[3/8] Preparing Debian runtime..."
"$PROOT" login --shared-home debian -- /bin/bash -lc '
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
ROOT="/root/Parsing2026"
cd "$ROOT"

apt-get update
apt-get install -y --no-install-recommends \
  ca-certificates curl git python3 python3-venv python3-pip python3-dev \
  build-essential libffi-dev libssl-dev

echo "Debian Python: $(python3 --version)"

rm -rf "$ROOT/.venv"
python3 -m venv "$ROOT/.venv"
. "$ROOT/.venv/bin/activate"

python -m pip install --upgrade pip setuptools wheel
python -m pip install -r "$ROOT/requirements.txt"
if [ -f "$ROOT/requirements-dev.txt" ]; then
  python -m pip install -r "$ROOT/requirements-dev.txt"
fi

mkdir -p /root/.local/share/parsing2026
chmod 700 /root/.local/share/parsing2026

if [ ! -f "$ROOT/.env" ]; then
  printf "Telegram bot token: "
  read -r -s TELEGRAM_TOKEN
  echo
  printf "Owner Telegram ID: "
  read -r OWNER_ID

  if [ -z "$TELEGRAM_TOKEN" ]; then
    echo "ERROR: Telegram bot token is empty."
    exit 1
  fi
  if ! [[ "$OWNER_ID" =~ ^[0-9]+$ ]] || [ "$OWNER_ID" -le 0 ]; then
    echo "ERROR: Owner Telegram ID must be a positive integer."
    exit 1
  fi

  KEY="$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")"
  umask 077
  cat > "$ROOT/.env" <<EOF
API_TOKEN=$TELEGRAM_TOKEN
OWNER_ID=$OWNER_ID
ACCESS_MODE=closed
AUTOBUY_MODE=dry-run
CREDENTIAL_ENCRYPTION_KEY=$KEY
LZT_BASE_URL=https://api.lzt.market
LZT_BALANCE_ID=20212
DB_FILE=/root/.local/share/parsing2026/bot_data.sqlite
AUTOBUY_LOG_FILE=/root/.local/share/parsing2026/autobuy.log
HEALTH_HOST=127.0.0.1
HEALTH_PORT=0
LOG_LEVEL=INFO
LOG_FORMAT=plain
EOF
  chmod 600 "$ROOT/.env"
  unset TELEGRAM_TOKEN OWNER_ID KEY
else
  echo "Existing .env preserved."
fi

echo "[4/8] Verifying Python dependencies..."
python -c "import aiogram,aiohttp,aiosqlite,dotenv,cryptography,pydantic,pydantic_core; from cryptography.fernet import Fernet; Fernet.generate_key(); print('IMPORTS OK'); print('aiogram',aiogram.__version__); print('cryptography',cryptography.__version__); print('pydantic',pydantic.__version__); print('pydantic-core',pydantic_core.__version__)"

echo "[5/8] Compiling project..."
python -m compileall -q .

echo "[6/8] Running tests..."
python -m pytest -q

echo "[7/8] Running correctness lint..."
python -m pyflakes .
python -m ruff check .

echo "[8/8] Debian runtime is READY."
'

echo "[service] Installing Termux supervised service..."
mkdir -p "$SERVICE_DIR/log" "$LOG_DIR" "$BOOT_DIR"

cat > "$SERVICE_DIR/run" <<EOF
#!/data/data/com.termux/files/usr/bin/sh
set -eu
exec "$PROOT" login --shared-home debian -- /bin/bash -lc 'cd /root/Parsing2026 && exec /root/Parsing2026/.venv/bin/python /root/Parsing2026/main.py'
EOF

cat > "$SERVICE_DIR/log/run" <<EOF
#!/data/data/com.termux/files/usr/bin/sh
set -eu
exec "$PREFIX/bin/svlogger"
EOF

chmod 700 "$SERVICE_DIR/run" "$SERVICE_DIR/log/run"
rm -f "$SERVICE_DIR/down"

cat > "$BOOT_DIR/10-parsing2026" <<EOF
#!/data/data/com.termux/files/usr/bin/sh
set -eu
termux-wake-lock || true
export SVDIR="$PREFIX/var/service"
export LOGDIR="$PREFIX/var/log"
"$PREFIX/bin/service-daemon" start >/dev/null 2>&1 || true
sleep 5
"$PREFIX/bin/sv" up "$SERVICE_NAME" >/dev/null 2>&1 || true
EOF
chmod 700 "$BOOT_DIR/10-parsing2026"

export SVDIR="$PREFIX/var/service"
export LOGDIR="$PREFIX/var/log"
"$PREFIX/bin/service-daemon" start >/dev/null 2>&1 || true
sleep 2
if command -v sv-enable >/dev/null 2>&1; then
  sv-enable "$SERVICE_NAME" >/dev/null 2>&1 || true
fi
sv up "$SERVICE_NAME"

echo
echo "=============================================="
echo "PARSING2026 ANDROID INSTALLATION COMPLETE"
echo "=============================================="
echo "Service: $SERVICE_NAME"
echo "Status:  sv status $SERVICE_NAME"
echo "Logs:    tail -n 100 $LOG_DIR/current"
echo "Boot:    $BOOT_DIR/10-parsing2026"
echo "Mode:    AUTOBUY_MODE=dry-run"
echo "Project: $ROOT"
echo "=============================================="
