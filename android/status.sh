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
tail -n 40 "$PREFIX/var/log/sv/$SERVICE_NAME/current" 2>/dev/null || echo "No log yet."
