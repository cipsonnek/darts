# DartSense — wdrożenie panelu operatora na serwerze

Ta paczka to **serwer centralny**: panel operatora (lokale, tarcze, statystyki, rozliczenia,
serwis), do którego tarcze w lokalach wysyłają swoje dane. Na serwer **nie** trafia program
tarczy z kamerami — ten działa na komputerze przy tarczy.

Instalacja **nie zmienia istniejącej strony** (np. wulkan-lawa.pl): panel dostaje własną
subdomenę i osobny wpis w serwerze WWW, a sama aplikacja słucha tylko lokalnie
(127.0.0.1:8100). Zużycie: ok. 300–500 MB RAM, ~1 GB dysku.

---

## Czego potrzebujesz

- VPS z Linuksem (Ubuntu 22.04/24.04 albo Debian 12) i dostęp **SSH jako root** (lub sudo),
- **subdomenę** dla panelu, np. `darts.wulkan-lawa.pl` (w przykładach niżej),
- na Windowsie: **WinSCP** (wgrywanie plików) i terminal (PowerShell ma `ssh`) lub PuTTY.

## Krok 0 — DNS (raz, 5 minut + czas propagacji)

W panelu, w którym zarządzasz domeną `wulkan-lawa.pl`, dodaj rekord:

| Typ | Nazwa   | Wartość          |
|-----|---------|------------------|
| A   | `darts` | adres IP serwera |

Sprawdzenie (po kilku–kilkudziesięciu minutach): `ping darts.wulkan-lawa.pl` pokazuje IP serwera.

## Krok 1 — wgraj paczkę

Plik: `dartsense-serwer-RRRRMMDD-GGMM.tar.gz` (nie rozpakowuj go na Windowsie).

**WinSCP:** Nowe połączenie → protokół SFTP, host = IP serwera, użytkownik `root` → zaloguj →
przeciągnij plik do katalogu `/root`.

albo z PowerShella:

```powershell
scp .\dartsense-serwer-*.tar.gz root@IP_SERWERA:/root/
```

## Krok 2 — instalacja (jedno polecenie)

Połącz się z serwerem (`ssh root@IP_SERWERA`) i wykonaj:

```bash
cd /root
tar xzf dartsense-serwer-*.tar.gz
cd dartsense-serwer
sudo bash deploy/install.sh darts.wulkan-lawa.pl
```

Skrypt sam: zainstaluje Pythona (jeśli trzeba), skopiuje aplikację do `/opt/dartsense`,
zainstaluje pakiety, uruchomi usługę `dartsense-central`, doda subdomenę do nginx/Apache
i zaproponuje darmowy certyfikat HTTPS (certbot — odpowiedz `T`, podaj e-mail i zaakceptuj
warunki Let's Encrypt). Można go bezpiecznie uruchomić ponownie.

## Krok 3 — konto do panelu

```bash
sudo bash /opt/dartsense/deploy/users.sh add szymon --name "Szymon"
```

Zapyta dwa razy o hasło (min. 8 znaków). Kolejne osoby — to samo z innym loginem.
Inne polecenia: `passwd LOGIN` (nowe hasło), `list`, `disable LOGIN`, `enable LOGIN`.

## Krok 4 — gotowe

Otwórz **https://darts.wulkan-lawa.pl** i zaloguj się.

---

## Podłączenie tarczy z lokalu

1. W panelu: **Tarcze → Dodaj tarczę**, wybierz lokal. Pokaże się blok `fleet:` z kluczem
   (klucz widać tylko raz — skopiuj od razu).
2. Na komputerze tarczy wklej go do pliku `configs\local.yaml` (utwórz, jeśli go nie ma).
   Adres musi być z `https://`:
   ```yaml
   fleet:
     url: https://darts.wulkan-lawa.pl
     board_key: dsb_...
   ```
3. Uruchom tarczę ponownie. Po minucie w panelu tarcza ma status **online**.

PIN obsługi tarczy (kalibracja) jest na komputerze tarczy w `data\service_pin.txt`;
własny ustawisz w `configs\local.yaml`:
```yaml
server:
  service_pin: "1234"
```

## Aktualizacja do nowej wersji

Wgraj nową paczkę jak w kroku 1, potem:

```bash
cd /root && rm -rf dartsense-serwer && tar xzf dartsense-serwer-NOWA.tar.gz
cd dartsense-serwer && sudo bash deploy/update.sh
```

Skrypt najpierw robi kopię bazy, potem podmienia kod i restartuje. Dane i konta zostają.

## Kopie zapasowe

Ręcznie: `sudo bash /opt/dartsense/deploy/backup.sh` (kopie w `/opt/dartsense/backups`,
trzymane ostatnie 30). Codziennie automatycznie — `crontab -e` jako root i dopisz:

```
30 3 * * * bash /opt/dartsense/deploy/backup.sh >/dev/null 2>&1
```

Najważniejsze dane to plik `/opt/dartsense/data/central.db` — warto co jakiś czas skopiować
kopię także poza serwer (WinSCP).

## Panel hostingowy (DirectAdmin, cPanel, HestiaCP, aaPanel, Plesk…)

Jeśli strona wulkan-lawa.pl jest zarządzana przez panel, skrypt to wykryje i **nie** zmieni
plików serwera WWW (panel by je nadpisał). Wtedy w panelu:

1. dodaj subdomenę `darts.wulkan-lawa.pl`,
2. ustaw dla niej **reverse proxy** (w panelu: „Proxy”, „Proxy template”, „Nginx proxy”)
   na adres `http://127.0.0.1:8100`, z przekazywaniem nagłówków `Host`, `X-Forwarded-For`
   i `X-Forwarded-Proto`,
3. włącz certyfikat SSL (Let's Encrypt) w panelu.

Reszta (usługa, konto) działa tak samo.

## Gdy coś nie działa

| Objaw | Co sprawdzić |
|---|---|
| Strona się nie otwiera | `ping darts.wulkan-lawa.pl` (DNS), `systemctl status dartsense-central` |
| „502 Bad Gateway” | usługa nie działa: `journalctl -u dartsense-central -n 80` |
| Certyfikat się nie wydał | DNS jeszcze nie wskazuje na serwer — odczekaj i: `certbot --nginx -d darts.wulkan-lawa.pl` |
| Tarcza „offline” | `url` w `configs\local.yaml` tarczy (z `https://`), klucz, internet w lokalu |
| Zapomniane hasło | `sudo bash /opt/dartsense/deploy/users.sh passwd LOGIN` |

Usunięcie w całości: `systemctl disable --now dartsense-central`, usuń
`/etc/systemd/system/dartsense-central.service`, plik `dartsense.conf` z katalogu nginx/Apache
(i przeładuj go) oraz katalog `/opt/dartsense` (najpierw skopiuj `data/central.db`!).

**Nie uruchamiaj na serwerze `backend.fleet_demo`** — wypełnia bazę przykładowymi danymi.
