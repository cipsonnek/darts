"""Binds the game engine to persistence, detections and the live event stream.

Flow of a detected dart:
    vision event ──▶ Detection row ──▶ (active game?) ──▶ confident and nothing pending?
                                                         ├─ yes: GameAction(dart) → replay → publish
                                                         └─ no:  detection 'pending' → UI asks the user
Corrections never modify earlier rows: they append a ``correct``/``void_dart`` action and a
Correction row, and the state is recomputed by replay.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select

from backend.database import Database
from backend.database.models import Correction, Detection, EventLog, Game, GameAction, GamePlayer, Player
from backend.game_engine import Action, Dart, GameError, get_mode, list_modes, replay
from backend.ws.hub import EventHub
from vision.events import EventType, VisionEvent
from vision.geometry.board import DartScore

log = logging.getLogger("backend.games")

_ACTIVE = ("running", "paused")


def dart_from_label(label: str, dart_id: str = "") -> Dart:
    s = DartScore.from_label(label)
    return Dart(s.sector, s.multiplier if s.sector else 0, dart_id)


class GameService:
    def __init__(self, db: Database, hub: EventHub) -> None:
        self.db = db
        self.hub = hub
        self._lock = threading.RLock()
        self.vision = None  # set by the app (VisionService), optional

    # ------------------------------------------------------------------ modes / players
    @staticmethod
    def modes() -> list[dict]:
        return list_modes()

    def list_players(self, include_archived: bool = False) -> list[dict]:
        with self.db.session() as s:
            q = select(Player).order_by(Player.name)
            if not include_archived:
                q = q.where(Player.archived.is_(False))
            return [_player_dict(p) for p in s.scalars(q)]

    def create_player(self, name: str, nickname: str | None = None, color: str | None = None,
                      avatar: str | None = None) -> dict:
        name = name.strip()
        if not name:
            raise GameError("name is required")
        with self.db.session() as s:
            if s.scalar(select(Player).where(func.lower(Player.name) == name.lower())):
                raise GameError("a player with this name already exists")
            p = Player(name=name[:64], nickname=(nickname or None), color=color or "#e8324a", avatar=avatar)
            s.add(p)
            s.flush()
            return _player_dict(p)

    def update_player(self, player_id: str, **fields: Any) -> dict:
        with self.db.session() as s:
            p = s.get(Player, player_id)
            if p is None:
                raise KeyError(player_id)
            for k in ("name", "nickname", "color", "avatar", "archived"):
                if k in fields and fields[k] is not None:
                    setattr(p, k, fields[k])
            s.flush()
            return _player_dict(p)

    def get_player(self, player_id: str) -> dict:
        with self.db.session() as s:
            p = s.get(Player, player_id)
            if p is None:
                raise KeyError(player_id)
            return _player_dict(p)

    # ------------------------------------------------------------------ games
    def create_game(self, mode: str, settings: dict[str, Any], player_ids: list[str], start: bool = True) -> dict:
        m = get_mode(mode)
        norm = m.normalize_settings(settings)
        if not player_ids:
            raise GameError("select at least one player")
        if len(set(player_ids)) != len(player_ids):
            raise GameError("a player can only appear once")
        with self._lock, self.db.session() as s:
            for pid in player_ids:
                if s.get(Player, pid) is None:
                    raise GameError(f"unknown player {pid}")
            if start:
                for g in s.scalars(select(Game).where(Game.status.in_(_ACTIVE))):
                    g.status = "paused"
            g = Game(mode=mode, settings=norm, status="running" if start else "created",
                     started_at=datetime.now(timezone.utc) if start else None)
            g.players = [GamePlayer(player_id=pid, position=i) for i, pid in enumerate(player_ids)]
            s.add(g)
            s.flush()
            gid = g.id
        state = self._recompute(gid)
        self.hub.publish("game", "game_created", state)
        return state

    def list_games(self, status: str | None = None, limit: int = 50) -> list[dict]:
        with self.db.session() as s:
            q = select(Game).order_by(Game.created_at.desc()).limit(min(limit, 500))
            if status:
                q = q.where(Game.status == status)
            return [self._summary(s, g) for g in s.scalars(q)]

    def active_game_id(self) -> str | None:
        with self.db.session() as s:
            g = s.scalar(select(Game).where(Game.status == "running").order_by(Game.started_at.desc()))
            return g.id if g else None

    def get_game(self, game_id: str) -> dict:
        with self.db.session() as s:
            g = s.get(Game, game_id)
            if g is None:
                raise KeyError(game_id)
            if g.state_cache is None:
                pass
        return self._recompute(game_id, persist=False)

    def set_status(self, game_id: str, status: str) -> dict:
        if status not in ("running", "paused", "finished", "abandoned"):
            raise GameError("invalid status")
        with self._lock, self.db.session() as s:
            g = s.get(Game, game_id)
            if g is None:
                raise KeyError(game_id)
            if g.status in ("finished", "abandoned") and status in ("running", "paused"):
                raise GameError("the game is over")
            if status == "running":
                for other in s.scalars(select(Game).where(Game.status == "running", Game.id != game_id)):
                    other.status = "paused"
                if g.started_at is None:
                    g.started_at = datetime.now(timezone.utc)
            if status in ("finished", "abandoned"):
                g.finished_at = datetime.now(timezone.utc)
            g.status = status
        state = self._recompute(game_id)
        self.hub.publish("game", "game_status", {"game_id": game_id, "status": status})
        return state

    def delete_game(self, game_id: str) -> None:
        with self._lock, self.db.session() as s:
            g = s.get(Game, game_id)
            if g is None:
                raise KeyError(game_id)
            s.query(GameAction).filter(GameAction.game_id == game_id).delete()
            s.delete(g)

    # ------------------------------------------------------------------ actions
    def _append(self, s, game_id: str, kind: str, dart: Dart | None = None, target: str | None = None,
                source: str = "manual", payload: dict | None = None, player_id: str | None = None) -> None:
        seq = (s.scalar(select(func.max(GameAction.seq)).where(GameAction.game_id == game_id)) or 0) + 1
        s.add(GameAction(game_id=game_id, seq=seq, kind=kind,
                         sector=dart.sector if dart else None, multiplier=dart.multiplier if dart else None,
                         dart_id=dart.dart_id if dart and dart.dart_id else None, target_dart_id=target,
                         source=source, payload=payload or {}, player_id=player_id))

    def _require_running(self, s, game_id: str) -> Game:
        g = s.get(Game, game_id)
        if g is None:
            raise KeyError(game_id)
        if g.status != "running":
            raise GameError(f"the game is {g.status}")
        return g

    def throw(self, game_id: str, label: str, source: str = "manual", dart_id: str | None = None) -> dict:
        import uuid

        dart = dart_from_label(label, dart_id or ("m" + uuid.uuid4().hex[:15]))
        with self._lock:
            with self.db.session() as s:
                self._require_running(s, game_id)
                self._append(s, game_id, "dart", dart, source=source, player_id=self._next_player_id(game_id))
            state = self._recompute(game_id)
        self._publish_state(state)
        return state

    def undo(self, game_id: str) -> dict:
        with self._lock:
            with self.db.session() as s:
                self._require_running(s, game_id)
                self._append(s, game_id, "undo")
            state = self._recompute(game_id)
        self._publish_state(state)
        return state

    def next_turn(self, game_id: str, source: str = "manual") -> dict:
        with self._lock:
            with self.db.session() as s:
                self._require_running(s, game_id)
                self._append(s, game_id, "next_turn", source=source)
            state = self._recompute(game_id)
        self._publish_state(state)
        return state

    def correct(self, game_id: str, dart_id: str, label: str, x_mm: float | None = None,
                y_mm: float | None = None, note: str | None = None) -> dict:
        """Change the value of a dart already in the game (history kept)."""
        with self._lock:
            with self.db.session() as s:
                g = s.get(Game, game_id)
                if g is None:
                    raise KeyError(game_id)
                orig = s.scalar(select(GameAction).where(GameAction.game_id == game_id, GameAction.kind == "dart",
                                                         GameAction.dart_id == dart_id))
                if orig is None:
                    raise GameError("no such dart in this game")
                new = dart_from_label(label, dart_id)
                if label.upper() == "VOID":
                    self._append(s, game_id, "void_dart", target=dart_id)
                else:
                    self._append(s, game_id, "correct", new, target=dart_id)
                old_label = Dart(orig.sector or 0, orig.multiplier or 0).label
                s.add(Correction(detection_id=dart_id, game_id=game_id, original_label=old_label,
                                 corrected_label=label.upper(), reason="manual", x_mm=x_mm, y_mm=y_mm, note=note))
                det = s.get(Detection, dart_id)
                if det is not None:
                    det.status = "resolved"
                    det.final_label = label.upper()
                self._relabel(dart_id, label.upper())
            state = self._recompute(game_id)
        self._publish_state(state)
        return state

    def _relabel(self, dart_id: str, label: str) -> None:
        if self.vision is not None and self.vision.engine is not None:
            self.vision.engine.relabel_dart(dart_id, label)
        self.hub.publish("events", "dart_relabelled", {"dart_id": dart_id, "label": label})

    def _next_player_id(self, game_id: str) -> str | None:
        st = self._recompute(game_id, persist=False)
        idx = st["state"]["current_player"]
        if st["state"]["awaiting_takeout"]:
            idx = (idx + 1) % len(st["players"])
        return st["players"][idx]["id"] if st["players"] else None

    # ------------------------------------------------------------------ vision integration
    def on_vision_event(self, ev: VisionEvent) -> None:
        """Called (from a worker thread) for every engine event."""
        try:
            if ev.type == EventType.DART:
                self._on_dart(ev.data)
            elif ev.type == EventType.DARTS_REMOVED:
                self._on_takeout(ev.data)
            elif ev.type in (EventType.OBSTRUCTION, EventType.UNRECOGNIZED, EventType.NO_CHANGE, EventType.ERROR,
                             EventType.BOARD_CLEAR, EventType.CALIBRATION, EventType.DART_MOVED, EventType.BASELINE):
                with self.db.session() as s:
                    s.add(EventLog(type=ev.type, data=ev.data))
        except Exception:  # noqa: BLE001
            log.exception("failed to handle vision event", extra={"type": ev.type})

    def _on_dart(self, d: dict) -> None:
        with self._lock:
            gid = self.active_game_id()
            with self.db.session() as s:
                pending = 0
                if gid is not None:
                    pending = s.scalar(select(func.count()).select_from(Detection).where(
                        Detection.game_id == gid, Detection.status.in_(("pending", "queued")))) or 0
                status = "unassigned"
                if gid is not None:
                    status = "pending" if d["uncertain"] else ("queued" if pending else "accepted")
                player_id = self._next_player_id(gid) if gid else None
                det = Detection(id=d["dart_id"], game_id=gid, player_id=player_id, sector=d["score"]["sector"],
                                multiplier=d["score"]["multiplier"], score=d["score"]["score"],
                                label=d["score"]["label"], x_mm=d["impact"]["x_mm"], y_mm=d["impact"]["y_mm"],
                                confidence=d["confidence"]["overall"], uncertain=d["uncertain"], status=status,
                                payload=d)
                s.add(det)
                if status == "accepted":
                    self._append(s, gid, "dart", Dart(d["score"]["sector"], d["score"]["multiplier"], d["dart_id"]),
                                 source="vision", player_id=player_id)
            if gid is not None:
                state = self._recompute(gid)
                self._publish_state(state)
                if status == "pending":
                    self.hub.publish("game", "dart_uncertain", {"game_id": gid, "detection": d})

    def pending(self, game_id: str | None = None) -> list[dict]:
        with self.db.session() as s:
            q = select(Detection).where(Detection.status.in_(("pending", "queued"))).order_by(Detection.created_at)
            if game_id:
                q = q.where(Detection.game_id == game_id)
            return [_det_dict(d) for d in s.scalars(q)]

    def resolve(self, detection_id: str, choice: str, label: str | None = None, x_mm: float | None = None,
                y_mm: float | None = None) -> dict:
        """Resolve a pending detection: ``accept`` the prediction, take ``label`` (an
        alternative or a manual value), or ``reject`` it (not a dart)."""
        with self._lock:
            with self.db.session() as s:
                det = s.get(Detection, detection_id)
                if det is None:
                    raise KeyError(detection_id)
                if det.status not in ("pending", "queued", "unassigned"):
                    raise GameError(f"detection already {det.status}")
                gid = det.game_id
                if choice == "accept":
                    final = det.label
                elif choice == "label" and label:
                    final = dart_from_label(label).label
                elif choice == "reject":
                    final = None
                else:
                    raise GameError("choice must be accept, label or reject")
                det.status = "rejected" if final is None else "resolved"
                det.final_label = final
                if final is not None and final != det.label:
                    s.add(Correction(detection_id=det.id, game_id=gid, original_label=det.label, corrected_label=final,
                                     reason="uncertain_choice" if choice == "label" else "manual", x_mm=x_mm, y_mm=y_mm))
                if final is None and self.vision is not None and self.vision.engine is not None:
                    self.vision.engine.remove_dart(det.id)
                if final is not None and final != det.label:
                    self._relabel(det.id, final)
                if gid is not None and final is not None:
                    self._append(s, gid, "dart", dart_from_label(final, det.id), source="vision",
                                 payload={"resolved_from": det.label}, player_id=det.player_id)
                # Release queued detections in order until the next pending one.
                if gid is not None:
                    for q in s.scalars(select(Detection).where(Detection.game_id == gid, Detection.status == "queued")
                                       .order_by(Detection.created_at)):
                        q.status = "accepted"
                        self._append(s, gid, "dart", Dart(q.sector, q.multiplier, q.id), source="vision",
                                     player_id=q.player_id)
            if gid is None:
                return {"detection_id": detection_id, "status": "resolved"}
            state = self._recompute(gid)
        self._publish_state(state)
        return state

    def _on_takeout(self, data: dict) -> None:
        if not data.get("board_clear"):
            return
        with self._lock:
            gid = self.active_game_id()
            if gid is None:
                return
            st = self._recompute(gid, persist=False)
            if st["state"]["awaiting_takeout"] and not st["pending"]:
                with self.db.session() as s:
                    self._append(s, gid, "next_turn", source="auto", payload={"reason": "takeout"})
                state = self._recompute(gid)
                self._publish_state(state)

    # ------------------------------------------------------------------ state
    def _load(self, s, game_id: str) -> tuple[Game, list[dict], list[Action]]:
        g = s.get(Game, game_id)
        if g is None:
            raise KeyError(game_id)
        players = [{**_player_dict(gp.player), "position": gp.position} for gp in g.players]
        actions = []
        for a in s.scalars(select(GameAction).where(GameAction.game_id == game_id).order_by(GameAction.seq)):
            dart = Dart(a.sector, a.multiplier, a.dart_id or "") if a.sector is not None else None
            actions.append(Action(a.kind, dart, a.target_dart_id, a.payload or {}))
        return g, players, actions

    def _recompute(self, game_id: str, persist: bool = True) -> dict:
        with self.db.session() as s:
            g, players, actions = self._load(s, game_id)
            mode = get_mode(g.mode)
            st = replay(mode, g.settings, [p["id"] for p in players], actions)
            summaries = [mode.player_summary(st, i) for i in range(len(players))]
            hint = None if st.finished else mode.checkout_hint(st)
            pend = [_det_dict(d) for d in s.scalars(select(Detection).where(
                Detection.game_id == game_id, Detection.status.in_(("pending", "queued"))).order_by(Detection.created_at))]
            if persist:
                g.state_cache = st.to_dict()
                if st.finished and g.status in _ACTIVE:
                    g.status = "finished"
                    g.finished_at = datetime.now(timezone.utc)
                    g.winner_player_id = players[st.winner]["id"] if st.winner is not None else None
            return {
                "id": g.id, "mode": g.mode, "mode_name": mode.name, "status": g.status, "settings": g.settings,
                "created_at": g.created_at.isoformat() if g.created_at else None,
                "started_at": g.started_at.isoformat() if g.started_at else None,
                "finished_at": g.finished_at.isoformat() if g.finished_at else None,
                "players": players, "state": st.to_dict(), "player_summaries": summaries,
                "checkout_hint": hint, "pending": pend,
                "winner": players[st.winner] if st.winner is not None else None,
            }

    def _summary(self, s, g: Game) -> dict:
        players = [_player_dict(gp.player) for gp in g.players]
        winner = next((p for p in players if p["id"] == g.winner_player_id), None)
        return {"id": g.id, "mode": g.mode, "status": g.status, "settings": g.settings, "players": players,
                "created_at": g.created_at.isoformat() if g.created_at else None,
                "finished_at": g.finished_at.isoformat() if g.finished_at else None, "winner": winner}

    def _publish_state(self, state: dict) -> None:
        self.hub.publish("game", "game_state", state)

    def recent_detections(self, limit: int = 50, game_id: str | None = None) -> list[dict]:
        with self.db.session() as s:
            q = select(Detection).order_by(Detection.created_at.desc()).limit(min(limit, 1000))
            if game_id:
                q = q.where(Detection.game_id == game_id)
            return [_det_dict(d) for d in s.scalars(q)]

    def detection(self, detection_id: str) -> dict:
        with self.db.session() as s:
            d = s.get(Detection, detection_id)
            if d is None:
                raise KeyError(detection_id)
            return {**_det_dict(d), "payload": d.payload}

    def corrections(self, limit: int = 100) -> list[dict]:
        with self.db.session() as s:
            q = select(Correction).order_by(Correction.created_at.desc()).limit(min(limit, 1000))
            return [{"id": c.id, "created_at": c.created_at.isoformat(), "detection_id": c.detection_id,
                     "game_id": c.game_id, "original": c.original_label, "corrected": c.corrected_label,
                     "reason": c.reason, "x_mm": c.x_mm, "y_mm": c.y_mm, "note": c.note} for c in s.scalars(q)]

    def event_log(self, limit: int = 200, type_: str | None = None) -> list[dict]:
        with self.db.session() as s:
            q = select(EventLog).order_by(EventLog.id.desc()).limit(min(limit, 2000))
            if type_:
                q = q.where(EventLog.type == type_)
            return [{"id": e.id, "created_at": e.created_at.isoformat(), "type": e.type, "data": e.data}
                    for e in s.scalars(q)]


def _player_dict(p: Player) -> dict:
    return {"id": p.id, "name": p.name, "nickname": p.nickname, "color": p.color, "avatar": p.avatar,
            "archived": p.archived, "created_at": p.created_at.isoformat() if p.created_at else None}


def _det_dict(d: Detection) -> dict:
    p = d.payload or {}
    return {"id": d.id, "created_at": d.created_at.isoformat() if d.created_at else None, "game_id": d.game_id,
            "player_id": d.player_id, "label": d.label, "score": d.score, "sector": d.sector,
            "multiplier": d.multiplier, "x_mm": d.x_mm, "y_mm": d.y_mm, "confidence": d.confidence,
            "uncertain": d.uncertain, "status": d.status, "final_label": d.final_label,
            "alternatives": p.get("alternatives", []), "score_probability": p.get("score_probability"),
            "cameras_used": p.get("cameras_used", []), "sigma_mm": p.get("sigma_mm")}
