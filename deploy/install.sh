#!/usr/bin/env bash
# DartSense — central server (operator panel) on a Linux VPS, next to existing websites.
#
#   sudo bash deploy/install.sh darts.example.pl
#
# What it does (safe to run again):
#   1. installs Python (venv) if missing, creates the system user "dartsense"
#   2. copies the application to /opt/dartsense (data/ is never touched)
#   3. installs the Python packages into /opt/dartsense/.venv
#   4. registers and starts the systemd service "dartsense-central" (127.0.0.1:8100 only)
#   5. adds a reverse proxy for the domain to nginx or Apache — the other sites stay as they are
#   6. offers a free HTTPS certificate (Let's Encrypt, certbot)
set -euo pipefail

DOMAIN="${1:-}"
APP=/opt/dartsense
SVC_USER=dartsense
SERVICE=dartsense-central
PORT=8100
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

say()  { printf '\n\033[1;33m==> %s\033[0m\n' "$*"; }
ok()   { printf '\033[1;32m    %s\033[0m\n' "$*"; }
fail() { printf '\n\033[1;31mBŁĄD: %s\033[0m\n' "$*" >&2; exit 1; }

[ -n "$DOMAIN" ] || fail "podaj domenę panelu, np.:  sudo bash deploy/install.sh darts.wulkan-lawa.pl"
[ "$(id -u)" -eq 0 ] || fail "uruchom przez sudo (potrzebne prawa administratora)"
[ -f "$SRC/backend/__main__.py" ] || fail "uruchom skrypt z rozpakowanej paczki (brak backend/)"

# ------------------------------------------------------------------ hosting panels
# A panel (DirectAdmin, cPanel, HestiaCP, aaPanel, Plesk, ISPConfig) rewrites web server
# configs itself; there the proxy has to be added in the panel, not in files.
PANEL=""
[ -d /usr/local/directadmin ] && PANEL="DirectAdmin"
[ -d /usr/local/cpanel ] && PANEL="cPanel"
[ -d /usr/local/hestia ] && PANEL="HestiaCP"
[ -d /usr/local/vesta ] && PANEL="VestaCP"
[ -d /www/server/panel ] && PANEL="aaPanel"
[ -d /usr/local/psa ] && PANEL="Plesk"
[ -d /usr/local/ispconfig ] && PANEL="ISPConfig"

# ------------------------------------------------------------------ 1. system packages
say "1/6 Python"
need_py=1
if command -v python3 >/dev/null && python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
  python3 -m venv --help >/dev/null 2>&1 && python3 -c 'import ensurepip' 2>/dev/null && need_py=0
fi
if [ "$need_py" -eq 1 ]; then
  if command -v apt-get >/dev/null; then
    apt-get update -qq
    ver=$(python3 -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")' 2>/dev/null || echo 3)
    apt-get install -y -qq python3 python3-venv python3-pip "python${ver}-venv" >/dev/null 2>&1 \
      || apt-get install -y -qq python3 python3-venv python3-pip >/dev/null
  elif command -v dnf >/dev/null; then
    dnf install -y -q python3 python3-pip
  else
    fail "nie znam menedżera pakietów tego systemu — zainstaluj Python 3.10+ z modułem venv"
  fi
fi
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' \
  || fail "potrzebny Python 3.10 lub nowszy (jest $(python3 --version 2>&1))"
ok "$(python3 --version)"

id "$SVC_USER" >/dev/null 2>&1 || useradd --system --home-dir "$APP" --shell /usr/sbin/nologin "$SVC_USER"

# ------------------------------------------------------------------ 2. application files
say "2/6 Pliki aplikacji → $APP"
mkdir -p "$APP"
if [ "$SRC" != "$APP" ]; then
  # replace code, keep data/ (database, settings) and .venv
  for d in backend vision configs frontend deploy; do rm -rf "${APP:?}/$d"; done
  cp -a "$SRC"/backend "$SRC"/vision "$SRC"/configs "$SRC"/frontend "$SRC"/deploy "$APP"/
  cp -a "$SRC"/pyproject.toml "$APP"/
  [ -f "$SRC/README.md" ] && cp -a "$SRC/README.md" "$APP"/
fi
mkdir -p "$APP/data" "$APP/logs" "$APP/backups"
chown -R "$SVC_USER:$SVC_USER" "$APP"
chmod 750 "$APP/data" "$APP/backups"
ok "skopiowano"

# ------------------------------------------------------------------ 3. python packages
say "3/6 Pakiety Pythona (pierwszy raz kilka minut)"
[ -x "$APP/.venv/bin/python" ] || sudo -u "$SVC_USER" python3 -m venv "$APP/.venv"
sudo -u "$SVC_USER" "$APP/.venv/bin/pip" install -q --upgrade pip
sudo -u "$SVC_USER" "$APP/.venv/bin/pip" install -q -r "$APP/deploy/requirements.txt"
ok "zainstalowano"

# ------------------------------------------------------------------ 4. service
say "4/6 Usługa systemd: $SERVICE"
sed -e "s#__APP__#$APP#g" -e "s#__USER__#$SVC_USER#g" "$APP/deploy/dartsense-central.service" \
  > "/etc/systemd/system/$SERVICE.service"
systemctl daemon-reload
systemctl enable "$SERVICE" >/dev/null 2>&1
systemctl restart "$SERVICE"
for _ in $(seq 1 60); do
  curl -fsS "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1 && break
  sleep 1
done
curl -fsS "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1 \
  || fail "usługa nie odpowiada — zobacz: journalctl -u $SERVICE -n 80"
ok "działa na 127.0.0.1:$PORT (z zewnątrz niedostępna, tylko przez serwer WWW)"

# ------------------------------------------------------------------ 5. web server
say "5/6 Serwer WWW dla $DOMAIN"
WEB=""
if [ -n "$PANEL" ]; then
  printf '    Wykryto panel %s. Dodaj w nim domenę %s i ustaw „reverse proxy” na http://127.0.0.1:%s\n' "$PANEL" "$DOMAIN" "$PORT"
  printf '    (szczegóły: deploy/README-WDROZENIE.md, sekcja „Panel hostingowy”). Pomijam ten krok.\n'
elif command -v nginx >/dev/null; then
  WEB=nginx
  conf=$(sed -e "s#__DOMAIN__#$DOMAIN#g" -e "s#__PORT__#$PORT#g" "$APP/deploy/nginx-dartsense.conf")
  if [ -d /etc/nginx/sites-available ]; then
    echo "$conf" > /etc/nginx/sites-available/dartsense.conf
    ln -sf /etc/nginx/sites-available/dartsense.conf /etc/nginx/sites-enabled/dartsense.conf
  else
    echo "$conf" > /etc/nginx/conf.d/dartsense.conf
  fi
  nginx -t || fail "konfiguracja nginx ma błąd — strona wulkan-lawa.pl działa dalej bez zmian; usuń dartsense.conf i sprawdź"
  systemctl reload nginx
  ok "nginx: dodano $DOMAIN"
elif command -v apache2 >/dev/null || command -v httpd >/dev/null; then
  WEB=apache
  conf=$(sed -e "s#__DOMAIN__#$DOMAIN#g" -e "s#__PORT__#$PORT#g" "$APP/deploy/apache-dartsense.conf")
  if command -v a2enmod >/dev/null; then
    a2enmod -q proxy proxy_http headers >/dev/null
    echo "$conf" > /etc/apache2/sites-available/dartsense.conf
    a2ensite -q dartsense >/dev/null
    apache2ctl configtest || fail "konfiguracja Apache ma błąd"
    systemctl reload apache2
  else
    echo "$conf" > /etc/httpd/conf.d/dartsense.conf
    httpd -t || fail "konfiguracja Apache ma błąd"
    systemctl reload httpd
  fi
  ok "Apache: dodano $DOMAIN"
else
  printf '    Nie znalazłem nginx ani Apache. Zainstaluj nginx (apt install nginx) i uruchom skrypt ponownie.\n'
fi

# ------------------------------------------------------------------ 6. HTTPS
say "6/6 Certyfikat HTTPS"
if [ -n "$WEB" ] && command -v certbot >/dev/null; then
  printf '    Domena %s musi już wskazywać na ten serwer (rekord A w DNS).\n' "$DOMAIN"
  read -r -p "    Uruchomić certbot teraz? [T/n] " a || a=n
  if [[ ! "$a" =~ ^[nN] ]]; then
    certbot "--$WEB" -d "$DOMAIN" --redirect || printf '    certbot się nie udał — sprawdź DNS i uruchom: certbot --%s -d %s\n' "$WEB" "$DOMAIN"
  fi
elif [ -n "$WEB" ]; then
  printf '    Brak certbota. Zainstaluj:  apt install certbot python3-certbot-%s\n' "$WEB"
  printf '    a potem:                    certbot --%s -d %s --redirect\n' "$WEB" "$DOMAIN"
fi

cat <<EOF

$(printf '\033[1;32m')Gotowe.$(printf '\033[0m')

  Załóż pierwsze konto do panelu (zapyta o hasło, min. 8 znaków):
    sudo bash $APP/deploy/users.sh add LOGIN --name "Imię Nazwisko"

  Panel:     https://$DOMAIN
  Logi:      journalctl -u $SERVICE -f
  Restart:   systemctl restart $SERVICE
  Kopia bazy: sudo bash $APP/deploy/backup.sh   (kopie w $APP/backups)
EOF
