"""Board → central server reporting (``fleet.url`` + ``fleet.board_key`` in the board's config).

Every ``fleet.interval_s`` the board sends a heartbeat with its health and then every game
that ended since the last confirmed report. The cursor (``fleet.cursor`` in the settings
table) only advances after the server accepted a batch, and the server ignores duplicates,
so games played while the internet is down are sent once it is back.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select

from backend import __version__
from backend.database import Database
from backend.database.models import Game, GameAction, Setting
from backend.settings import AppSettings

log = logging.getLogger("backend.fleet")

CURSOR_KEY = "fleet.cursor"
BATCH = 200


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).isoformat()


class FleetReporter:
    def __init__(self, settings: AppSettings, db: Database, vision: Any) -> None:
        self.cfg = settings.fleet
        self.mode = settings.mode
        self.db = db
        self.vision = vision
        self.started = time.monotonic()
        self.last_ok: float | None = None
        self.last_error: str | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.cfg.url and self.cfg.board_key)

    # ------------------------------------------------------------------ payloads
    def heartbeat_payload(self) -> dict[str, Any]:
        v = self.vision
        cams = []
        engine = None
        calibration = None
        if v is not None:
            engine = v.engine.state.value if v.engine else "stopped"
            try:
                status = v.calibration_status()
                overall = v.calibration_overall()
                calibration = overall.get("status")
                health = {h["camera_id"]: h for h in (v.manager.health() if v.manager else [])}
                for cid, st in status.items():
                    pose = st.get("pose")
                    h = health.get(cid) or {}
                    cams.append({"id": cid, "connected": bool(st.get("connected")),
                                 "calibrated": bool(pose and not pose.get("stale")), "fps": h.get("fps")})
            except Exception:  # noqa: BLE001 - health must never break reporting
                log.exception("could not collect board health")
        with self.db.session() as s:
            active = s.scalar(select(func.count()).select_from(Game).where(Game.status == "running")) or 0
        return {"version": __version__, "mode": self.mode, "engine": engine, "calibration": calibration,
                "uptime_s": round(time.monotonic() - self.started), "active_game": active > 0, "cameras": cams}

    def pending_games(self) -> tuple[list[dict[str, Any]], str | None]:
        """Games ended after the cursor (oldest first) and the cursor value after them."""
        with self.db.session() as s:
            row = s.get(Setting, CURSOR_KEY)
            cursor = (row.value or {}).get("finished_at") if row else None
            q = select(Game).where(Game.status.in_(("finished", "abandoned")), Game.finished_at.is_not(None))
            if cursor:
                q = q.where(Game.finished_at > datetime.fromisoformat(cursor))
            games = list(s.scalars(q.order_by(Game.finished_at).limit(BATCH)))
            darts = dict(s.execute(select(GameAction.game_id, func.count()).where(
                GameAction.game_id.in_([g.id for g in games]), GameAction.kind == "dart")
                .group_by(GameAction.game_id)).all())
            out = [{"game_id": g.id, "mode": g.mode, "status": g.status, "players": max(1, len(g.players)),
                    "darts": darts.get(g.id, 0), "started_at": _iso(g.started_at or g.created_at),
                    "finished_at": _iso(g.finished_at)} for g in games]
        return out, (out[-1]["finished_at"] if out else cursor)

    def _save_cursor(self, value: str | None) -> None:
        if not value:
            return
        with self.db.session() as s:
            row = s.get(Setting, CURSOR_KEY)
            if row is None:
                s.add(Setting(key=CURSOR_KEY, value={"finished_at": value}))
            else:
                row.value = {"finished_at": value}

    # ------------------------------------------------------------------ transport
    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        url = self.cfg.url.rstrip("/") + path
        req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
                                     headers={"Content-Type": "application/json", "X-Board-Key": self.cfg.board_key or ""})
        with urllib.request.urlopen(req, timeout=10) as res:  # noqa: S310 - URL comes from the operator's config
            return json.loads(res.read() or b"{}")

    def report_once(self) -> None:
        self._post("/api/fleet/ingest/heartbeat", self.heartbeat_payload())
        while True:
            games, cursor = self.pending_games()
            if not games:
                break
            self._post("/api/fleet/ingest/games", {"games": games})
            self._save_cursor(cursor)
            if len(games) < BATCH:
                break

    async def run(self) -> None:
        if not self.enabled:
            return
        log.info("fleet reporting enabled", extra={"url": self.cfg.url, "interval_s": self.cfg.interval_s})
        while True:
            try:
                await asyncio.to_thread(self.report_once)
                if self.last_error:
                    log.info("fleet server reachable again")
                self.last_ok, self.last_error = time.time(), None
            except (urllib.error.URLError, OSError, ValueError) as e:
                msg = f"{type(e).__name__}: {e}"
                if msg != self.last_error:  # log each distinct failure once
                    log.warning("fleet report failed", extra={"error": msg})
                self.last_error = msg
            except Exception:  # noqa: BLE001
                log.exception("fleet report crashed")
            await asyncio.sleep(self.cfg.interval_s)
