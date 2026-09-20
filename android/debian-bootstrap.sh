#!/bin/bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
ROOT="/root/Parsing2026"

cd "$ROOT"

echo "[debian 1/7] Installing Linux runtime dependencies..."
apt-get update
apt-get install -y --no-install-recommends \
  ca-certificates curl git python3 python3-venv python3-pip python3-dev \
  build-essential libffi-dev libssl-dev

echo "Debian Python: $(python3 --version)"

echo "[debian 2/7] Creating clean virtual environment..."
rm -rf "$ROOT/.venv"
python3 -m venv "$ROOT/.venv"
. "$ROOT/.venv/bin/activate"

echo "[debian 3/7] Installing project dependencies..."
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r "$ROOT/requirements.txt"
if [ -f "$ROOT/requirements-dev.txt" ]; then
  python -m pip install -r "$ROOT/requirements-dev.txt"
fi

mkdir -p /root/.local/share/parsing2026
chmod 700 /root/.local/share/parsing2026

if [ ! -f "$ROOT/.env" ]; then
  echo
  echo "Telegram token input is hidden by design."
  echo "Paste the token and press Enter; nothing will appear while typing/pasting."
  printf "Telegram bot token: "
  read -r -s TELEGRAM_TOKEN
  echo
  printf "Owner Telegram ID: "
  read -r OWNER_ID
  echo

  if [ -z "$TELEGRAM_TOKEN" ]; then
    echo "ERROR: Telegram bot token is empty."
    exit 1
  fi

  if ! [[ "$OWNER_ID" =~ ^[0-9]+$ ]] || [ "$OWNER_ID" -le 0 ]; then
    echo "ERROR: Owner Telegram ID must be a positive integer."
    exit 1
  fi

  KEY="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"

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

echo "[debian 4/7] Verifying Python dependencies..."
python -c "import aiogram,aiohttp,aiosqlite,dotenv,cryptography,pydantic,pydantic_core; from cryptography.fernet import Fernet; Fernet.generate_key(); print('IMPORTS OK'); print('aiogram',aiogram.__version__); print('cryptography',cryptography.__version__); print('pydantic',pydantic.__version__); print('pydantic-core',pydantic_core.__version__)"

echo "[debian 5/7] Compiling project..."
python -m compileall -q main.py test_v2.py app bot buyer domain filters market metrics purchase runtime services storage

echo "[debian 6/7] Running tests..."
python -m pytest -q

echo "[debian 7/7] Running correctness checks..."
python -m pyflakes main.py test_v2.py app bot buyer domain filters market metrics purchase runtime services storage
python -m ruff check .

echo
echo "Debian application runtime checks PASSED."
