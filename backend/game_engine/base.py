"""Game engine core: event-sourced, rule modules plug in through :class:`GameMode`.

A game's state is a pure function of its settings, its players and the ordered list of
*actions* applied to it (darts thrown, corrections, manual turn ends, undo). Corrections
and undo never rewrite history: they are new actions, and the state is recomputed by
replaying the log. This makes every past state reproducible and auditable.

The engine knows nothing about cameras, HTTP or React; it consumes :class:`Dart` values.
"""

from __future__ import annotations

import copy
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


class GameError(ValueError):
    pass


@dataclass(frozen=True)
class Dart:
    """The value of one dart as the game sees it."""

    sector: int  # 0 miss, 1..20, 25 bull
    multiplier: int  # 0 miss, 1, 2, 3
    dart_id: str = ""

    def __post_init__(self) -> None:
        if self.sector == 0:
            if self.multiplier not in (0, 1):
                raise GameError("a miss has multiplier 0")
        elif self.sector == 25:
            if self.multiplier not in (1, 2):
                raise GameError("bull multiplier must be 1 or 2")
        elif 1 <= self.sector <= 20:
            if self.multiplier not in (1, 2, 3):
                raise GameError("multiplier must be 1, 2 or 3")
        else:
            raise GameError(f"invalid sector {self.sector}")

    @property
    def score(self) -> int:
        return 0 if self.sector == 0 else self.sector * self.multiplier

    @property
    def is_double(self) -> bool:
        return self.multiplier == 2

    @property
    def is_triple(self) -> bool:
        return self.multiplier == 3

    @property
    def label(self) -> str:
        if self.sector == 0:
            return "MISS"
        if self.sector == 25:
            return "BULL" if self.multiplier == 2 else "25"
        return {1: "S", 2: "D", 3: "T"}[self.multiplier] + str(self.sector)

    def to_dict(self) -> dict:
        return {"sector": self.sector, "multiplier": self.multiplier, "score": self.score,
                "label": self.label, "dart_id": self.dart_id}


@dataclass
class Turn:
    player_index: int
    darts: list[Dart] = field(default_factory=list)
    bust: bool = False
    finished: bool = False  # turn closed
    points: int = 0  # mode-specific points of this turn
    note: str = ""

    def to_dict(self) -> dict:
        return {"player_index": self.player_index, "darts": [d.to_dict() for d in self.darts],
                "bust": self.bust, "finished": self.finished, "points": self.points, "note": self.note}


@dataclass
class GameState:
    mode: str
    settings: dict[str, Any]
    players: list[str]  # player ids, in throwing order of the first leg
    current_player: int = 0
    leg: int = 1
    set: int = 1
    legs_won: list[int] = field(default_factory=list)
    sets_won: list[int] = field(default_factory=list)
    leg_starter: int = 0
    turns: list[Turn] = field(default_factory=list)  # turns of the current leg
    leg_history: list[dict] = field(default_factory=list)
    player_data: list[dict[str, Any]] = field(default_factory=list)  # mode-specific per player
    winner: int | None = None
    finished: bool = False
    awaiting_takeout: bool = False  # 3 darts thrown (or bust/leg won): waiting for next player
    message: str = ""

    @property
    def current_turn(self) -> Turn | None:
        if self.turns and not self.turns[-1].finished:
            return self.turns[-1]
        return None

    def to_dict(self) -> dict:
        return {
            "mode": self.mode, "settings": self.settings, "players": self.players,
            "current_player": self.current_player, "leg": self.leg, "set": self.set,
            "legs_won": self.legs_won, "sets_won": self.sets_won, "leg_starter": self.leg_starter,
            "turns": [t.to_dict() for t in self.turns], "leg_history": self.leg_history,
            "player_data": self.player_data, "winner": self.winner, "finished": self.finished,
            "awaiting_takeout": self.awaiting_takeout, "message": self.message,
        }


class GameMode(ABC):
    """A rule module. Subclasses implement the per-dart rules; turn rotation, legs and
    sets are handled here."""

    id: str = ""
    name: str = ""
    darts_per_turn: int = 3
    description: str = ""

    @classmethod
    def settings_schema(cls) -> dict[str, Any]:
        """JSON-schema-like description of the settings (rendered by the frontend)."""
        return {}

    @classmethod
    def normalize_settings(cls, settings: dict[str, Any]) -> dict[str, Any]:
        out = {"legs_to_win_set": 1, "sets_to_win": 1}
        out.update(settings or {})
        for k in ("legs_to_win_set", "sets_to_win"):
            out[k] = int(out[k])
            if not 1 <= out[k] <= 25:
                raise GameError(f"{k} must be between 1 and 25")
        return out

    # -- per-mode hooks ---------------------------------------------------------------
    @abstractmethod
    def init_player(self, state: GameState, index: int) -> dict[str, Any]: ...

    @abstractmethod
    def apply_dart(self, state: GameState, turn: Turn, dart: Dart) -> str:
        """Apply one dart to the current player. Returns one of ``continue``, ``bust``
        (turn ends, its darts are void), ``leg_won`` (current player wins the leg) or
        ``turn_over`` (the mode ends the turn early)."""

    def on_turn_end(self, state: GameState, turn: Turn) -> str | None:
        """Called when a turn closes normally. May return ``leg_won`` (e.g. rounds-based
        modes decide the winner here)."""
        return None

    def checkout_hint(self, state: GameState) -> list[str] | None:
        return None

    def player_summary(self, state: GameState, index: int) -> dict[str, Any]:
        return dict(state.player_data[index])

    # -- engine ---------------------------------------------------------------------
    def new_state(self, settings: dict[str, Any], players: list[str]) -> GameState:
        if not players:
            raise GameError("a game needs at least one player")
        if len(players) > 16:
            raise GameError("at most 16 players")
        st = GameState(self.id, self.normalize_settings(settings), list(players))
        st.legs_won = [0] * len(players)
        st.sets_won = [0] * len(players)
        self._start_leg(st)
        return st

    def _start_leg(self, st: GameState) -> None:
        st.player_data = [self.init_player(st, i) for i in range(len(st.players))]
        st.turns = []
        st.current_player = st.leg_starter
        st.awaiting_takeout = False

    def throw(self, st: GameState, dart: Dart) -> None:
        if st.finished:
            raise GameError("the game is finished")
        if st.awaiting_takeout:
            # A dart thrown after the turn ended means the next player has started.
            self.next_turn(st)
        turn = st.current_turn
        if turn is None:
            turn = Turn(st.current_player)
            st.turns.append(turn)
        if len(turn.darts) >= self.darts_per_turn:
            raise GameError("turn already complete")
        turn.darts.append(dart)
        result = self.apply_dart(st, turn, dart)
        if result == "bust":
            turn.bust = True
            self._close_turn(st, turn, run_hook=False)
            st.message = "BUST"
        elif result == "leg_won":
            self._close_turn(st, turn, run_hook=False)
            self._win_leg(st, st.current_player)
        elif result == "turn_over" or len(turn.darts) >= self.darts_per_turn:
            self._close_turn(st, turn, run_hook=True)

    def _close_turn(self, st: GameState, turn: Turn, run_hook: bool) -> None:
        turn.finished = True
        st.awaiting_takeout = not st.finished
        if run_hook:
            res = self.on_turn_end(st, turn)
            if res == "leg_won":
                winner = self.rounds_winner(st)
                if winner is not None:
                    self._win_leg(st, winner)

    def rounds_winner(self, st: GameState) -> int | None:
        return None

    def next_turn(self, st: GameState) -> None:
        """Advance to the next player (after takeout, or by user action). Closes an
        incomplete turn (darts not thrown count as nothing)."""
        if st.finished:
            return
        turn = st.current_turn
        if turn is not None:
            turn.finished = True
            if not turn.bust:
                res = self.on_turn_end(st, turn)
                if res == "leg_won":
                    winner = self.rounds_winner(st)
                    if winner is not None:
                        self._win_leg(st, winner)
                        return
        if st.awaiting_takeout and st.leg_history and st.leg_history[-1].get("pending_next_leg"):
            st.leg_history[-1].pop("pending_next_leg")
            self._start_leg(st)
            return
        st.current_player = (st.current_player + 1) % len(st.players)
        st.awaiting_takeout = False
        st.message = ""

    def _win_leg(self, st: GameState, winner: int) -> None:
        st.legs_won[winner] += 1
        record = {"leg": st.leg, "set": st.set, "winner": winner,
                  "turns": [t.to_dict() for t in st.turns], "pending_next_leg": True}
        st.leg_history.append(record)
        cfg = st.settings
        msg = f"{st.players[winner]} wins leg {st.leg}"
        if st.legs_won[winner] >= cfg["legs_to_win_set"]:
            st.sets_won[winner] += 1
            msg = f"{st.players[winner]} wins set {st.set}"
            if st.sets_won[winner] >= cfg["sets_to_win"]:
                st.finished = True
                st.winner = winner
                st.awaiting_takeout = False
                st.message = f"{st.players[winner]} wins the game"
                record.pop("pending_next_leg", None)
                return
            st.set += 1
            st.legs_won = [0] * len(st.players)
        st.leg += 1
        st.leg_starter = (st.leg_starter + 1) % len(st.players)
        st.awaiting_takeout = True
        st.message = msg


@dataclass
class Action:
    """One entry of a game's action log."""

    kind: str  # dart | correct | undo | next_turn | void_dart
    dart: Dart | None = None
    target_dart_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


def replay(mode: GameMode, settings: dict[str, Any], players: list[str], actions: list[Action]) -> GameState:
    """Recompute a game's state from its action log.

    * ``correct`` replaces the value of an earlier dart (by dart id),
    * ``void_dart`` removes an earlier dart (e.g. a false detection),
    * ``undo`` cancels the most recent effective action.
    """
    effective: list[Action] = []
    for a in actions:
        if a.kind == "undo":
            if effective:
                effective.pop()
        else:
            effective.append(a)
    corrections: dict[str, Dart] = {}
    voided: set[str] = set()
    for a in effective:
        if a.kind == "correct" and a.target_dart_id and a.dart is not None:
            corrections[a.target_dart_id] = a.dart
        elif a.kind == "void_dart" and a.target_dart_id:
            voided.add(a.target_dart_id)
    st = mode.new_state(settings, players)
    for a in effective:
        if a.kind == "dart" and a.dart is not None:
            if a.dart.dart_id and a.dart.dart_id in voided:
                continue
            d = corrections.get(a.dart.dart_id, a.dart) if a.dart.dart_id else a.dart
            if d.dart_id != a.dart.dart_id:
                d = Dart(d.sector, d.multiplier, a.dart.dart_id)
            if st.finished:
                break
            mode.throw(st, d)
        elif a.kind == "next_turn":
            mode.next_turn(st)
    return st


def clone(st: GameState) -> GameState:
    return copy.deepcopy(st)
