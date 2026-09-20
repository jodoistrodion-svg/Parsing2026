#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKUP_DIR="$HOME/storage/downloads/parsing2026-backups"
STAMP="$(date +%Y%m%d-%H%M%S)"
PROOT="$PREFIX/bin/proot-distro"

mkdir -p "$BACKUP_DIR"

[ -f "$ROOT/.env" ] || { echo "ERROR: .env not found."; exit 1; }
[ -x "$ROOT/.venv/bin/python" ] || { echo "ERROR: Debian runtime is not installed."; exit 1; }

"$PROOT" login --shared-home debian -- /bin/bash -lc '
set -e
python - <<PY
import sqlite3
from pathlib import Path
src = Path("/root/.local/share/parsing2026/bot_data.sqlite")
dst = Path("/root/storage/downloads/parsing2026-backups/bot_data-'"$STAMP"'.sqlite")
dst.parent.mkdir(parents=True, exist_ok=True)
if not src.exists():
    print("No database yet; skipping database backup.")
else:
    with sqlite3.connect(src) as a, sqlite3.connect(dst) as b:
        a.backup(b)
    print(f"Database backup: {dst}")
PY
'

umask 077
cp "$ROOT/.env" "$BACKUP_DIR/env-$STAMP.env"
echo "Backup directory: $BACKUP_DIR"
