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
"${PROOT}" login --shared-home debian -- /bin/bash /root/Parsing2026/android/debian-bootstrap.sh
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
