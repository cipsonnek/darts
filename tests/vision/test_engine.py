"""Temporal behaviour of the engine on rendered sequences (real engine, virtual clock)."""

from __future__ import annotations

import numpy as np
import pytest

from vision.cameras.base import Frame
from vision.config import VisionConfig
from vision.engine import EngineState, VisionEngine
from vision.evaluation import Scenario, ScenarioStep, SimulationRunner, compute_metrics
from vision.events import EventType

pytestmark = pytest.mark.slow


def _runner(seed: int = 5) -> SimulationRunner:
    return SimulationRunner(seed=seed, fps=15, width=960, height=540, calibration="truth")


def test_turn_of_three_darts_and_takeout() -> None:
    r = _runner()
    steps = [ScenarioStep(1.5, "throw", {"target": (0.0, 103.0)}),
             ScenarioStep(2.7, "throw", {"target": (-60.0, 70.0)}),
             ScenarioStep(3.9, "throw", {"target": (80.0, -40.0)}),
             ScenarioStep(5.0, "takeout", {})]
    res = r.run(Scenario("turn", steps, 9.0))
    types = [e.type for e in res.events]
    darts = [e for e in res.events if e.type == EventType.DART]
    assert len(darts) == 3
    m = compute_metrics([res])
    assert m["detection_rate"] == 1.0
    assert m["duplicates"] == 0 and m["false_positives"] == 0
    assert m["impact_error_mm"]["max"] < 3.0
    removed = [e for e in res.events if e.type == EventType.DARTS_REMOVED]
    assert removed and removed[-1].data["board_clear"]
    assert EventType.BOARD_CLEAR in types
    assert r.engine.state == EngineState.IDLE
    assert len(r.engine.board_state) == 0
    # Each dart event comes after its landing and before the next throw.
    gts = sorted(res.ground_truth, key=lambda g: g.landed_at)
    for g, e in zip(gts, darts):
        assert g.landed_at < e.timestamp < g.landed_at + 1.2


def test_hand_passing_is_not_a_dart() -> None:
    r = _runner(6)
    steps = [ScenarioStep(1.5, "throw", {"target": (20.0, 60.0)}),
             ScenarioStep(3.0, "hand", {}),
             ScenarioStep(5.0, "throw", {"target": (-30.0, -90.0)})]
    res = r.run(Scenario("hand", steps, 7.0))
    m = compute_metrics([res])
    assert m["darts_thrown"] == 2
    assert m["detected"] == 2
    assert m["false_positives"] == 0 and m["duplicates"] == 0


def test_takeout_after_a_light_change_leaves_no_phantom_darts() -> None:
    """Under light other than the empty-board image's, the spots pulled darts leave read as
    "added" pixels. They must not become new darts in the takeout scene: those stayed in
    memory, so the next takeout was never complete and the game waited."""
    r = _runner()
    steps = [ScenarioStep(1.5, "throw", {"target": (0.0, 103.0)}),
             ScenarioStep(2.7, "throw", {"target": (-60.0, 70.0)}),
             ScenarioStep(3.9, "throw", {"target": (80.0, -40.0)}),
             ScenarioStep(5.0, "lighting", {"preset": "uneven"}),
             ScenarioStep(8.0, "takeout", {})]
    res = r.run(Scenario("takeout-light", steps, 12.0))
    removed = [e for e in res.events if e.type == EventType.DARTS_REMOVED]
    assert removed and removed[-1].data["board_clear"]
    takeout_t = removed[-1].timestamp
    assert not [e for e in res.events if e.type == EventType.DART and e.timestamp >= takeout_t]
    assert EventType.BOARD_CLEAR in [e.type for e in res.events]
    assert len(r.engine.board_state) == 0


def test_lighting_change_does_not_rescore_existing_dart() -> None:
    r = _runner(7)
    steps = [ScenarioStep(1.5, "throw", {"target": (0.0, 140.0)}),
             ScenarioStep(3.0, "lighting", {"preset": "warm"}),
             ScenarioStep(5.0, "throw", {"target": (50.0, -60.0)})]
    res = r.run(Scenario("light", steps, 7.0))
    m = compute_metrics([res])
    assert m["detected"] == 2
    assert m["false_positives"] == 0 and m["duplicates"] == 0


def test_engine_requires_settling_before_baseline() -> None:
    cfg = VisionConfig()
    eng = VisionEngine(cfg, {"c": None})
    rng = np.random.default_rng(0)
    img = rng.integers(0, 255, (120, 160, 3), dtype=np.uint8)
    for i in range(3):
        eng.process_frameset({"c": Frame("c", img, i * 0.05, i)})
    assert eng.state == EngineState.STARTING
    for i in range(3, 12):
        eng.process_frameset({"c": Frame("c", img, i * 0.05, i)})
    assert eng.state == EngineState.IDLE


def test_permanent_scene_change_is_adopted_not_obstruction_forever() -> None:
    # e.g. the room lights are switched on: a large, perfectly still change.
    r = _runner(8)
    res = r.run(Scenario("idle", [], 2.0))
    eng = r.engine
    last = {cid: ctx.last_frame for cid, ctx in eng.cameras.items()}
    t0 = max(f.timestamp for f in last.values())
    changed = {}
    for cid, f in last.items():
        img = f.image.copy()
        h, w = img.shape[:2]
        img[h // 4: 3 * h // 4, w // 4: 3 * w // 4] = (40, 90, 160)
        changed[cid] = img
    events = []
    for i in range(1, int(12 * 15)):
        events += eng.process_frameset({cid: Frame(cid, changed[cid], t0 + i / 15, 10_000 + i) for cid in changed})
    rebased = [e for e in events if e.type == EventType.BASELINE and e.data.get("reason") == "scene_changed"]
    assert rebased, [e.type for e in events]
    assert not [e for e in events if e.type == EventType.DART]
    assert eng.state == EngineState.IDLE
    assert res is not None


def _flicker(img: np.ndarray, i: int) -> np.ndarray:
    """Every 2 s a few frames with a moving bright patch: breaks stillness like sensor noise or
    flicker does, without being a real change of the scene."""
    if i % 30 >= 3:
        return img
    out = img.copy()
    h, w = out.shape[:2]
    x = w // 2 + (i % 30) * 12
    out[h // 2 - 25: h // 2 + 25, x - 25: x + 25] = 255
    return out


def test_restless_obstruction_is_adopted_too() -> None:
    """Seen on the real board after ~15 min: the status flipped between "motion" and
    "obstructed" for good. A changed picture that never stays perfectly still for 8 s was
    never adopted."""
    r = _runner(8)
    r.run(Scenario("idle", [], 2.0))
    eng = r.engine
    last = {cid: ctx.last_frame for cid, ctx in eng.cameras.items()}
    t0 = max(f.timestamp for f in last.values())
    changed = {}
    for cid, f in last.items():
        img = f.image.copy()
        h, w = img.shape[:2]
        img[h // 4: 3 * h // 4, w // 4: 3 * w // 4] = (40, 90, 160)
        changed[cid] = img
    events, states = [], []
    for i in range(1, 30 * 15):
        events += eng.process_frameset({cid: Frame(cid, _flicker(changed[cid], i), t0 + i / 15, 10_000 + i)
                                        for cid in changed})
        states.append(eng.state)
    assert EngineState.OBSTRUCTED in states  # it was an obstruction first
    assert [e for e in events if e.type == EventType.BASELINE and e.data.get("reason") == "scene_changed"]
    assert states[-1] == EngineState.IDLE
    assert not [e for e in events if e.type == EventType.DART]


def test_idle_references_follow_slow_drift() -> None:
    """A picture drifting slowly (white balance, lamp warming up) must never add up to an
    obstruction: while idle, the references follow it."""
    r = _runner(8)
    r.run(Scenario("idle", [], 2.0))
    eng = r.engine
    last = {cid: ctx.last_frame for cid, ctx in eng.cameras.items()}
    t0 = max(f.timestamp for f in last.values())
    events = []
    n = 60 * 15
    for i in range(1, n):
        gain = 1.0 + 0.6 * i / n  # +60 % brightness over a minute
        frames = {cid: Frame(cid, np.clip(f.image.astype(np.float32) * gain, 0, 255).astype(np.uint8),
                             t0 + i / 15, 10_000 + i) for cid, f in last.items()}
        events += eng.process_frameset(frames)
    assert not [e for e in events if e.type in (EventType.OBSTRUCTION, EventType.DART)]
    assert eng.state == EngineState.IDLE


def test_missed_scene_is_kept_for_replay(tmp_path) -> None:
    """A change with no dart counted is saved: pictures before/after, empty board, darts."""
    import json
    import time as _time

    r = SimulationRunner(seed=2, fps=15, width=640, height=360, calibration="truth")
    r.run(Scenario("one", [ScenarioStep(1.0, "throw", {"target": (0.0, 103.0)})], 4.0))
    eng = r.engine
    eng.scene_dir = tmp_path / "missed"
    cams = {cid: ctx for cid, ctx in eng.cameras.items() if ctx.reference is not None}
    frames = {cid: ctx.last_frame for cid, ctx in cams.items()}
    changes = {cid: None for cid in cams}
    from vision.dart_detection.change import compute_change
    for cid, ctx in cams.items():
        changes[cid] = compute_change(ctx.reference, frames[cid].image, ctx.roi, eng.config.detection, ctx.empty)
    eng._keep_scene(frames, cams, changes, 12.5)
    for _ in range(50):
        found = list((tmp_path / "missed").glob("*/scene.json"))
        if found:
            break
        _time.sleep(0.1)
    assert found, "scene not written"
    folder = found[0].parent
    meta = json.loads(found[0].read_text(encoding="utf-8"))
    assert len(meta["darts_on_board"]) == 1
    for cid in cams:
        assert (folder / f"{cid}_before.png").exists() and (folder / f"{cid}_after.png").exists()
    assert (folder / "darts.pkl").exists()


def test_darts_in_the_board_at_start_do_not_spoil_later_throws() -> None:
    """The first real rig: the server started with darts in the board, so the empty-board
    picture showed darts. Takeouts of later darts at the same spots were then not seen, the
    list of darts went stale and new darts there were taken for those stale ones."""
    r = SimulationRunner(seed=4, fps=15, width=960, height=540, calibration="truth")
    eng = r.engine
    state = {"done": False}

    def start_up_with_darts(_frac: float) -> None:
        # Once the two first darts are in, act as a fresh start: the "empty" picture shows
        # them, and the engine knows of no darts.
        if not state["done"] and r.clock.t >= 4.0:
            for ctx in eng.cameras.values():
                if ctx.last_frame is not None:
                    ctx.empty = ctx.last_frame.image.copy()
            eng.board_state.remove([d.dart_id for d in eng.board_state.darts])
            state["done"] = True
            state["events_before"] = len(r.events)

    steps = [ScenarioStep(1.0, "throw", {"target": (0.0, 103.0)}),
             ScenarioStep(2.2, "throw", {"target": (-60.0, 70.0)}),
             ScenarioStep(5.0, "takeout", {}),
             ScenarioStep(8.0, "throw", {"target": (1.5, 104.5)}),
             ScenarioStep(10.0, "takeout", {}),
             ScenarioStep(13.0, "throw", {"target": (-1.0, 102.0)})]
    r.run(Scenario("start-with-darts", steps, 16.0), progress=start_up_with_darts)
    assert state["done"]
    later = r.events[state["events_before"]:]
    darts = [e for e in later if e.type == EventType.DART]
    assert len(darts) == 2, [e.type for e in later]
    removed = [e for e in later if e.type == EventType.DARTS_REMOVED]
    assert removed and removed[-1].data["board_clear"]
    assert len(eng.board_state) == 1
