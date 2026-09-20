#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE_NAME="parsing2026"
SERVICE_DIR="$PREFIX/var/service/$SERVICE_NAME"
LOG_DIR="$PREFIX/var/log/sv/$SERVICE_NAME"
PROOT="$PREFIX/bin/proot-distro"

[ -n "${TERMUX_VERSION:-}" ] || { echo "ERROR: run inside Termux."; exit 1; }
[ -x "$PROOT" ] || { echo "ERROR: proot-distro is not installed."; exit 1; }
[ -x "$ROOT/.venv/bin/python" ] || { echo "ERROR: Debian runtime is not bootstrapped."; exit 1; }
[ -f "$ROOT/.env" ] || { echo "ERROR: .env is missing."; exit 1; }

mkdir -p "$SERVICE_DIR/log" "$LOG_DIR"

cat > "$SERVICE_DIR/run" <<EOF
#!/data/data/com.termux/files/usr/bin/sh
set -eu
exec "$PROOT" login --shared-home debian -- /bin/bash -lc 'cd /root/Parsing2026 && exec /root/Parsing2026/.venv/bin/python /root/Parsing2026/main.py'
EOF

cat > "$SERVICE_DIR/log/run" <<EOF
#!/data/data/com.termux/files/usr/bin/sh
set -eu
exec "$PREFIX/share/termux-services/svlogger" "$@"
EOF

chmod 700 "$SERVICE_DIR/run" "$SERVICE_DIR/log/run"
rm -f "$SERVICE_DIR/down"

export SVDIR="$PREFIX/var/service"
export LOGDIR="$PREFIX/var/log"
"$PREFIX/bin/service-daemon" start >/dev/null 2>&1 || true
sleep 1
command -v sv-enable >/dev/null 2>&1 && sv-enable "$SERVICE_NAME" >/dev/null 2>&1 || true
sv up "$SERVICE_NAME"

echo "Service installed: $SERVICE_NAME"
echo "Logs: $LOG_DIR/current"
