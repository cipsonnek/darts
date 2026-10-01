"""Around the Clock, Shanghai and Bob's 27."""

from __future__ import annotations

from typing import Any

from backend.game_engine.base import Dart, GameError, GameMode, GameState, Turn


class AroundTheClock(GameMode):
    id = "atc"
    name = "Around the Clock"
    description = "Hit 1 to 20 in order (optionally finish on the bull)."

    @classmethod
    def settings_schema(cls) -> dict[str, Any]:
        return {
            "include_bull": {"type": "boolean", "default": True},
            "multiplier_advances": {"type": "boolean", "default": False,
                                    "help": "Doubles/triples advance 2/3 targets"},
            "legs_to_win_set": {"type": "integer", "default": 1, "min": 1, "max": 25},
            "sets_to_win": {"type": "integer", "default": 1, "min": 1, "max": 25},
        }

    @classmethod
    def normalize_settings(cls, settings: dict[str, Any]) -> dict[str, Any]:
        out = super().normalize_settings(settings)
        out["include_bull"] = bool(out.get("include_bull", True))
        out["multiplier_advances"] = bool(out.get("multiplier_advances", False))
        return out

    def _sequence(self, state: GameState) -> list[int]:
        return list(range(1, 21)) + ([25] if state.settings["include_bull"] else [])

    def init_player(self, state: GameState, index: int) -> dict[str, Any]:
        return {"position": 0, "target": 1, "darts_thrown": 0, "hits": 0}

    def apply_dart(self, state: GameState, turn: Turn, dart: Dart) -> str:
        pd = state.player_data[state.current_player]
        seq = self._sequence(state)
        pd["darts_thrown"] += 1
        if dart.sector == seq[pd["position"]]:
            step = dart.multiplier if state.settings["multiplier_advances"] and dart.sector != 25 else 1
            pd["position"] = min(len(seq), pd["position"] + step)
            pd["hits"] += 1
            turn.points += 1
            if pd["position"] >= len(seq):
                pd["target"] = None
                return "leg_won"
            pd["target"] = seq[pd["position"]]
        return "continue"

    def player_summary(self, state: GameState, index: int) -> dict[str, Any]:
        pd = state.player_data[index]
        return {"target": pd["target"], "progress": pd["position"], "of": len(self._sequence(state)),
                "hit_rate": round(pd["hits"] / pd["darts_thrown"], 3) if pd["darts_thrown"] else 0.0}


class Shanghai(GameMode):
    id = "shanghai"
    name = "Shanghai"
    description = "Round n scores only on n. Single + double + triple of n in one turn wins instantly."

    @classmethod
    def settings_schema(cls) -> dict[str, Any]:
        return {
            "rounds": {"type": "integer", "default": 7, "min": 1, "max": 20},
            "legs_to_win_set": {"type": "integer", "default": 1, "min": 1, "max": 25},
            "sets_to_win": {"type": "integer", "default": 1, "min": 1, "max": 25},
        }

    @classmethod
    def normalize_settings(cls, settings: dict[str, Any]) -> dict[str, Any]:
        out = super().normalize_settings(settings)
        out["rounds"] = int(out.get("rounds", 7))
        if not 1 <= out["rounds"] <= 20:
            raise GameError("rounds must be 1..20")
        return out

    def init_player(self, state: GameState, index: int) -> dict[str, Any]:
        return {"points": 0, "round": 1, "darts_thrown": 0}

    def apply_dart(self, state: GameState, turn: Turn, dart: Dart) -> str:
        pd = state.player_data[state.current_player]
        pd["darts_thrown"] += 1
        target = pd["round"]
        if dart.sector == target:
            pd["points"] += dart.score
            turn.points += dart.score
        if len(turn.darts) == 3:
            mults = {d.multiplier for d in turn.darts if d.sector == target}
            if mults == {1, 2, 3}:
                turn.note = "SHANGHAI"
                return "leg_won"
        return "continue"

    def on_turn_end(self, state: GameState, turn: Turn) -> str | None:
        pd = state.player_data[turn.player_index]
        pd["round"] += 1
        last = (state.leg_starter - 1) % len(state.players)
        if turn.player_index == last and pd["round"] > state.settings["rounds"]:
            return "leg_won"
        return None

    def rounds_winner(self, state: GameState) -> int | None:
        pts = [p["points"] for p in state.player_data]
        return pts.index(max(pts))

    def player_summary(self, state: GameState, index: int) -> dict[str, Any]:
        pd = state.player_data[index]
        return {"points": pd["points"], "round": min(pd["round"], state.settings["rounds"]),
                "target": pd["round"] if pd["round"] <= state.settings["rounds"] else None}


class Bobs27(GameMode):
    id = "bobs27"
    name = "Bob's 27"
    description = "Doubles practice: start on 27, gain 2n per D(n) hit, lose 2n for a round without one."

    @classmethod
    def settings_schema(cls) -> dict[str, Any]:
        return {"include_bull": {"type": "boolean", "default": True}}

    @classmethod
    def normalize_settings(cls, settings: dict[str, Any]) -> dict[str, Any]:
        out = super().normalize_settings(settings)
        out["include_bull"] = bool(out.get("include_bull", True))
        return out

    def _targets(self, state: GameState) -> list[int]:
        return list(range(1, 21)) + ([25] if state.settings["include_bull"] else [])

    def init_player(self, state: GameState, index: int) -> dict[str, Any]:
        return {"points": 27, "round": 0, "eliminated": False, "doubles_hit": 0, "darts_thrown": 0}

    def apply_dart(self, state: GameState, turn: Turn, dart: Dart) -> str:
        pd = state.player_data[state.current_player]
        if pd["eliminated"]:
            return "turn_over"
        pd["darts_thrown"] += 1
        target = self._targets(state)[pd["round"]]
        if dart.sector == target and dart.multiplier == 2:
            value = 2 * target if target != 25 else 50
            pd["points"] += value
            pd["doubles_hit"] += 1
            turn.points += value
        return "continue"

    def on_turn_end(self, state: GameState, turn: Turn) -> str | None:
        pd = state.player_data[turn.player_index]
        if not pd["eliminated"]:
            targets = self._targets(state)
            target = targets[pd["round"]]
            if turn.points == 0:
                pd["points"] -= 2 * target if target != 25 else 50
                if pd["points"] < 0:
                    pd["eliminated"] = True
            pd["round"] += 1
            if pd["round"] >= len(targets):
                pd["eliminated"] = pd["eliminated"] or False
        last = (state.leg_starter - 1) % len(state.players)
        done = all(p["eliminated"] or p["round"] >= len(self._targets(state)) for p in state.player_data)
        if turn.player_index == last and done:
            return "leg_won"
        return None

    def rounds_winner(self, state: GameState) -> int | None:
        pts = [(-1 if p["eliminated"] else p["points"]) for p in state.player_data]
        return pts.index(max(pts))

    def player_summary(self, state: GameState, index: int) -> dict[str, Any]:
        pd = state.player_data[index]
        targets = self._targets(state)
        return {"points": pd["points"], "eliminated": pd["eliminated"], "doubles_hit": pd["doubles_hit"],
                "target": None if pd["round"] >= len(targets) else ("BULL" if targets[pd["round"]] == 25 else f"D{targets[pd['round']]}")}
