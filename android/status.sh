#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
SERVICE_NAME="parsing2026"
export SVDIR="$PREFIX/var/service"
export LOGDIR="$PREFIX/var/log"
if ! command -v sv >/dev/null 2>&1; then
  echo "termux-services is not installed."
  exit 1
fi
sv status "$SERVICE_NAME" || true
echo
echo "Recent service log:"
tail -n 100 "$PREFIX/var/log/sv/$SERVICE_NAME/current" 2>/dev/null || echo "No log yet."
echo
if command -v proot-distro >/dev/null 2>&1; then
  echo "PRoot sessions:"
  proot-distro ps || true
fi
