"""Cricket (standard and cut-throat) on 15-20 and the bull."""

from __future__ import annotations

from typing import Any

from backend.game_engine.base import Dart, GameError, GameMode, GameState, Turn

NUMBERS = [20, 19, 18, 17, 16, 15, 25]


class Cricket(GameMode):
    id = "cricket"
    name = "Cricket"
    description = "Close 15-20 and the bull; score on numbers your opponents have not closed."

    @classmethod
    def settings_schema(cls) -> dict[str, Any]:
        return {
            "variant": {"type": "enum", "values": ["standard", "cutthroat"], "default": "standard"},
            "max_rounds": {"type": "integer", "default": 20, "min": 0, "max": 99,
                           "help": "0 = unlimited; otherwise the best score after this many rounds wins"},
            "legs_to_win_set": {"type": "integer", "default": 1, "min": 1, "max": 25},
            "sets_to_win": {"type": "integer", "default": 1, "min": 1, "max": 25},
        }

    @classmethod
    def normalize_settings(cls, settings: dict[str, Any]) -> dict[str, Any]:
        out = super().normalize_settings(settings)
        out.setdefault("variant", "standard")
        out.setdefault("max_rounds", 20)
        if out["variant"] not in ("standard", "cutthroat"):
            raise GameError("variant must be standard or cutthroat")
        out["max_rounds"] = int(out["max_rounds"])
        return out

    def init_player(self, state: GameState, index: int) -> dict[str, Any]:
        return {"marks": {str(n): 0 for n in NUMBERS}, "points": 0, "darts_thrown": 0, "marks_total": 0}

    def _closed(self, state: GameState, idx: int, n: int) -> bool:
        return state.player_data[idx]["marks"][str(n)] >= 3

    def apply_dart(self, state: GameState, turn: Turn, dart: Dart) -> str:
        me = state.current_player
        pd = state.player_data[me]
        pd["darts_thrown"] += 1
        n = dart.sector
        if n not in NUMBERS or dart.multiplier == 0:
            return self._check_win(state)
        hits = dart.multiplier
        before = pd["marks"][str(n)]
        new_marks = before + hits
        pd["marks"][str(n)] = min(new_marks, 3)
        pd["marks_total"] += min(new_marks, 3) - before
        extra = max(0, new_marks - 3) if before < 3 else hits
        if extra:
            value = extra * n
            others = [i for i in range(len(state.players)) if i != me and not self._closed(state, i, n)]
            if others:
                if state.settings["variant"] == "cutthroat":
                    for i in others:
                        state.player_data[i]["points"] += value
                else:
                    pd["points"] += value
                turn.points += value
        return self._check_win(state)

    def _check_win(self, state: GameState) -> str:
        me = state.current_player
        if not all(self._closed(state, me, n) for n in NUMBERS):
            return "continue"
        mine = state.player_data[me]["points"]
        others = [state.player_data[i]["points"] for i in range(len(state.players)) if i != me]
        if state.settings["variant"] == "cutthroat":
            ok = all(mine <= o for o in others)
        else:
            ok = all(mine >= o for o in others)
        return "leg_won" if ok else "continue"

    def on_turn_end(self, state: GameState, turn: Turn) -> str | None:
        limit = state.settings["max_rounds"]
        if limit and turn.player_index == (state.leg_starter - 1) % len(state.players):
            rounds = sum(1 for t in state.turns if t.player_index == state.leg_starter and t.finished)
            if rounds >= limit:
                return "leg_won"
        return None

    def rounds_winner(self, state: GameState) -> int | None:
        pts = [p["points"] for p in state.player_data]
        if state.settings["variant"] == "cutthroat":
            best = min(pts)
        else:
            best = max(pts)
        cands = [i for i, p in enumerate(pts) if p == best]
        if len(cands) > 1:
            marks = [state.player_data[i]["marks_total"] for i in cands]
            return cands[marks.index(max(marks))]
        return cands[0]

    def player_summary(self, state: GameState, index: int) -> dict[str, Any]:
        pd = state.player_data[index]
        rounds = max(1, pd["darts_thrown"] / 3)
        return {"marks": pd["marks"], "points": pd["points"],
                "marks_per_round": round(pd["marks_total"] / rounds, 2) if pd["darts_thrown"] else 0.0}
