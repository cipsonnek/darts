#!/usr/bin/env bash
# Consistent copy of the central database (safe while the service runs), keeps the last 30.
#   sudo bash /opt/dartsense/deploy/backup.sh
# Daily at 3:30 (crontab -e as root):
#   30 3 * * * bash /opt/dartsense/deploy/backup.sh >/dev/null 2>&1
set -euo pipefail
APP=/opt/dartsense
DB="$APP/data/central.db"
OUT="$APP/backups"
[ -f "$DB" ] || { echo "Brak bazy $DB — nic do skopiowania."; exit 0; }
mkdir -p "$OUT"
dest="$OUT/central-$(date +%Y%m%d-%H%M%S).db"
"$APP/.venv/bin/python" - "$DB" "$dest" <<'PY'
import sqlite3, sys
src = sqlite3.connect(sys.argv[1])
dst = sqlite3.connect(sys.argv[2])
src.backup(dst)
dst.close()
src.close()
PY
chown dartsense:dartsense "$dest" 2>/dev/null || true
chmod 640 "$dest"
ls -1t "$OUT"/central-*.db | tail -n +31 | xargs -r rm -f
echo "Kopia: $dest"
