"""A dart that moves while it is pulled out must not score for the next turn."""

from __future__ import annotations

from types import SimpleNamespace

from backend.database import Database
from backend.services.game_service import GameService
from backend.ws.hub import EventHub
from vision.config import VisionConfig
from vision.events import EventType, VisionEvent


class _Engine:
    def __init__(self) -> None:
        self.board_state: list[str] = []

    def relabel_dart(self, *_a) -> bool:
        return True

    def remove_dart(self, *_a) -> bool:
        return True


def _dart(dart_id: str, label: str, sector: int, mult: int) -> VisionEvent:
    return VisionEvent(EventType.DART, 0.0, {
        "dart_id": dart_id, "uncertain": False,
        "score": {"sector": sector, "multiplier": mult, "score": sector * mult, "label": label},
        "impact": {"x_mm": 0.0, "y_mm": 100.0}, "confidence": {"overall": 0.99}})


def _setup(tmp_path):
    db = Database(f"sqlite:///{(tmp_path / 'db.sqlite').as_posix()}")
    db.migrate()
    games = GameService(db, EventHub())
    engine = _Engine()
    games.vision = SimpleNamespace(engine=engine, cfg=VisionConfig())
    a = games.create_player("A")["id"]
    b = games.create_player("B")["id"]
    gid = games.create_game("x01", {"start_score": 501}, [a, b])["id"]
    return games, engine, gid


def _throw(games, engine, dart_id, label="S20", sector=20, mult=1):
    engine.board_state.append(dart_id)  # the engine adds a dart before emitting it
    games.on_vision_event(_dart(dart_id, label, sector, mult))


def test_dart_seen_during_takeout_is_not_scored(tmp_path) -> None:
    games, engine, gid = _setup(tmp_path)
    for i in range(3):
        _throw(games, engine, f"d{i}")
    st = games.get_game(gid)
    assert st["state"]["awaiting_takeout"] and st["player_summaries"][0]["remaining"] == 441
    # Player grabs a dart, it tilts: the engine reports it as a new dart.
    _throw(games, engine, "ghost", "S5", 5, 1)
    st = games.get_game(gid)
    assert st["state"]["current_player"] == 0 and st["state"]["awaiting_takeout"]
    assert st["player_summaries"][1]["remaining"] == 501
    assert games.detection("ghost")["status"] == "ignored"
    # Board cleared: next player's turn, and their darts count again.
    engine.board_state.clear()
    games.on_vision_event(VisionEvent(EventType.DARTS_REMOVED, 0.0, {"dart_ids": [], "board_clear": True,
                                                                    "remaining": []}))
    _throw(games, engine, "b1", "T20", 20, 3)
    st = games.get_game(gid)
    assert st["state"]["current_player"] == 1 and st["player_summaries"][1]["remaining"] == 441


def test_game_messages_use_player_names(tmp_path) -> None:
    games, _engine, _ = _setup(tmp_path)
    a = games.list_players()[0]
    gid = games.create_game("x01", {"start_score": 101, "legs_to_win_set": 2}, [a["id"]])["id"]
    for label in ("T20", "S1", "D20"):
        st = games.throw(gid, label)
    assert st["state"]["message"] == f"{a['name']} wins leg 1", st["state"]["message"]


def test_throw_without_takeout_counts_after_board_empty(tmp_path) -> None:
    # Takeout missed by the cameras but the board is empty: the dart is the next player's.
    games, engine, gid = _setup(tmp_path)
    for i in range(3):
        _throw(games, engine, f"d{i}")
    engine.board_state.clear()
    _throw(games, engine, "b1", "S1", 1, 1)
    st = games.get_game(gid)
    assert st["state"]["current_player"] == 1 and st["player_summaries"][1]["remaining"] == 500
