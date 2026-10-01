"""Player statistics, computed from the recorded games (by replaying their action logs) and
from the stored detections (impact heatmaps). Nothing here is estimated or simulated."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from sqlalchemy import select

from backend.database import Database
from backend.database.models import Detection, Game, GamePlayer, Player
from backend.game_engine import get_mode
from backend.game_engine.base import Dart, replay
from backend.services.game_service import GameService


def _is_single_dart_finish(remaining: int, rule: str) -> bool:
    if rule == "double":
        return remaining == 50 or (2 <= remaining <= 40 and remaining % 2 == 0)
    if rule == "master":
        return remaining == 50 or (2 <= remaining <= 40 and remaining % 2 == 0) or \
            (3 <= remaining <= 60 and remaining % 3 == 0)
    return 1 <= remaining <= 60


class StatsService:
    def __init__(self, db: Database, games: GameService) -> None:
        self.db = db
        self.games = games

    def player_stats(self, player_id: str, mode: str | None = None, last_n_games: int | None = None) -> dict[str, Any]:
        with self.db.session() as s:
            p = s.get(Player, player_id)
            if p is None:
                raise KeyError(player_id)
            q = (select(Game).join(GamePlayer, GamePlayer.game_id == Game.id)
                 .where(GamePlayer.player_id == player_id, Game.status.in_(("running", "paused", "finished")))
                 .order_by(Game.created_at.desc()))
            if mode:
                q = q.where(Game.mode == mode)
            games = list(s.scalars(q))
            if last_n_games:
                games = games[:last_n_games]
            game_ids = [g.id for g in games]
            finished = [g for g in games if g.status == "finished"]
        x01 = _X01Acc()
        cricket = {"darts": 0, "marks": 0}
        regions: Counter[str] = Counter()
        darts_total = 0
        history = []
        for gid in game_ids:
            data = self.games._recompute(gid, persist=False)
            idx = next((i for i, pl in enumerate(data["players"]) if pl["id"] == player_id), None)
            if idx is None:
                continue
            legs = [lh["turns"] for lh in data["state"]["leg_history"]] + [[t for t in data["state"]["turns"]]]
            game_x01 = _X01Acc()
            for turns in legs:
                mine = [t for t in turns if t["player_index"] == idx]
                for t in mine:
                    for d in t["darts"]:
                        darts_total += 1
                        regions[d["label"]] += 1
                if data["mode"] == "x01":
                    for acc in (x01, game_x01):
                        acc.add_leg(mine, data["settings"])
                elif data["mode"] == "cricket":
                    for t in mine:
                        cricket["darts"] += len(t["darts"])
                        cricket["marks"] += sum(_cricket_marks(d) for d in t["darts"])
            if data["mode"] == "x01" and game_x01.darts:
                history.append({"game_id": gid, "date": data["started_at"] or data["created_at"],
                                "average_3_dart": round(game_x01.points / game_x01.darts * 3, 2)})
        won = sum(1 for g in finished if g.winner_player_id == player_id)
        out = {
            "player": self.games.get_player(player_id),
            "games_played": len(game_ids),
            "games_finished": len(finished),
            "games_won": won,
            "win_rate": round(won / len(finished), 4) if finished else None,
            "darts_thrown": darts_total,
            "x01": x01.summary(),
            "cricket": {"darts": cricket["darts"],
                        "marks_per_round": round(cricket["marks"] / cricket["darts"] * 3, 2) if cricket["darts"] else None},
            "hit_distribution": _distribution(regions),
            "average_history": list(reversed(history)),
        }
        return out

    def heatmap(self, player_id: str | None = None, limit: int = 5000) -> list[dict]:
        with self.db.session() as s:
            q = select(Detection).where(Detection.status.in_(("accepted", "resolved"))).order_by(
                Detection.created_at.desc()).limit(limit)
            if player_id:
                q = q.where(Detection.player_id == player_id)
            return [{"x_mm": d.x_mm, "y_mm": d.y_mm, "label": d.final_label or d.label} for d in s.scalars(q)]

    def overview(self) -> dict[str, Any]:
        with self.db.session() as s:
            players = list(s.scalars(select(Player).where(Player.archived.is_(False))))
            games = list(s.scalars(select(Game)))
            dets = list(s.scalars(select(Detection)))
        by_mode = Counter(g.mode for g in games)
        status = Counter(d.status for d in dets)
        uncertain = sum(1 for d in dets if d.uncertain)
        corrected = sum(1 for d in dets if d.final_label and d.final_label != d.label)
        return {
            "players": len(players),
            "games": len(games),
            "games_by_mode": dict(by_mode),
            "games_finished": sum(1 for g in games if g.status == "finished"),
            "detections": len(dets),
            "detections_by_status": dict(status),
            "uncertain_rate": round(uncertain / len(dets), 4) if dets else None,
            "corrected_rate": round(corrected / len(dets), 4) if dets else None,
            "leaderboard": self._leaderboard(players),
        }

    def _leaderboard(self, players: list[Player]) -> list[dict]:
        rows = []
        for p in players:
            st = self.player_stats(p.id, mode="x01")
            if st["darts_thrown"] == 0:
                continue
            rows.append({"player_id": p.id, "name": p.name, "color": p.color, "games": st["games_played"],
                         "won": st["games_won"], "average_3_dart": st["x01"]["average_3_dart"],
                         "checkout_pct": st["x01"]["checkout_pct"]})
        rows.sort(key=lambda r: -(r["average_3_dart"] or 0))
        return rows


class _X01Acc:
    def __init__(self) -> None:
        self.points = 0
        self.darts = 0
        self.first9_points = 0
        self.first9_darts = 0
        self.legs_won = 0
        self.checkout_attempts = 0
        self.checkouts: list[int] = []
        self.tons = Counter()
        self.busts = 0

    def add_leg(self, turns: list[dict], settings: dict) -> None:
        remaining = settings.get("start_score", 501)
        rule = settings.get("out_mode", "double")
        for k, t in enumerate(turns):
            n = len(t["darts"])
            self.darts += n
            if k < 3:
                self.first9_darts += n
            start = remaining
            # Darts thrown at a finish (checkout attempts).
            r = remaining
            for d in t["darts"]:
                if _is_single_dart_finish(r, rule):
                    self.checkout_attempts += 1
                r -= d["score"]
            if t["bust"]:
                self.busts += 1
                continue
            pts = sum(d["score"] for d in t["darts"])
            self.points += pts
            if k < 3:
                self.first9_points += pts
            remaining -= pts
            if n == 3 or remaining == 0:
                if pts == 180:
                    self.tons["180"] += 1
                elif pts >= 140:
                    self.tons["140+"] += 1
                elif pts >= 100:
                    self.tons["100+"] += 1
            if remaining == 0:
                self.legs_won += 1
                self.checkouts.append(start)

    def summary(self) -> dict:
        return {
            "darts": self.darts,
            "average_3_dart": round(self.points / self.darts * 3, 2) if self.darts else None,
            "first_9_average": round(self.first9_points / self.first9_darts * 3, 2) if self.first9_darts else None,
            "legs_won": self.legs_won,
            "checkout_pct": round(len(self.checkouts) / self.checkout_attempts, 4) if self.checkout_attempts else None,
            "checkout_attempts": self.checkout_attempts,
            "highest_checkout": max(self.checkouts) if self.checkouts else None,
            "count_180": self.tons["180"], "count_140_plus": self.tons["140+"], "count_100_plus": self.tons["100+"],
            "busts": self.busts,
        }


def _cricket_marks(d: dict) -> int:
    if d["sector"] in (15, 16, 17, 18, 19, 20, 25):
        return d["multiplier"]
    return 0


def _distribution(regions: Counter) -> dict[str, Any]:
    total = sum(regions.values())
    if not total:
        return {"total": 0, "labels": {}, "triple_rate": None, "double_rate": None, "miss_rate": None}
    trip = sum(v for k, v in regions.items() if k.startswith("T"))
    dbl = sum(v for k, v in regions.items() if k.startswith("D") or k == "BULL")
    miss = regions.get("MISS", 0)
    return {"total": total, "labels": dict(regions.most_common()), "triple_rate": round(trip / total, 4),
            "double_rate": round(dbl / total, 4), "miss_rate": round(miss / total, 4)}
