"""Demo data for the central fleet server: ``python -m backend.fleet_demo``.

Creates venues in Polish cities, boards, a few months of game history (busier in the
evenings and at weekends), board health states and service tickets, so the operator panel
can be shown before real boards report.

    python -m backend.fleet_demo --reset          # wipe fleet tables and seed again
    python -m backend.fleet_demo --live           # keep demo boards online (and playing) while running
    python -m backend.fleet_demo --link-simulator # register a board for the local simulator and
                                                  # write fleet.url/board_key to configs/local.yaml

All names, addresses and contacts are invented. Demo boards have serials starting with DEMO-.
"""

from __future__ import annotations

import argparse
import os
import random
import time
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import yaml
from sqlalchemy import delete, insert, select

from backend.database import Database
from backend.database.models import Board, BoardGame, Ticket, TicketComment, Venue
from backend.services.fleet_service import FleetService
from backend.settings import ROOT, load_settings

CITIES = {
    "Warszawa": (52.2297, 21.0122), "Kraków": (50.0614, 19.9366), "Wrocław": (51.1079, 17.0385),
    "Poznań": (52.4064, 16.9252), "Gdańsk": (54.3520, 18.6466), "Łódź": (51.7592, 19.4560),
    "Katowice": (50.2649, 19.0238), "Lublin": (51.2465, 22.5684), "Szczecin": (53.4285, 14.5528),
    "Białystok": (53.1325, 23.1688), "Rzeszów": (50.0412, 21.9991), "Bydgoszcz": (53.1235, 18.0084),
}

# name, kind, city, street, popularity (games per board per average day), price, venue share %
VENUES = [
    ("Pub Pod Lotką", "pub", "Kraków", "ul. Długa 14", 16, 6, 50),
    ("Bar Bullseye", "bar", "Warszawa", "ul. Chmielna 21", 22, 8, 50),
    ("Salon Gier Arena", "arcade", "Warszawa", "al. Jana Pawła II 43", 26, 8, 40),
    ("Klub Oko Byka", "club", "Wrocław", "ul. Ruska 19", 14, 6, 50),
    ("Pub Stara Tarcza", "pub", "Poznań", "ul. Wrocławska 8", 12, 5, 50),
    ("Arena 180", "arcade", "Gdańsk", "ul. Grunwaldzka 82", 19, 7, 45),
    ("Bar Na Rogu", "bar", "Łódź", "ul. Piotrkowska 101", 15, 5, 50),
    ("Salon Gier Joker", "arcade", "Katowice", "ul. Mariacka 5", 17, 6, 40),
    ("Pub Trzy Lotki", "pub", "Lublin", "ul. Krakowskie Przedmieście 30", 10, 5, 50),
    ("Klub Double Out", "club", "Szczecin", "al. Wojska Polskiego 12", 11, 6, 60),
    ("Bar Przystań", "bar", "Białystok", "ul. Lipowa 7", 8, 5, 50),
    ("Pub Celownik", "pub", "Rzeszów", "ul. 3 Maja 16", 9, 5, 50),
    ("Pub Kufel", "pub", "Bydgoszcz", "ul. Gdańska 40", 7, 5, 50),
    ("Salon Gier Retro", "arcade", "Kraków", "ul. Kalwaryjska 9", 13, 6, 45),
]
HOURS = {"pub": (16, 2), "bar": (15, 1), "club": (18, 3), "arcade": (12, 22), "other": (12, 22)}
HOURS_TEXT = {"pub": "pn–nd 16:00–02:00", "bar": "pn–nd 15:00–01:00", "club": "śr–nd 18:00–03:00",
              "arcade": "pn–nd 12:00–22:00", "other": ""}
WEEKDAY = [0.6, 0.6, 0.75, 0.9, 1.4, 1.65, 1.0]  # Mon..Sun
MODES = [("x01", 55), ("cricket", 20), ("atc", 10), ("shanghai", 8), ("bobs27", 7)]
CONTACTS = ["Anna Kowalczyk", "Piotr Nowak", "Marta Wiśniewska", "Tomasz Lewandowski", "Katarzyna Zielińska",
            "Michał Wójcik", "Agnieszka Kamińska", "Paweł Szymański", "Ewa Dąbrowska", "Krzysztof Mazur"]
TECHS = ["Marek (serwis)", "Kamil (serwis)", "Ola (wsparcie)"]


def _hour_weights(kind: str) -> list[float]:
    """Relative chance of a game starting in each local hour, given the opening hours."""
    open_h, close_h = HOURS[kind]
    w = [0.0] * 24
    h = open_h
    while h != close_h:
        # ramps up towards a 20:00–23:00 peak
        w[h] = 1.0 + (2.5 if 20 <= h <= 22 else 1.5 if h in (19, 23) else 0.8 if h in (0, 18) else 0.3)
        h = (h + 1) % 24
    return w


def reset(db: Database) -> None:
    with db.session() as s:
        for model in (TicketComment, Ticket, BoardGame, Board, Venue):
            s.execute(delete(model))


def seed(db: Database, days: int, rnd: random.Random, tz: ZoneInfo) -> None:
    now = datetime.now(timezone.utc)
    today = now.astimezone(tz).date()
    boards: list[tuple[Board, Venue, float]] = []
    with db.session() as s:
        for i, (name, kind, city, street, pop, price, share) in enumerate(VENUES):
            lat, lng = CITIES[city]
            v = Venue(name=name, kind=kind, address=street, city=city,
                      postal_code=f"{rnd.randint(10, 99)}-{rnd.randint(100, 999)}",
                      lat=round(lat + rnd.uniform(-0.012, 0.012), 5), lng=round(lng + rnd.uniform(-0.018, 0.018), 5),
                      contact_name=CONTACTS[i % len(CONTACTS)], phone=f"+48 600 100 {100 + i:03d}",
                      email=f"lokal{i + 1}@example.com", opening_hours=HOURS_TEXT[kind],
                      price_per_game=float(price), venue_share_pct=float(share),
                      created_at=now - timedelta(days=days + 10))
            s.add(v)
            s.flush()
            n_boards = 3 if pop >= 22 else 2 if pop >= 13 else 1
            for k in range(n_boards):
                installed = now - timedelta(days=rnd.randint(min(30, days), days) if k else days)
                b = Board(venue_id=v.id, name=f"{city[:3].upper()}-{i + 1:02d}-{k + 1}", serial=f"DEMO-{i + 1:02d}{k + 1}",
                          key_hash=f"demo{i:02d}{k}".ljust(64, "0"), key_prefix="demo", installed_at=installed,
                          created_at=installed)
                s.add(b)
                s.flush()
                boards.append((b, v, pop * rnd.uniform(0.8, 1.2)))
        # spare board in the warehouse, registered but never connected
        s.add(Board(name="MAG-01", serial="DEMO-SPARE", key_hash="demospare".ljust(64, "0"), key_prefix="demo",
                    notes="Zapasowa tarcza w magazynie"))

        # game history
        rows = []
        mode_names, mode_w = zip(*MODES)
        for b, v, rate in boards:
            hours = _hour_weights(v.kind)
            installed_local = b.installed_at.astimezone(tz).date()
            for d in range(days, -1, -1):
                day = today - timedelta(days=d)
                if day < installed_local:
                    continue
                trend = 0.85 + 0.3 * (1 - d / max(days, 1))  # slow growth
                n = max(0, round(rnd.gauss(rate * WEEKDAY[day.weekday()] * trend, rate * 0.25)))
                for _ in range(n):
                    hour = rnd.choices(range(24), hours)[0]
                    # hours after midnight belong to the previous evening
                    start_day = day + timedelta(days=1) if hour < HOURS[v.kind][0] and HOURS[v.kind][1] < HOURS[v.kind][0] else day
                    start = datetime(start_day.year, start_day.month, start_day.day, hour, rnd.randint(0, 59),
                                     rnd.randint(0, 59), tzinfo=tz).astimezone(timezone.utc)
                    if start > now:
                        continue
                    players = rnd.choices((1, 2, 3, 4), (15, 55, 18, 12))[0]
                    minutes = max(4, rnd.gauss(7 + 4 * players, 3))
                    mode = rnd.choices(mode_names, mode_w)[0]
                    rows.append({"board_id": b.id, "venue_id": v.id, "game_id": f"demo{len(rows):07d}", "mode": mode,
                                 "status": "abandoned" if rnd.random() < 0.06 else "finished", "players": players,
                                 "darts": int(minutes * rnd.uniform(3.5, 5)), "started_at": start,
                                 "finished_at": start + timedelta(minutes=minutes), "duration_s": int(minutes * 60),
                                 "price": v.price_per_game, "venue_share_pct": v.venue_share_pct, "received_at": start})
        for i in range(0, len(rows), 5000):
            s.execute(insert(BoardGame), rows[i:i + 5000])

        # health: most boards online and fine, a few with typical problems
        def beat(b: Board, seen: datetime | None, cams_ok=(True, True, True), calibrated=(True, True, True),
                 calibration="ok", playing=False):
            b.last_seen_at = seen
            b.last_status = {"version": "1.0.0", "mode": "live", "engine": "idle", "calibration": calibration,
                             "uptime_s": rnd.randint(3600, 9 * 86400), "active_game": playing,
                             "cameras": [{"id": f"cam{j + 1}", "connected": cams_ok[j], "calibrated": calibrated[j],
                                          "fps": 30.0 if cams_ok[j] else None} for j in range(3)]}

        all_boards = [b for b, _, _ in boards]
        for b in all_boards:
            beat(b, now - timedelta(seconds=rnd.randint(5, 50)), playing=rnd.random() < 0.3)
        beat(all_boards[4], now - timedelta(hours=3, minutes=12))                       # offline
        beat(all_boards[9], now - timedelta(days=2, hours=5))                           # offline for days
        beat(all_boards[6], now - timedelta(seconds=20), cams_ok=(True, False, True))   # camera unplugged
        beat(all_boards[12], now - timedelta(seconds=30), calibrated=(True, True, False), calibration="warning")
        all_boards[15].status = "maintenance"
        all_boards[15].notes = "Wymiana pierścienia LED zaplanowana"

        # service tickets
        def ticket(b: Board, title, desc, cat, prio, status, age_h, assignee="", comments=()):
            created = now - timedelta(hours=age_h)
            t = Ticket(board_id=b.id, venue_id=b.venue_id, title=title, description=desc, category=cat, priority=prio,
                       status=status, assignee=assignee, reporter="Lokal" if cat == "fault" else "Operator",
                       created_at=created, updated_at=created,
                       closed_at=created + timedelta(hours=age_h * 0.6) if status == "closed" else None)
            s.add(t)
            s.flush()
            for k, (author, text, change) in enumerate(comments):
                s.add(TicketComment(ticket_id=t.id, author=author, text=text, status_change=change,
                                    created_at=created + timedelta(hours=(k + 1) * age_h / (len(comments) + 1))))

        ticket(all_boards[6], "Kamera 2 nie łapie obrazu", "Obsługa zgłasza, że od wczoraj tarcza źle liczy rzuty z lewej strony.",
               "fault", "high", "in_progress", 20, TECHS[0],
               [(TECHS[0], "Zdalnie: kamera 2 rozłączona, prawdopodobnie kabel USB.", "open->in_progress"),
                (TECHS[0], "Wizyta umówiona na jutro 12:00.", "")])
        ticket(all_boards[4], "Tarcza offline", "Brak sygnału od ponad 3 godzin.", "fault", "critical", "open", 3)
        ticket(all_boards[9], "Brak połączenia z internetem", "Lokal zmienił router, tarcza nie łączy się z siecią.",
               "fault", "high", "waiting", 50, TECHS[2],
               [(TECHS[2], "Poproszono lokal o hasło do nowej sieci Wi-Fi.", "open->waiting")])
        ticket(all_boards[12], "Kalibracja do sprawdzenia", "Automatyczna kontrola wykryła przesunięcie kamery 3.",
               "maintenance", "normal", "open", 6)
        ticket(all_boards[15], "Wymiana pierścienia LED", "Planowa wymiana oświetlenia.", "maintenance", "normal",
               "in_progress", 30, TECHS[1], [(TECHS[1], "Części zamówione.", "open->in_progress")])
        ticket(all_boards[0], "Wymiana tarczy (zużyte sizal)", "Pole 20 mocno zużyte.", "maintenance", "low", "closed", 240,
               TECHS[1], [(TECHS[1], "Tarcza wymieniona, kalibracja OK.", "open->closed")])
        ticket(all_boards[2], "Gracze zgłaszają podwójne liczenie", "Odbita lotka liczona dwa razy.", "fault", "normal",
               "closed", 400, TECHS[0], [(TECHS[0], "Zaktualizowano oprogramowanie do 1.0.0.", "open->closed")])
        ticket(all_boards[1], "Montaż drugiej tarczy", "Lokal chce drugą tarczę na sali VIP.", "install", "normal",
               "open", 70)


def live(db: Database, svc: FleetService, rnd: random.Random, tz: ZoneInfo, interval: int = 30) -> None:
    """Keep demo boards that were online at seeding online, and occasionally record games."""
    print("Demo na żywo: odświeżam tarcze DEMO- co", interval, "s (Ctrl+C kończy)")
    while True:
        now = datetime.now(timezone.utc)
        local = now.astimezone(tz)
        with db.session() as s:
            boards = list(s.scalars(select(Board).where(Board.serial.like("DEMO-%"), Board.status == "active",
                                                        Board.last_seen_at.is_not(None))))
            venues = {v.id: v for v in s.scalars(select(Venue))}
            for b in boards:
                seen = b.last_seen_at if b.last_seen_at.tzinfo else b.last_seen_at.replace(tzinfo=timezone.utc)
                if now - seen > timedelta(minutes=10):
                    continue  # boards seeded as offline stay offline
                b.last_seen_at = now
                st = dict(b.last_status or {})
                st["active_game"] = rnd.random() < 0.35
                b.last_status = st
                v = venues.get(b.venue_id)
                if v and _hour_weights(v.kind)[local.hour] and rnd.random() < 0.08:
                    start = now - timedelta(minutes=rnd.randint(8, 20))
                    s.add(BoardGame(board_id=b.id, venue_id=v.id, game_id=f"live{int(time.time() * 1000) % 10**10}{rnd.randint(0, 99)}",
                                    mode=rnd.choices([m for m, _ in MODES], [w for _, w in MODES])[0], players=2,
                                    darts=rnd.randint(30, 80), started_at=start, finished_at=now,
                                    duration_s=int((now - start).total_seconds()), price=v.price_per_game,
                                    venue_share_pct=v.venue_share_pct))
        time.sleep(interval)


def link_simulator(svc: FleetService, port: int) -> None:
    """Register a board for the local simulator and point it at this server in configs/local.yaml."""
    venues = [v for v in svc.list_venues() if v["active"]]
    board = svc.create_board({"name": "Symulator (dev)", "serial": "SIM-LOCAL",
                              "venue_id": venues[0]["id"] if venues else None,
                              "notes": "Lokalny symulator dewelopera"})
    path = ROOT / "configs" / "local.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    data = data or {}
    data["fleet"] = {**(data.get("fleet") or {}), "url": f"http://127.0.0.1:{port}", "board_key": board["api_key"],
                     "interval_s": 15}
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(f"Tarcza '{board['name']}' zarejestrowana w lokalu {board['venue_name'] or '—'}; klucz zapisany w {path}.")
    print("Uruchom ponownie symulator (python -m backend --simulator), żeby zaczął raportować.")


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m backend.fleet_demo", description=__doc__.splitlines()[0])
    ap.add_argument("--days", type=int, default=120, help="days of game history (default 120)")
    ap.add_argument("--reset", action="store_true", help="delete all fleet data first")
    ap.add_argument("--live", action="store_true", help="keep demo boards online while running")
    ap.add_argument("--link-simulator", action="store_true", help="register the local simulator as a board")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    os.environ.setdefault("DARTSENSE_CONFIG", "configs/central.yaml")
    settings = load_settings()
    if settings.mode != "central":
        raise SystemExit("Uruchom z konfiguracją centralną (configs/central.yaml).")
    db = Database(settings.database.url)
    db.migrate()
    svc = FleetService(db, settings.fleet)
    rnd = random.Random(args.seed)
    tz = ZoneInfo(settings.fleet.timezone)
    with db.session() as s:
        has_data = s.scalar(select(Venue.id).limit(1)) is not None
    if args.reset:
        reset(db)
        has_data = False
    if not has_data:
        t0 = time.time()
        seed(db, args.days, rnd, tz)
        st = svc.stats(str(date.today() - timedelta(days=args.days)), None)
        print(f"Dane demo: {len(VENUES)} lokali, {len(svc.list_boards())} tarcz, {st['totals']['games']} gier "
              f"({time.time() - t0:.1f} s).")
    elif not (args.live or args.link_simulator):
        print("Baza ma już dane floty — użyj --reset, żeby wygenerować je od nowa.")
    if args.link_simulator:
        link_simulator(svc, settings.server.port)
    if args.live:
        try:
            live(db, svc, rnd, tz)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
