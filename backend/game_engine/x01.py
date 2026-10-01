"""X01 (301 / 501 / 701 / any start) with straight/double/master in and out."""

from __future__ import annotations

from typing import Any

from backend.game_engine.base import Dart, GameError, GameMode, GameState, Turn
from backend.game_engine.checkout import suggest_checkout

_RULES = ("straight", "double", "master")


class X01(GameMode):
    id = "x01"
    name = "X01"
    description = "Count down from the start score; finish exactly on zero."

    @classmethod
    def settings_schema(cls) -> dict[str, Any]:
        return {
            "start_score": {"type": "integer", "default": 501, "presets": [301, 501, 701, 901], "min": 101, "max": 2001},
            "in_mode": {"type": "enum", "values": list(_RULES), "default": "straight"},
            "out_mode": {"type": "enum", "values": list(_RULES), "default": "double"},
            "legs_to_win_set": {"type": "integer", "default": 1, "min": 1, "max": 25},
            "sets_to_win": {"type": "integer", "default": 1, "min": 1, "max": 25},
        }

    @classmethod
    def normalize_settings(cls, settings: dict[str, Any]) -> dict[str, Any]:
        out = super().normalize_settings(settings)
        out.setdefault("start_score", 501)
        out.setdefault("in_mode", "straight")
        out.setdefault("out_mode", "double")
        out["start_score"] = int(out["start_score"])
        if not 101 <= out["start_score"] <= 2001:
            raise GameError("start_score must be between 101 and 2001")
        for k in ("in_mode", "out_mode"):
            if out[k] not in _RULES:
                raise GameError(f"{k} must be one of {_RULES}")
        return out

    def init_player(self, state: GameState, index: int) -> dict[str, Any]:
        return {"remaining": state.settings["start_score"], "opened": state.settings["in_mode"] == "straight",
                "turn_start": state.settings["start_score"], "darts_thrown": 0, "points_scored": 0}

    @staticmethod
    def _qualifies(dart: Dart, rule: str) -> bool:
        if rule == "straight":
            return True
        if rule == "double":
            return dart.is_double
        return dart.is_double or dart.is_triple

    def apply_dart(self, state: GameState, turn: Turn, dart: Dart) -> str:
        pd = state.player_data[state.current_player]
        if len(turn.darts) == 1:
            pd["turn_start"] = pd["remaining"]
            pd["opened_at_turn_start"] = pd["opened"]
        pd["darts_thrown"] += 1
        if not pd["opened"]:
            if self._qualifies(dart, state.settings["in_mode"]) and dart.score > 0:
                pd["opened"] = True
            else:
                return "continue"
        new = pd["remaining"] - dart.score
        rule = state.settings["out_mode"]
        min_left = 0 if rule == "straight" else 2
        if new < 0 or (0 < new < min_left):
            return self._bust(pd, turn)
        if new == 0:
            if not self._qualifies(dart, rule):
                return self._bust(pd, turn)
            pd["remaining"] = 0
            turn.points = pd["turn_start"]
            pd["points_scored"] += dart.score
            return "leg_won"
        pd["remaining"] = new
        pd["points_scored"] += dart.score
        turn.points = pd["turn_start"] - new
        return "continue"

    @staticmethod
    def _bust(pd: dict, turn: Turn) -> str:
        pd["points_scored"] -= pd["turn_start"] - pd["remaining"]
        pd["remaining"] = pd["turn_start"]
        pd["opened"] = pd.get("opened_at_turn_start", pd["opened"])
        turn.points = 0
        return "bust"

    def checkout_hint(self, state: GameState) -> list[str] | None:
        pd = state.player_data[state.current_player]
        turn = state.current_turn
        left = self.darts_per_turn - (len(turn.darts) if turn else 0)
        if not pd["opened"] or left <= 0:
            return None
        return suggest_checkout(pd["remaining"], left, state.settings["out_mode"])

    def player_summary(self, state: GameState, index: int) -> dict[str, Any]:
        pd = state.player_data[index]
        darts = pd["darts_thrown"]
        return {"remaining": pd["remaining"], "opened": pd["opened"], "darts_thrown": darts,
                "average_3_dart": round(pd["points_scored"] / darts * 3, 2) if darts else 0.0}
