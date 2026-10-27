#!/usr/bin/env bash
# Update the central server from a newer package (run from the unpacked new package):
#   sudo bash deploy/update.sh
# Backs up the database, replaces the code, installs packages, restarts. data/ is kept.
set -euo pipefail
APP=/opt/dartsense
SERVICE=dartsense-central
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

[ "$(id -u)" -eq 0 ] || { echo "Uruchom przez sudo."; exit 1; }
[ -d "$APP/.venv" ] || { echo "Brak instalacji w $APP — najpierw deploy/install.sh."; exit 1; }
[ "$SRC" != "$APP" ] || { echo "Uruchom z rozpakowanej NOWEJ paczki, nie z $APP."; exit 1; }

echo "==> Kopia bazy"
bash "$SRC/deploy/backup.sh"

echo "==> Nowy kod"
for d in backend vision configs frontend deploy; do rm -rf "${APP:?}/$d"; done
cp -a "$SRC"/backend "$SRC"/vision "$SRC"/configs "$SRC"/frontend "$SRC"/deploy "$SRC"/pyproject.toml "$APP"/
[ -f "$SRC/README.md" ] && cp -a "$SRC/README.md" "$APP"/
chown -R dartsense:dartsense "$APP"

echo "==> Pakiety"
sudo -u dartsense "$APP/.venv/bin/pip" install -q -r "$APP/deploy/requirements.txt"

echo "==> Restart (migracje bazy wykonują się same przy starcie)"
systemctl restart "$SERVICE"
for _ in $(seq 1 60); do
  curl -fsS http://127.0.0.1:8100/api/health >/dev/null 2>&1 && { echo "Działa."; exit 0; }
  sleep 1
done
echo "Usługa nie odpowiada — journalctl -u $SERVICE -n 80. Kopia bazy jest w $APP/backups."
exit 1
