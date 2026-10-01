import pytest

from backend.game_engine import Action, Dart, GameError, get_mode, list_modes, replay
from backend.game_engine.checkout import suggest_checkout


def d(label: str, i: int = 0) -> Dart:
    from vision.geometry.board import DartScore

    s = DartScore.from_label(label)
    return Dart(s.sector, s.multiplier, f"d{i}")


def play(mode_id: str, settings: dict, players: list[str], labels: list[str | None]):
    """None in labels means 'next turn' (takeout)."""
    m = get_mode(mode_id)
    st = m.new_state(settings, players)
    for i, lbl in enumerate(labels):
        if lbl is None:
            m.next_turn(st)
        else:
            m.throw(st, d(lbl, i))
    return m, st


# ---------------------------------------------------------------------------- X01
def test_x01_basic_scoring_and_turn_rotation() -> None:
    m, st = play("x01", {"start_score": 501}, ["a", "b"], ["T20", "T20", "T20", None, "S1"])
    assert st.player_data[0]["remaining"] == 321
    assert st.player_data[1]["remaining"] == 500
    assert st.current_player == 1


def test_x01_bust_restores_turn_start() -> None:
    m, st = play("x01", {"start_score": 101, "out_mode": "double"}, ["a"], ["T20", "S20", "S20"])
    # 101-60=41, -20=21, -20=1 -> leaves 1 with double out: bust
    assert st.turns[-1].bust
    assert st.player_data[0]["remaining"] == 101


def test_x01_double_out_required() -> None:
    m, st = play("x01", {"start_score": 101, "out_mode": "double"}, ["a"], ["T20", "S1", "S40" if False else "D20"])
    assert st.finished and st.winner == 0


def test_x01_single_finish_is_bust_with_double_out() -> None:
    # 101 -> 41 -> 40 -> 20; next turn a single 20 reaches zero without a double: bust.
    m, st = play("x01", {"start_score": 101}, ["a"], ["T20", "S1", "S20", None, "S20"])
    assert not st.finished
    assert st.turns[-1].bust
    assert st.player_data[0]["remaining"] == 20


def test_x01_straight_out() -> None:
    m, st = play("x01", {"start_score": 101, "out_mode": "straight"}, ["a"], ["T20", "S1", "S20", None, "S20"])
    assert st.finished


def test_x01_master_out_allows_triple() -> None:
    m, st = play("x01", {"start_score": 101, "out_mode": "master"}, ["a"], ["T20", "S11", "T10"])
    assert st.finished


def test_x01_double_in() -> None:
    m, st = play("x01", {"start_score": 301, "in_mode": "double"}, ["a"], ["T20", "S5", "D10"])
    assert st.player_data[0]["remaining"] == 281
    assert st.player_data[0]["opened"]


def test_x01_bull_finish() -> None:
    m, st = play("x01", {"start_score": 101}, ["a"], ["S20", "S20", None, "S11", "BULL"])
    assert st.finished


def test_x01_legs_and_sets() -> None:
    labels = []
    for _ in range(2):  # player a wins two legs of 101 (b throws misses)
        labels += ["T20", "S1", "D20"]
    m = get_mode("x01")
    st = m.new_state({"start_score": 101, "legs_to_win_set": 2, "sets_to_win": 1}, ["a", "b"])
    m.throw(st, d("T20"))
    m.throw(st, d("S1"))
    m.throw(st, d("D20"))
    assert st.legs_won == [1, 0] and not st.finished
    m.next_turn(st)  # new leg, b starts
    assert st.current_player == 1
    for lbl in ("MISS", "MISS", "MISS"):
        m.throw(st, d(lbl))
    m.next_turn(st)
    for lbl in ("T20", "S1", "D20"):
        m.throw(st, d(lbl))
    assert st.finished and st.winner == 0


def test_x01_rejects_bad_settings() -> None:
    with pytest.raises(GameError):
        get_mode("x01").new_state({"start_score": 50}, ["a"])
    with pytest.raises(GameError):
        get_mode("x01").new_state({"out_mode": "triple"}, ["a"])


def test_throw_after_turn_complete_starts_next_player() -> None:
    m, st = play("x01", {}, ["a", "b"], ["S1", "S1", "S1", "S5"])
    assert st.player_data[1]["remaining"] == 496


# ---------------------------------------------------------------------------- Cricket
def test_cricket_marks_and_points() -> None:
    m, st = play("cricket", {}, ["a", "b"], ["T20", "T20", "S19"])
    assert st.player_data[0]["marks"]["20"] == 3
    assert st.player_data[0]["points"] == 60
    assert st.player_data[0]["marks"]["19"] == 1


def test_cricket_no_points_on_closed_number() -> None:
    m, st = play("cricket", {}, ["a", "b"], ["T20", "MISS", "MISS", None, "T20", "MISS", "MISS", None, "T20"])
    assert st.player_data[0]["points"] == 0


def test_cricket_cutthroat_points_go_to_opponents() -> None:
    m, st = play("cricket", {"variant": "cutthroat"}, ["a", "b"], ["T20", "S20"])
    assert st.player_data[0]["points"] == 0
    assert st.player_data[1]["points"] == 20


def test_cricket_win() -> None:
    labels = []
    for n in (20, 19, 18, 17, 16, 15):
        labels.append(f"T{n}")
    labels.insert(3, None)
    m = get_mode("cricket")
    st = m.new_state({}, ["a"])
    for lbl in ["T20", "T19", "T18", "T17", "T16", "T15", "BULL", "25"]:
        if st.awaiting_takeout:
            m.next_turn(st)
        m.throw(st, d(lbl))
    assert st.finished and st.winner == 0


# ---------------------------------------------------------------------------- practice modes
def test_around_the_clock() -> None:
    m = get_mode("atc")
    st = m.new_state({"include_bull": False}, ["a"])
    for n in range(1, 21):
        if st.awaiting_takeout:
            m.next_turn(st)
        m.throw(st, d(f"S{n}"))
    assert st.finished


def test_shanghai_instant_win() -> None:
    m, st = play("shanghai", {"rounds": 7}, ["a", "b"], ["S1", "D1", "T1"])
    assert st.finished and st.winner == 0


def test_shanghai_rounds() -> None:
    m = get_mode("shanghai")
    st = m.new_state({"rounds": 2}, ["a", "b"])
    for lbl in ["S1", "MISS", "MISS"]:
        m.throw(st, d(lbl))
    m.next_turn(st)
    for lbl in ["T1", "MISS", "MISS"]:
        m.throw(st, d(lbl))
    m.next_turn(st)
    for lbl in ["MISS"] * 3:
        m.throw(st, d(lbl))
    m.next_turn(st)
    for lbl in ["S2", "MISS", "MISS"]:
        m.throw(st, d(lbl))
    m.next_turn(st)
    assert st.finished and st.winner == 1


def test_bobs27() -> None:
    m = get_mode("bobs27")
    st = m.new_state({}, ["a"])
    for lbl in ["D1", "MISS", "MISS"]:
        m.throw(st, d(lbl))
    m.next_turn(st)
    assert st.player_data[0]["points"] == 29
    for lbl in ["MISS"] * 3:
        m.throw(st, d(lbl))
    m.next_turn(st)
    assert st.player_data[0]["points"] == 25


# ---------------------------------------------------------------------------- replay, corrections, undo
def _actions(labels):
    return [Action("dart", d(lbl, i)) for i, lbl in enumerate(labels)]


def test_replay_correction_replaces_value() -> None:
    m = get_mode("x01")
    acts = _actions(["T20", "S5", "T20"])
    acts.append(Action("correct", Dart(20, 3, "x"), target_dart_id="d1"))
    st = replay(m, {"start_score": 501}, ["a"], acts)
    assert st.player_data[0]["remaining"] == 501 - 180


def test_replay_void_dart_and_undo() -> None:
    m = get_mode("x01")
    acts = _actions(["T20", "S5"]) + [Action("void_dart", target_dart_id="d1")]
    st = replay(m, {"start_score": 501}, ["a"], acts)
    assert st.player_data[0]["remaining"] == 441
    st2 = replay(m, {"start_score": 501}, ["a"], acts + [Action("undo")])
    assert st2.player_data[0]["remaining"] == 436


def test_dart_validation() -> None:
    with pytest.raises(GameError):
        Dart(21, 1)
    with pytest.raises(GameError):
        Dart(25, 3)
    assert Dart(25, 2).score == 50
    assert Dart(0, 0).label == "MISS"


def test_mode_registry() -> None:
    ids = {m["id"] for m in list_modes()}
    assert {"x01", "cricket", "atc", "shanghai", "bobs27"} <= ids


@pytest.mark.parametrize("left,expected_len", [(170, 3), (100, 2), (40, 1), (50, 1), (3, 2), (159, None)])
def test_checkout_suggestions(left: int, expected_len: int | None) -> None:
    route = suggest_checkout(left, 3, "double")
    if expected_len is None:
        assert route is None
    else:
        assert route is not None and len(route) == expected_len
        total = sum(Dart(*_parse(x)).score for x in route)
        assert total == left
        assert route[-1].startswith("D") or route[-1] == "BULL"


def _parse(label: str):
    from vision.geometry.board import DartScore

    s = DartScore.from_label(label)
    return s.sector, s.multiplier
