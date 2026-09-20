#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

[ -n "${TERMUX_VERSION:-}" ] || { echo "ERROR: run inside Termux."; exit 1; }

BOOT_DIR="$HOME/.termux/boot"
mkdir -p "$BOOT_DIR"

cat > "$BOOT_DIR/10-parsing2026" <<EOF
#!/data/data/com.termux/files/usr/bin/sh
set -eu
termux-wake-lock || true
export SVDIR="$PREFIX/var/service"
export LOGDIR="$PREFIX/var/log"
"$PREFIX/bin/service-daemon" start >/dev/null 2>&1 || true
sleep 5
"$PREFIX/bin/sv" up parsing2026 >/dev/null 2>&1 || true
EOF

chmod 700 "$BOOT_DIR/10-parsing2026"
echo "Boot script installed: $BOOT_DIR/10-parsing2026"
echo "Install/open Termux:Boot once from the same source family as Termux."
