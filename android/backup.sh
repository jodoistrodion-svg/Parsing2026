#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATA_DIR="${HOME}/.local/share/parsing2026"
BACKUP_DIR="${HOME}/storage/downloads/parsing2026-backups"
STAMP="$(date +%Y%m%d-%H%M%S)"

mkdir -p "$BACKUP_DIR"
if [ ! -f "$ROOT/.env" ]; then
  echo "ERROR: .env not found."
  exit 1
fi

"$ROOT/.venv/bin/python" - <<PY
import sqlite3
from pathlib import Path
src = Path("$DATA_DIR/bot_data.sqlite")
dst = Path("$BACKUP_DIR/bot_data-$STAMP.sqlite")
if not src.exists():
    print("No database yet; skipping database backup.")
else:
    with sqlite3.connect(src) as a, sqlite3.connect(dst) as b:
        a.backup(b)
    print(f"Database backup: {dst}")
PY

umask 077
cp "$ROOT/.env" "$BACKUP_DIR/env-$STAMP.env"
echo "Backup directory: $BACKUP_DIR"
