"""Fleet management for the operator's central server (``mode: central``).

Venues (bars, arcades) host boards. Every board reports to the central server with its own
API key: a heartbeat with its health every ``fleet.interval_s`` and a summary of every
finished game. From that the operator gets board health and alerts, usage statistics and
monthly revenue settlements with each venue (price per game and venue share are per venue
and are copied onto every game when it is reported).

Alerts and health are computed on read from the last heartbeat; nothing is stored for them.
Texts are language-neutral codes; the UI translates them.
"""

from __future__ import annotations

import hashlib
import secrets
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.database import Database
from backend.database.models import Board, BoardGame, Ticket, TicketComment, Venue
from backend.settings import FleetSettings


class FleetError(ValueError):
    """Invalid request (bad input, unknown id, conflicting state)."""


class NotFound(FleetError):
    pass


VENUE_KINDS = ("bar", "pub", "arcade", "club", "other")
BOARD_STATUSES = ("active", "maintenance", "retired")
TICKET_STATUSES = ("open", "in_progress", "waiting", "closed")
TICKET_PRIORITIES = ("low", "normal", "high", "critical")
TICKET_CATEGORIES = ("fault", "maintenance", "install", "other")

_VENUE_FIELDS = ("name", "kind", "address", "city", "postal_code", "lat", "lng", "contact_name", "phone", "email",
                 "opening_hours", "price_per_game", "venue_share_pct", "notes", "active")
_BOARD_FIELDS = ("name", "venue_id", "serial", "status", "installed_at", "notes")
_TICKET_FIELDS = ("title", "description", "category", "priority", "status", "assignee", "board_id", "venue_id")


def _utc(dt: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes; everything is stored in UTC."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    dt = _utc(dt)
    return dt.isoformat() if dt else None


def _parse_dt(v: Any) -> datetime | None:
    if v in (None, ""):
        return None
    if isinstance(v, datetime):
        return _utc(v)
    try:
        return _utc(datetime.fromisoformat(str(v).replace("Z", "+00:00")))
    except ValueError as e:
        raise FleetError(f"invalid date: {v}") from e


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def new_board_key() -> tuple[str, str, str]:
    """A new board API key: (key, sha256, short prefix shown in the UI)."""
    key = "dsb_" + secrets.token_urlsafe(24)
    return key, hash_key(key), key[4:10]


def _money(v: float) -> float:
    return round(float(v), 2)


class FleetService:
    def __init__(self, db: Database, cfg: FleetSettings) -> None:
        self.db = db
        self.cfg = cfg
        self.tz = ZoneInfo(cfg.timezone)

    # ------------------------------------------------------------------ helpers
    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _local_day_start(self, d: date) -> datetime:
        return datetime(d.year, d.month, d.day, tzinfo=self.tz).astimezone(timezone.utc)

    def _range(self, date_from: str | None, date_to: str | None, default_days: int = 30) -> tuple[date, date]:
        """Inclusive local-date range; defaults to the last ``default_days`` days."""
        today = self._now().astimezone(self.tz).date()
        try:
            d1 = date.fromisoformat(date_to) if date_to else today
            d0 = date.fromisoformat(date_from) if date_from else d1 - timedelta(days=default_days - 1)
        except ValueError as e:
            raise FleetError("dates must be YYYY-MM-DD") from e
        if d0 > d1:
            raise FleetError("date_from is after date_to")
        if (d1 - d0).days > 3660:
            raise FleetError("range too long")
        return d0, d1

    def _games(self, s: Session, d0: date, d1: date, venue_id: str | None = None, board_id: str | None = None):
        q = select(BoardGame.started_at, BoardGame.venue_id, BoardGame.board_id, BoardGame.mode, BoardGame.price,
                   BoardGame.venue_share_pct, BoardGame.darts, BoardGame.duration_s, BoardGame.players).where(
            BoardGame.started_at >= self._local_day_start(d0),
            BoardGame.started_at < self._local_day_start(d1 + timedelta(days=1)))
        if venue_id:
            q = q.where(BoardGame.venue_id == venue_id)
        if board_id:
            q = q.where(BoardGame.board_id == board_id)
        return s.execute(q).all()

    # ------------------------------------------------------------------ board health
    def board_health(self, b: Board) -> dict[str, Any]:
        """Online state and alerts from the last heartbeat."""
        now = self._now()
        seen = _utc(b.last_seen_at)
        online = seen is not None and (now - seen).total_seconds() <= self.cfg.offline_after_s
        st = b.last_status or {}
        alerts: list[dict[str, Any]] = []
        if b.status == "retired":
            return {"online": online, "alerts": [], "level": "retired"}
        if b.status == "maintenance":
            # Expected to be off or misbehaving while serviced: no fault alerts.
            return {"online": online, "alerts": [{"code": "maintenance", "severity": "info"}], "level": "warn"}
        if seen is None:
            alerts.append({"code": "never_seen", "severity": "warn"})
        elif not online:
            alerts.append({"code": "offline", "severity": "bad", "since": _iso(seen)})
        if online:
            cams = st.get("cameras") or []
            down = [c.get("id") for c in cams if not c.get("connected")]
            if down:
                alerts.append({"code": "camera_down", "severity": "bad", "cameras": down})
            uncal = [c.get("id") for c in cams if c.get("connected") and not c.get("calibrated")]
            if uncal:
                alerts.append({"code": "uncalibrated", "severity": "warn", "cameras": uncal})
            if st.get("calibration") in ("warning", "moved"):
                alerts.append({"code": "calibration_drift", "severity": "warn", "status": st.get("calibration")})
            if st.get("engine") in ("stopped", None) and st.get("mode") != "simulator":
                alerts.append({"code": "engine_stopped", "severity": "bad"})
        severities = {a["severity"] for a in alerts}
        level = "bad" if "bad" in severities else "warn" if "warn" in severities else "ok"
        return {"online": online, "alerts": alerts, "level": level}

    def _board_dict(self, b: Board, venue: Venue | None = None) -> dict[str, Any]:
        st = b.last_status or {}
        return {
            "id": b.id, "name": b.name, "serial": b.serial, "status": b.status, "venue_id": b.venue_id,
            "venue_name": venue.name if venue else None, "venue_city": venue.city if venue else None,
            "key_prefix": b.key_prefix, "installed_at": _iso(b.installed_at), "last_seen_at": _iso(b.last_seen_at),
            "version": st.get("version"), "engine": st.get("engine"), "cameras": st.get("cameras") or [],
            "active_game": st.get("active_game"), "uptime_s": st.get("uptime_s"), "mode": st.get("mode"),
            "notes": b.notes, "created_at": _iso(b.created_at), **self.board_health(b),
        }

    # ------------------------------------------------------------------ venues
    @staticmethod
    def _venue_dict(v: Venue) -> dict[str, Any]:
        return {k: getattr(v, k) for k in ("id", *_VENUE_FIELDS)} | {"created_at": _iso(v.created_at)}

    def _check_venue(self, data: dict[str, Any]) -> dict[str, Any]:
        out = {k: v for k, v in data.items() if k in _VENUE_FIELDS}
        if "name" in out and not str(out["name"]).strip():
            raise FleetError("name is required")
        if "kind" in out and out["kind"] not in VENUE_KINDS:
            raise FleetError(f"kind must be one of {VENUE_KINDS}")
        if out.get("price_per_game") is not None and float(out["price_per_game"]) < 0:
            raise FleetError("price_per_game must be >= 0")
        if out.get("venue_share_pct") is not None and not 0 <= float(out["venue_share_pct"]) <= 100:
            raise FleetError("venue_share_pct must be between 0 and 100")
        for k, lo, hi in (("lat", -90, 90), ("lng", -180, 180)):
            if out.get(k) is not None and not lo <= float(out[k]) <= hi:
                raise FleetError(f"{k} out of range")
        return out

    def list_venues(self, include_inactive: bool = True) -> list[dict[str, Any]]:
        d0, d1 = self._range(None, None, 30)
        with self.db.session() as s:
            q = select(Venue).order_by(Venue.city, Venue.name)
            if not include_inactive:
                q = q.where(Venue.active.is_(True))
            venues = list(s.scalars(q))
            boards = list(s.scalars(select(Board).where(Board.status != "retired")))
            games = self._games(s, d0, d1)
            tickets = Counter(s.scalars(select(Ticket.venue_id).where(Ticket.status != "closed")))
        per_games: dict[str, list] = defaultdict(list)
        for g in games:
            per_games[g.venue_id].append(g)
        per_boards: dict[str, list[Board]] = defaultdict(list)
        for b in boards:
            per_boards[b.venue_id].append(b)
        out = []
        for v in venues:
            bs = per_boards.get(v.id, [])
            health = [self.board_health(b) for b in bs]
            gs = per_games.get(v.id, [])
            revenue = sum(g.price for g in gs)
            out.append(self._venue_dict(v) | {
                "boards": len(bs), "boards_online": sum(h["online"] for h in health),
                "alerts": sum(1 for h in health if h["level"] in ("bad", "warn")),
                "games_30d": len(gs), "revenue_30d": _money(revenue),
                "open_tickets": tickets.get(v.id, 0),
            })
        return out

    def get_venue(self, venue_id: str) -> dict[str, Any]:
        with self.db.session() as s:
            v = s.get(Venue, venue_id)
            if v is None:
                raise NotFound("venue not found")
            boards = [self._board_dict(b, v) for b in s.scalars(select(Board).where(Board.venue_id == v.id).order_by(Board.name))]
            return self._venue_dict(v) | {"board_list": boards}

    def create_venue(self, data: dict[str, Any]) -> dict[str, Any]:
        out = self._check_venue(data)
        if not out.get("name"):
            raise FleetError("name is required")
        with self.db.session() as s:
            v = Venue(**out)
            s.add(v)
            s.flush()
            return self._venue_dict(v)

    def update_venue(self, venue_id: str, data: dict[str, Any]) -> dict[str, Any]:
        out = self._check_venue(data)
        with self.db.session() as s:
            v = s.get(Venue, venue_id)
            if v is None:
                raise NotFound("venue not found")
            for k, val in out.items():
                setattr(v, k, val)
            s.flush()
            return self._venue_dict(v)

    def delete_venue(self, venue_id: str) -> None:
        with self.db.session() as s:
            v = s.get(Venue, venue_id)
            if v is None:
                raise NotFound("venue not found")
            if s.scalar(select(func.count()).select_from(BoardGame).where(BoardGame.venue_id == venue_id)):
                raise FleetError("venue has recorded games; deactivate it instead")
            if s.scalar(select(func.count()).select_from(Board).where(Board.venue_id == venue_id)):
                raise FleetError("move or remove the venue's boards first")
            s.delete(v)

    # ------------------------------------------------------------------ boards
    def list_boards(self) -> list[dict[str, Any]]:
        with self.db.session() as s:
            venues = {v.id: v for v in s.scalars(select(Venue))}
            boards = list(s.scalars(select(Board).order_by(Board.name)))
            since = self._now() - timedelta(days=30)
            counts = dict(s.execute(select(BoardGame.board_id, func.count()).where(BoardGame.started_at >= since)
                                    .group_by(BoardGame.board_id)).all())
            last_game = dict(s.execute(select(BoardGame.board_id, func.max(BoardGame.started_at))
                                       .group_by(BoardGame.board_id)).all())
            tickets = Counter(s.scalars(select(Ticket.board_id).where(Ticket.status != "closed")))
        return [self._board_dict(b, venues.get(b.venue_id)) | {
            "games_30d": counts.get(b.id, 0), "last_game_at": _iso(last_game.get(b.id)),
            "open_tickets": tickets.get(b.id, 0)} for b in boards]

    def get_board(self, board_id: str) -> dict[str, Any]:
        with self.db.session() as s:
            b = s.get(Board, board_id)
            if b is None:
                raise NotFound("board not found")
            venue = s.get(Venue, b.venue_id) if b.venue_id else None
            recent = s.scalars(select(BoardGame).where(BoardGame.board_id == b.id)
                               .order_by(BoardGame.started_at.desc()).limit(25))
            games = [{"game_id": g.game_id, "mode": g.mode, "status": g.status, "players": g.players, "darts": g.darts,
                      "started_at": _iso(g.started_at), "duration_s": g.duration_s, "price": g.price} for g in recent]
            return self._board_dict(b, venue) | {"recent_games": games, "raw_status": b.last_status or {}}

    def _check_board(self, s: Session, data: dict[str, Any]) -> dict[str, Any]:
        out = {k: v for k, v in data.items() if k in _BOARD_FIELDS}
        if "name" in out and not str(out["name"]).strip():
            raise FleetError("name is required")
        if "status" in out and out["status"] not in BOARD_STATUSES:
            raise FleetError(f"status must be one of {BOARD_STATUSES}")
        if out.get("venue_id") and s.get(Venue, out["venue_id"]) is None:
            raise FleetError("unknown venue")
        if "installed_at" in out:
            out["installed_at"] = _parse_dt(out["installed_at"])
        if "venue_id" in out and not out["venue_id"]:
            out["venue_id"] = None
        return out

    def create_board(self, data: dict[str, Any]) -> dict[str, Any]:
        """Register a board. The returned ``api_key`` is shown only once."""
        key, digest, prefix = new_board_key()
        with self.db.session() as s:
            out = self._check_board(s, data)
            if not out.get("name"):
                raise FleetError("name is required")
            if out.get("venue_id") and not out.get("installed_at"):
                out["installed_at"] = self._now()
            b = Board(**out, key_hash=digest, key_prefix=prefix)
            s.add(b)
            s.flush()
            venue = s.get(Venue, b.venue_id) if b.venue_id else None
            return self._board_dict(b, venue) | {"api_key": key}

    def update_board(self, board_id: str, data: dict[str, Any]) -> dict[str, Any]:
        with self.db.session() as s:
            b = s.get(Board, board_id)
            if b is None:
                raise NotFound("board not found")
            out = self._check_board(s, data)
            if "venue_id" in out and out["venue_id"] != b.venue_id and out["venue_id"] and "installed_at" not in out:
                out["installed_at"] = self._now()
            for k, val in out.items():
                setattr(b, k, val)
            s.flush()
            return self._board_dict(b, s.get(Venue, b.venue_id) if b.venue_id else None)

    def rotate_key(self, board_id: str) -> dict[str, Any]:
        key, digest, prefix = new_board_key()
        with self.db.session() as s:
            b = s.get(Board, board_id)
            if b is None:
                raise NotFound("board not found")
            b.key_hash, b.key_prefix = digest, prefix
            return {"id": b.id, "api_key": key, "key_prefix": prefix}

    def delete_board(self, board_id: str) -> None:
        with self.db.session() as s:
            b = s.get(Board, board_id)
            if b is None:
                raise NotFound("board not found")
            if s.scalar(select(func.count()).select_from(BoardGame).where(BoardGame.board_id == board_id)):
                raise FleetError("board has recorded games; retire it instead")
            s.delete(b)

    # ------------------------------------------------------------------ ingest (boards → central)
    def authenticate(self, key: str | None) -> str:
        """Board id for an API key."""
        if not key:
            raise PermissionError("missing board key")
        with self.db.session() as s:
            b = s.scalar(select(Board).where(Board.key_hash == hash_key(key)))
            if b is None:
                raise PermissionError("unknown board key")
            if b.status == "retired":
                raise PermissionError("board is retired")
            return b.id

    def heartbeat(self, board_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        cams = [{"id": str(c.get("id", ""))[:32], "connected": bool(c.get("connected")),
                 "calibrated": bool(c.get("calibrated")), "fps": c.get("fps")}
                for c in (payload.get("cameras") or [])[:8] if isinstance(c, dict)]
        status = {k: payload.get(k) for k in ("version", "mode", "engine", "calibration", "uptime_s", "active_game")}
        status["cameras"] = cams
        with self.db.session() as s:
            b = s.get(Board, board_id)
            b.last_seen_at = self._now()
            b.last_status = status
            return {"ok": True, "interval_s": self.cfg.interval_s, "server_time": _iso(b.last_seen_at)}

    def ingest_games(self, board_id: str, games: list[dict[str, Any]]) -> dict[str, Any]:
        accepted = duplicates = 0
        with self.db.session() as s:
            b = s.get(Board, board_id)
            venue = s.get(Venue, b.venue_id) if b.venue_id else None
            known = set(s.scalars(select(BoardGame.game_id).where(
                BoardGame.board_id == board_id, BoardGame.game_id.in_([str(g.get("game_id")) for g in games]))))
            for g in games:
                gid = str(g.get("game_id") or "")[:32]
                started = _parse_dt(g.get("started_at"))
                if not gid or started is None:
                    raise FleetError("each game needs game_id and started_at")
                if gid in known:
                    duplicates += 1
                    continue
                finished = _parse_dt(g.get("finished_at"))
                s.add(BoardGame(
                    board_id=board_id, venue_id=venue.id if venue else None, game_id=gid,
                    mode=str(g.get("mode") or "unknown")[:32],
                    status="abandoned" if g.get("status") == "abandoned" else "finished",
                    players=max(1, int(g.get("players") or 1)), darts=max(0, int(g.get("darts") or 0)),
                    started_at=started, finished_at=finished,
                    duration_s=int((finished - started).total_seconds()) if finished else 0,
                    # Games on a board not installed in a venue (testing, warehouse) are free.
                    price=venue.price_per_game if venue else 0.0,
                    venue_share_pct=venue.venue_share_pct if venue else 0.0))
                known.add(gid)
                accepted += 1
            b.last_seen_at = self._now()
        return {"accepted": accepted, "duplicates": duplicates}

    # ------------------------------------------------------------------ tickets
    @staticmethod
    def _ticket_dict(t: Ticket, venues: dict[str, Venue], boards: dict[str, Board], comments: bool = False) -> dict[str, Any]:
        v = venues.get(t.venue_id) if t.venue_id else None
        b = boards.get(t.board_id) if t.board_id else None
        d = {k: getattr(t, k) for k in ("id", *_TICKET_FIELDS, "reporter")} | {
            "venue_name": v.name if v else None, "board_name": b.name if b else None,
            "created_at": _iso(t.created_at), "updated_at": _iso(t.updated_at), "closed_at": _iso(t.closed_at)}
        if comments:
            d["comments"] = [{"id": c.id, "author": c.author, "text": c.text, "status_change": c.status_change,
                              "created_at": _iso(c.created_at)} for c in t.comments]
        return d

    def _lookups(self, s: Session) -> tuple[dict[str, Venue], dict[str, Board]]:
        return {v.id: v for v in s.scalars(select(Venue))}, {b.id: b for b in s.scalars(select(Board))}

    def _check_ticket(self, s: Session, data: dict[str, Any]) -> dict[str, Any]:
        out = {k: v for k, v in data.items() if k in _TICKET_FIELDS}
        for k, allowed in (("status", TICKET_STATUSES), ("priority", TICKET_PRIORITIES), ("category", TICKET_CATEGORIES)):
            if k in out and out[k] not in allowed:
                raise FleetError(f"{k} must be one of {allowed}")
        if "title" in out and not str(out["title"]).strip():
            raise FleetError("title is required")
        if out.get("board_id"):
            b = s.get(Board, out["board_id"])
            if b is None:
                raise FleetError("unknown board")
            out.setdefault("venue_id", b.venue_id)
        if out.get("venue_id") and s.get(Venue, out["venue_id"]) is None:
            raise FleetError("unknown venue")
        return out

    def list_tickets(self, status: str | None = None, venue_id: str | None = None,
                     board_id: str | None = None) -> list[dict[str, Any]]:
        with self.db.session() as s:
            q = select(Ticket).order_by(Ticket.created_at.desc())
            if status == "active":
                q = q.where(Ticket.status != "closed")
            elif status:
                q = q.where(Ticket.status == status)
            if venue_id:
                q = q.where(Ticket.venue_id == venue_id)
            if board_id:
                q = q.where(Ticket.board_id == board_id)
            venues, boards = self._lookups(s)
            return [self._ticket_dict(t, venues, boards) for t in s.scalars(q.limit(500))]

    def get_ticket(self, ticket_id: int) -> dict[str, Any]:
        with self.db.session() as s:
            t = s.get(Ticket, ticket_id)
            if t is None:
                raise NotFound("ticket not found")
            venues, boards = self._lookups(s)
            return self._ticket_dict(t, venues, boards, comments=True)

    def create_ticket(self, data: dict[str, Any]) -> dict[str, Any]:
        with self.db.session() as s:
            out = self._check_ticket(s, data)
            if not out.get("title"):
                raise FleetError("title is required")
            t = Ticket(**out, reporter=str(data.get("reporter") or "")[:80])
            if t.status == "closed":
                t.closed_at = self._now()
            s.add(t)
            s.flush()
            tid = t.id
        return self.get_ticket(tid)

    def update_ticket(self, ticket_id: int, data: dict[str, Any]) -> dict[str, Any]:
        """Change fields; a status change (and an optional ``comment``) is logged as a comment."""
        with self.db.session() as s:
            t = s.get(Ticket, ticket_id)
            if t is None:
                raise NotFound("ticket not found")
            out = self._check_ticket(s, data)
            change = ""
            if "status" in out and out["status"] != t.status:
                change = f"{t.status}->{out['status']}"
                t.closed_at = self._now() if out["status"] == "closed" else None
            for k, val in out.items():
                setattr(t, k, val)
            text = str(data.get("comment") or "").strip()
            if change or text:
                s.add(TicketComment(ticket_id=t.id, author=str(data.get("author") or "")[:80], text=text,
                                    status_change=change))
            t.updated_at = self._now()
        return self.get_ticket(ticket_id)

    def add_comment(self, ticket_id: int, author: str, text: str) -> dict[str, Any]:
        if not text.strip():
            raise FleetError("comment is empty")
        with self.db.session() as s:
            t = s.get(Ticket, ticket_id)
            if t is None:
                raise NotFound("ticket not found")
            s.add(TicketComment(ticket_id=t.id, author=author[:80], text=text.strip()))
            t.updated_at = self._now()
        return self.get_ticket(ticket_id)

    # ------------------------------------------------------------------ statistics
    def stats(self, date_from: str | None = None, date_to: str | None = None, venue_id: str | None = None,
              board_id: str | None = None) -> dict[str, Any]:
        d0, d1 = self._range(date_from, date_to, 30)
        with self.db.session() as s:
            rows = self._games(s, d0, d1, venue_id, board_id)
            venues = {v.id: v for v in s.scalars(select(Venue))}
            boards = {b.id: b for b in s.scalars(select(Board))}
        days = (d1 - d0).days + 1
        daily = {d0 + timedelta(days=i): {"games": 0, "revenue": 0.0} for i in range(days)}
        heat = [[0] * 24 for _ in range(7)]
        modes: Counter = Counter()
        per_venue: dict[str | None, dict[str, float]] = defaultdict(lambda: {"games": 0, "revenue": 0.0, "venue_share": 0.0})
        per_board: Counter = Counter()
        revenue = venue_share = 0.0
        darts = duration = players = 0
        for g in rows:
            local = _utc(g.started_at).astimezone(self.tz)
            day = daily.get(local.date())
            if day is not None:
                day["games"] += 1
                day["revenue"] += g.price
            heat[local.weekday()][local.hour] += 1
            modes[g.mode] += 1
            share = g.price * g.venue_share_pct / 100
            pv = per_venue[g.venue_id]
            pv["games"] += 1
            pv["revenue"] += g.price
            pv["venue_share"] += share
            per_board[g.board_id] += 1
            revenue += g.price
            venue_share += share
            darts += g.darts
            duration += g.duration_s
            players += g.players
        n = len(rows)
        return {
            "from": d0.isoformat(), "to": d1.isoformat(), "currency": self.cfg.currency, "timezone": self.cfg.timezone,
            "totals": {"games": n, "revenue": _money(revenue), "venue_share": _money(venue_share),
                       "operator_share": _money(revenue - venue_share), "darts": darts,
                       "avg_duration_s": round(duration / n) if n else 0,
                       "avg_players": round(players / n, 2) if n else 0,
                       "games_per_day": round(n / days, 1)},
            "daily": [{"date": d.isoformat(), "games": v["games"], "revenue": _money(v["revenue"])} for d, v in daily.items()],
            "heatmap": heat,  # [weekday Mon=0][hour] in local time
            "modes": [{"mode": m, "games": c} for m, c in modes.most_common()],
            "by_venue": sorted([{"venue_id": vid, "name": venues[vid].name if vid in venues else None,
                                 "city": venues[vid].city if vid in venues else None, "games": int(v["games"]),
                                 "revenue": _money(v["revenue"]), "venue_share": _money(v["venue_share"])}
                                for vid, v in per_venue.items()], key=lambda r: -r["revenue"]),
            "by_board": [{"board_id": bid, "name": boards[bid].name if bid in boards else bid, "games": c,
                          "venue_name": venues[boards[bid].venue_id].name
                          if bid in boards and boards[bid].venue_id in venues else None}
                         for bid, c in per_board.most_common(15)],
        }

    def settlement(self, month: str | None = None) -> dict[str, Any]:
        """Revenue split with every venue for one calendar month (local time)."""
        today = self._now().astimezone(self.tz).date()
        try:
            y, m = (int(x) for x in month.split("-")) if month else (today.year, today.month)
            first = date(y, m, 1)
        except (ValueError, TypeError) as e:
            raise FleetError("month must be YYYY-MM") from e
        last = (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1))
        with self.db.session() as s:
            rows = self._games(s, first, last)
            venues = {v.id: v for v in s.scalars(select(Venue))}
        agg: dict[str | None, dict[str, Any]] = {}
        for g in rows:
            a = agg.setdefault(g.venue_id, {"games": 0, "revenue": 0.0, "venue_share": 0.0, "prices": set(), "pcts": set()})
            a["games"] += 1
            a["revenue"] += g.price
            a["venue_share"] += g.price * g.venue_share_pct / 100
            a["prices"].add(g.price)
            a["pcts"].add(g.venue_share_pct)
        out = []
        for vid, a in agg.items():
            v = venues.get(vid)
            if v is None and a["revenue"] == 0:
                continue  # free games on boards outside venues
            out.append({"venue_id": vid, "name": v.name if v else None, "city": v.city if v else None,
                        "games": a["games"], "revenue": _money(a["revenue"]), "venue_share": _money(a["venue_share"]),
                        "operator_share": _money(a["revenue"] - a["venue_share"]),
                        "prices": sorted(a["prices"]), "share_pcts": sorted(a["pcts"])})
        out.sort(key=lambda r: -r["revenue"])
        tot = {k: _money(sum(r[k] for r in out)) for k in ("revenue", "venue_share", "operator_share")}
        tot["games"] = sum(r["games"] for r in out)
        return {"month": f"{y:04d}-{m:02d}", "from": first.isoformat(), "to": last.isoformat(),
                "currency": self.cfg.currency, "venues": out, "totals": tot}

    def dashboard(self) -> dict[str, Any]:
        boards = self.list_boards()
        live = [b for b in boards if b["status"] != "retired"]
        last30 = self.stats()
        today = self._now().astimezone(self.tz).date()
        d_today = self.stats(today.isoformat(), today.isoformat())["totals"]
        prev = self.stats((today - timedelta(days=59)).isoformat(), (today - timedelta(days=30)).isoformat())["totals"]
        with self.db.session() as s:
            open_by_prio = dict(s.execute(select(Ticket.priority, func.count()).where(Ticket.status != "closed")
                                          .group_by(Ticket.priority)).all())
            venues_active = s.scalar(select(func.count()).select_from(Venue).where(Venue.active.is_(True))) or 0
        alerts = [{"board_id": b["id"], "board_name": b["name"], "venue_id": b["venue_id"], "venue_name": b["venue_name"],
                   **a} for b in live for a in b["alerts"] if a["severity"] != "info"]
        alerts.sort(key=lambda a: 0 if a["severity"] == "bad" else 1)
        return {
            "currency": self.cfg.currency,
            "venues_active": venues_active,
            "boards": {"total": len(live), "online": sum(b["online"] for b in live),
                       "offline": sum(1 for b in live if not b["online"]),
                       "maintenance": sum(1 for b in live if b["status"] == "maintenance"),
                       "playing": sum(1 for b in live if b["online"] and b["active_game"])},
            "today": d_today,
            "last_30d": last30["totals"], "prev_30d": prev,
            "daily": last30["daily"],
            "top_venues": last30["by_venue"][:5],
            "open_tickets": open_by_prio, "open_tickets_total": sum(open_by_prio.values()),
            "alerts": alerts[:50],
        }
