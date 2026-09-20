#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE_NAME="parsing2026"
SERVICE_DIR="$PREFIX/var/service/$SERVICE_NAME"
LOG_DIR="$PREFIX/var/log/sv/$SERVICE_NAME"

if [ -z "${TERMUX_VERSION:-}" ]; then
  echo "ERROR: run inside Termux."
  exit 1
fi

cd "$ROOT"
if [ ! -x "$ROOT/.venv/bin/python" ]; then
  echo "ERROR: Android environment is not bootstrapped. Run: bash android/bootstrap.sh"
  exit 1
fi
if [ ! -f "$ROOT/.env" ]; then
  echo "ERROR: .env is missing. Run: bash android/bootstrap.sh"
  exit 1
fi

pkg install -y termux-services
mkdir -p "$SERVICE_DIR/log" "$LOG_DIR"

cat > "$SERVICE_DIR/run" <<EOF
#!/data/data/com.termux/files/usr/bin/sh
set -eu
cd "$ROOT"
exec "$ROOT/.venv/bin/python" "$ROOT/main.py"
EOF

cat > "$SERVICE_DIR/log/run" <<EOF
#!/data/data/com.termux/files/usr/bin/sh
set -eu
exec "$PREFIX/bin/svlogger"
EOF

chmod 700 "$SERVICE_DIR/run" "$SERVICE_DIR/log/run"
rm -f "$SERVICE_DIR/down"

export SVDIR="$PREFIX/var/service"
export LOGDIR="$PREFIX/var/log"
"$PREFIX/bin/service-daemon" start >/dev/null 2>&1 || true
sleep 1
"$PREFIX/bin/sv-enable" "$SERVICE_NAME"
"$PREFIX/bin/sv" up "$SERVICE_NAME"

echo
echo "Service installed: $SERVICE_NAME"
echo "Status: $PREFIX/bin/sv status $SERVICE_NAME"
echo "Logs:   $LOG_DIR/current"
