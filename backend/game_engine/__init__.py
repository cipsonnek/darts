"""Reusable, UI-independent game engine. Register additional modes with :func:`register`."""

from __future__ import annotations

from backend.game_engine.base import Action, Dart, GameError, GameMode, GameState, Turn, replay
from backend.game_engine.cricket import Cricket
from backend.game_engine.practice import AroundTheClock, Bobs27, Shanghai
from backend.game_engine.x01 import X01

_REGISTRY: dict[str, GameMode] = {}


def register(mode_cls: type[GameMode]) -> None:
    if not mode_cls.id:
        raise ValueError("game mode needs an id")
    _REGISTRY[mode_cls.id] = mode_cls()


def get_mode(mode_id: str) -> GameMode:
    try:
        return _REGISTRY[mode_id]
    except KeyError as exc:
        raise GameError(f"unknown game mode {mode_id!r}") from exc


def list_modes() -> list[dict]:
    return [{"id": m.id, "name": m.name, "description": m.description, "settings": m.settings_schema(),
             "darts_per_turn": m.darts_per_turn} for m in _REGISTRY.values()]


for _cls in (X01, Cricket, AroundTheClock, Shanghai, Bobs27):
    register(_cls)

__all__ = ["Action", "Dart", "GameError", "GameMode", "GameState", "Turn", "replay", "register", "get_mode",
           "list_modes"]
