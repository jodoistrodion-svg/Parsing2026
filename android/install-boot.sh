#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

if [ -z "${TERMUX_VERSION:-}" ]; then
  echo "ERROR: run inside Termux."
  exit 1
fi

BOOT_DIR="$HOME/.termux/boot"
mkdir -p "$BOOT_DIR"

cat > "$BOOT_DIR/10-parsing2026" <<'EOF'
#!/data/data/com.termux/files/usr/bin/sh
set -eu
termux-wake-lock || true
sleep 8
export SVDIR="$PREFIX/var/service"
export LOGDIR="$PREFIX/var/log"
. "$PREFIX/etc/profile.d/start-services.sh"
EOF

chmod 700 "$BOOT_DIR/10-parsing2026"
echo "Boot script installed: $BOOT_DIR/10-parsing2026"
echo "Install and open Termux:Boot once, from the same source/signing family as Termux."
