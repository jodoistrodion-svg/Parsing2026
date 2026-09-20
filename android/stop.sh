#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
export SVDIR="$PREFIX/var/service"
export LOGDIR="$PREFIX/var/log"
sv down parsing2026
