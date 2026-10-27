"""Central fleet server: venues, boards, ingest from boards, statistics, settlements, tickets,
and the board-side reporter talking to it."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.database import Database
from backend.database.models import Game, GamePlayer, Player
from backend.services.fleet_client import FleetReporter
from backend.settings import load_settings


def _settings(tmp_path, **extra):
    return load_settings(extra={
        "mode": "central",
        "data_dir": str(tmp_path / "data"),
        "database": {"url": f"sqlite:///{(tmp_path / 'central.sqlite').as_posix()}"},
        "logging": {"directory": str(tmp_path / "logs"), "json": False},
        "server": {"serve_frontend": False},
        "vision": {"cameras": [], "validation": {"enabled": False}},
        **extra,
    })


@pytest.fixture()
def client(tmp_path):
    with TestClient(create_app(_settings(tmp_path))) as c:
        c.app.state.auth.create_user("operator", "sekretne-haslo")
        assert c.post("/api/auth/login", json={"username": "operator", "password": "sekretne-haslo"}).status_code == 200
        yield c


def _venue(c, **kw):
    body = {"name": "Pub Pod Lotką", "city": "Kraków", "lat": 50.06, "lng": 19.94, "price_per_game": 6,
            "venue_share_pct": 40} | kw
    r = c.post("/api/fleet/venues", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _board(c, venue_id=None):
    r = c.post("/api/fleet/boards", json={"name": "Tarcza 1", "venue_id": venue_id})
    assert r.status_code == 201, r.text
    return r.json()


def _game(i, start, minutes=12):
    return {"game_id": f"g{i}", "mode": "x01", "players": 2, "darts": 60,
            "started_at": start.isoformat(), "finished_at": (start + timedelta(minutes=minutes)).isoformat()}


def test_fleet_routes_only_on_central(tmp_path):
    with TestClient(create_app(_settings(tmp_path, mode="simulator"), start_vision=False)) as c:
        assert c.get("/api/fleet/venues").status_code == 404


def test_operator_panel_needs_sign_in(tmp_path):
    with TestClient(create_app(_settings(tmp_path))) as c:
        auth = c.app.state.auth
        auth.create_user("Jan", "dlugie-haslo-1", "Jan Kowalski")
        # no session: the panel API and /me are closed, the board's API does not exist here
        assert c.get("/api/fleet/venues").status_code == 401
        assert c.get("/api/auth/me").status_code == 401
        assert c.get("/api/games").status_code == 404
        assert c.get("/api/cameras").status_code == 404
        assert c.get("/api/health").json()["mode"] == "central"
        # wrong password, then the right one (username is case-insensitive)
        assert c.post("/api/auth/login", json={"username": "jan", "password": "zle"}).status_code == 401
        r = c.post("/api/auth/login", json={"username": "JAN", "password": "dlugie-haslo-1"})
        assert r.status_code == 200 and r.json()["user"]["display_name"] == "Jan Kowalski"
        assert "httponly" in r.headers["set-cookie"].lower()
        assert c.get("/api/fleet/venues").status_code == 200
        # password change keeps this browser signed in, the old password stops working
        assert c.post("/api/auth/password", json={"old_password": "zle", "new_password": "nowe-haslo-22"}).status_code == 400
        assert c.post("/api/auth/password", json={"old_password": "dlugie-haslo-1", "new_password": "krotkie"}).status_code == 400
        assert c.post("/api/auth/password", json={"old_password": "dlugie-haslo-1", "new_password": "nowe-haslo-22"}).status_code == 200
        assert c.get("/api/auth/me").status_code == 200
        assert c.post("/api/auth/logout").status_code == 204
        assert c.get("/api/fleet/venues").status_code == 401
        assert c.post("/api/auth/login", json={"username": "jan", "password": "dlugie-haslo-1"}).status_code == 401


def test_login_is_throttled(tmp_path):
    with TestClient(create_app(_settings(tmp_path))) as c:
        c.app.state.auth.create_user("jan", "dlugie-haslo-1")
        for _ in range(8):
            assert c.post("/api/auth/login", json={"username": "jan", "password": "zle"}).status_code == 401
        # even the right password waits now
        assert c.post("/api/auth/login", json={"username": "jan", "password": "dlugie-haslo-1"}).status_code == 429


def test_board_lifecycle_ingest_and_settlement(client):
    v = _venue(client)
    b = _board(client, v["id"])
    key = b["api_key"]
    assert key.startswith("dsb_") and b["key_prefix"] == key[4:10]
    assert b["online"] is False and b["alerts"][0]["code"] == "never_seen"
    assert "api_key" not in client.get(f"/api/fleet/boards/{b['id']}").json()

    # ingest needs the board's key
    assert client.post("/api/fleet/ingest/heartbeat", json={}).status_code == 401
    assert client.post("/api/fleet/ingest/heartbeat", json={}, headers={"X-Board-Key": "dsb_wrong"}).status_code == 401
    hb = {"version": "1.0.0", "mode": "live", "engine": "idle", "calibration": "ok", "active_game": True,
          "cameras": [{"id": "cam1", "connected": True, "calibrated": True},
                      {"id": "cam2", "connected": False, "calibrated": True}]}
    assert client.post("/api/fleet/ingest/heartbeat", json=hb, headers={"X-Board-Key": key}).json()["ok"]
    board = client.get(f"/api/fleet/boards/{b['id']}").json()
    assert board["online"] and board["level"] == "bad"
    assert [a["code"] for a in board["alerts"]] == ["camera_down"]

    now = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(hours=1)
    games = [_game(i, now - timedelta(minutes=20 * i)) for i in range(3)]
    r = client.post("/api/fleet/ingest/games", json={"games": games}, headers={"X-Board-Key": key})
    assert r.json() == {"accepted": 3, "duplicates": 0}
    r = client.post("/api/fleet/ingest/games", json={"games": games[:2]}, headers={"X-Board-Key": key})
    assert r.json() == {"accepted": 0, "duplicates": 2}

    # price and share are frozen per game: changing the venue's terms does not rewrite history
    client.patch(f"/api/fleet/venues/{v['id']}", json={"price_per_game": 10, "venue_share_pct": 50})
    st = client.get("/api/fleet/stats").json()
    assert st["totals"]["games"] == 3
    assert st["totals"]["revenue"] == 18.0
    assert st["totals"]["venue_share"] == 7.2 and st["totals"]["operator_share"] == 10.8
    assert sum(sum(row) for row in st["heatmap"]) == 3
    assert st["modes"] == [{"mode": "x01", "games": 3}]

    month = now.astimezone().strftime("%Y-%m")
    s = client.get(f"/api/fleet/settlements?month={month}").json()
    if s["totals"]["games"] == 3:  # unless the games straddle a month boundary
        assert s["venues"][0]["venue_share"] == 7.2 and s["venues"][0]["share_pcts"] == [40.0]

    venues = client.get("/api/fleet/venues").json()
    assert venues[0]["games_30d"] == 3 and venues[0]["boards_online"] == 1

    dash = client.get("/api/fleet/dashboard").json()
    assert dash["boards"]["online"] == 1 and dash["boards"]["playing"] == 1
    assert dash["alerts"][0]["code"] == "camera_down"

    # a board with games cannot be deleted, only retired; a retired board cannot report
    assert client.delete(f"/api/fleet/boards/{b['id']}").status_code == 400
    assert client.delete(f"/api/fleet/venues/{v['id']}").status_code == 400
    client.patch(f"/api/fleet/boards/{b['id']}", json={"status": "retired"})
    assert client.post("/api/fleet/ingest/heartbeat", json=hb, headers={"X-Board-Key": key}).status_code == 401

    # key rotation invalidates the old key
    client.patch(f"/api/fleet/boards/{b['id']}", json={"status": "active"})
    new = client.post(f"/api/fleet/boards/{b['id']}/rotate-key").json()["api_key"]
    assert client.post("/api/fleet/ingest/heartbeat", json=hb, headers={"X-Board-Key": key}).status_code == 401
    assert client.post("/api/fleet/ingest/heartbeat", json=hb, headers={"X-Board-Key": new}).status_code == 200


def test_validation(client):
    assert client.post("/api/fleet/venues", json={"name": " "}).status_code == 400
    assert client.post("/api/fleet/venues", json={"name": "X", "venue_share_pct": 120}).status_code == 400
    assert client.post("/api/fleet/venues", json={"name": "X", "lat": 95}).status_code == 400
    assert client.post("/api/fleet/boards", json={"name": "B", "venue_id": "nope"}).status_code == 400
    assert client.get("/api/fleet/stats?from=2026-02-10&to=2026-01-01").status_code == 400
    assert client.get("/api/fleet/settlements?month=2026-13").status_code == 400
    assert client.get("/api/fleet/venues/nope").status_code == 404


def test_tickets(client):
    v = _venue(client)
    b = _board(client, v["id"])
    t = client.post("/api/fleet/tickets", json={"title": "Kamera 2 nie działa", "board_id": b["id"],
                                                "priority": "high", "reporter": "Ania"}).json()
    assert t["venue_id"] == v["id"] and t["status"] == "open" and t["board_name"] == "Tarcza 1"
    t = client.patch(f"/api/fleet/tickets/{t['id']}", json={"status": "in_progress", "assignee": "Marek",
                                                            "comment": "Jadę na miejsce", "author": "Marek"}).json()
    assert t["comments"][0]["status_change"] == "open->in_progress" and t["comments"][0]["text"] == "Jadę na miejsce"
    t = client.post(f"/api/fleet/tickets/{t['id']}/comments", json={"text": "Wymieniony kabel USB", "author": "Marek"}).json()
    t = client.patch(f"/api/fleet/tickets/{t['id']}", json={"status": "closed"}).json()
    assert t["closed_at"] and len(t["comments"]) == 3
    assert client.get("/api/fleet/tickets?status=active").json() == []
    assert len(client.get(f"/api/fleet/tickets?board_id={b['id']}").json()) == 1
    assert client.patch(f"/api/fleet/tickets/{t['id']}", json={"priority": "urgent"}).status_code == 400


def test_board_reporter_sends_heartbeat_and_games_once(client, tmp_path, monkeypatch):
    """The reporter on a board, posting through the test client instead of HTTP."""
    v = _venue(client)
    key = _board(client, v["id"])["api_key"]

    board_db = Database(f"sqlite:///{(tmp_path / 'board.sqlite').as_posix()}")
    board_db.migrate()
    t0 = datetime.now(timezone.utc) - timedelta(hours=2)
    with board_db.session() as s:
        p = Player(name="Ola")
        s.add(p)
        s.flush()
        for i, status in enumerate(("finished", "abandoned", "running")):
            g = Game(mode="cricket", status=status, started_at=t0 + timedelta(minutes=20 * i),
                     finished_at=None if status == "running" else t0 + timedelta(minutes=20 * i + 15))
            g.players = [GamePlayer(player_id=p.id, position=0)]
            s.add(g)

    settings = load_settings(extra={"mode": "live", "fleet": {"url": "http://central", "board_key": key}})
    rep = FleetReporter(settings, board_db, vision=None)
    sent = []

    def post(path, body):
        sent.append(path)
        r = client.post(path, json=body, headers={"X-Board-Key": key})
        assert r.status_code == 200, r.text
        return r.json()

    monkeypatch.setattr(rep, "_post", post)
    rep.report_once()
    assert sent == ["/api/fleet/ingest/heartbeat", "/api/fleet/ingest/games"]
    st = client.get("/api/fleet/stats").json()["totals"]
    assert st["games"] == 2 and st["revenue"] == 12.0

    sent.clear()
    rep.report_once()  # cursor advanced: nothing new to send
    assert sent == ["/api/fleet/ingest/heartbeat"]
    assert client.get("/api/fleet/stats").json()["totals"]["games"] == 2


def test_board_in_maintenance_raises_no_fault_alerts(client):
    b = _board(client)
    client.patch(f"/api/fleet/boards/{b['id']}", json={"status": "maintenance"})
    board = client.get(f"/api/fleet/boards/{b['id']}").json()
    assert [a["code"] for a in board["alerts"]] == ["maintenance"]
    assert client.get("/api/fleet/dashboard").json()["alerts"] == []
