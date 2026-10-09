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
