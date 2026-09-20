#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
PROOT="$PREFIX/bin/proot-distro"
SERVICE="parsing2026"
SDIR="$PREFIX/var/service/$SERVICE"
LDIR="$PREFIX/var/log/sv/$SERVICE"
BOOT="$HOME/.termux/boot/10-parsing2026"

[ -n "${TERMUX_VERSION:-}" ] || { echo "ERROR: run in Termux."; exit 1; }
[ -x "$PROOT" ] || { echo "ERROR: proot-distro is missing."; exit 1; }

cd "$ROOT"
echo "[1/6] Termux packages"
pkg update -y
pkg install -y proot-distro termux-services git curl ca-certificates

echo "[2/6] Debian"
if ! "$PROOT" login debian -- /bin/true >/dev/null 2>&1; then
  "$PROOT" install debian
fi

echo "[3/6] Python runtime"
"$PROOT" login --shared-home debian -- /bin/bash /root/Parsing2026/android/debian-bootstrap.sh

echo "[4/6] Service"
mkdir -p "$SDIR/log" "$LDIR"
cat > "$SDIR/run" <<EOF
#!/data/data/com.termux/files/usr/bin/sh
set -eu
exec "$PROOT" login --shared-home debian -- /bin/bash -lc 'cd /root/Parsing2026 && exec /root/Parsing2026/.venv/bin/python /root/Parsing2026/main.py'
EOF
cat > "$SDIR/log/run" <<EOF
#!/data/data/com.termux/files/usr/bin/sh
set -eu
exec "$PREFIX/share/termux-services/svlogger" "\$@"
EOF
chmod 700 "$SDIR/run" "$SDIR/log/run"
rm -f "$SDIR/down"

echo "[5/6] Boot"
mkdir -p "$(dirname "$BOOT")"
cat > "$BOOT" <<EOF
#!/data/data/com.termux/files/usr/bin/sh
set -eu
termux-wake-lock || true
export SVDIR="$PREFIX/var/service"
export LOGDIR="$PREFIX/var/log"
"$PREFIX/bin/service-daemon" start >/dev/null 2>&1 || true
sleep 3
"$PREFIX/bin/sv" up "$SERVICE" >/dev/null 2>&1 || true
EOF
chmod 700 "$BOOT"

export SVDIR="$PREFIX/var/service"
export LOGDIR="$PREFIX/var/log"
"$PREFIX/bin/service-daemon" start >/dev/null 2>&1 || true
sleep 2
command -v sv-enable >/dev/null 2>&1 && sv-enable "$SERVICE" >/dev/null 2>&1 || true
sv down "$SERVICE" >/dev/null 2>&1 || true
sleep 1
sv up "$SERVICE"
sleep 5

echo "[6/6] Result"
sv status "$SERVICE" || true
echo
echo "--- service log ---"
tail -n 60 "$LDIR/current" 2>/dev/null || true
echo
echo "--- app log ---"
tail -n 60 "$HOME/.local/share/parsing2026/autobuy.log" 2>/dev/null || true
echo
echo "DONE"
