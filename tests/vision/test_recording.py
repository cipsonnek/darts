"""Record a simulated session to disk, replay it through a fresh engine, get the same darts."""

from __future__ import annotations

import json

import numpy as np
import pytest

from backend.services.replay import evaluate_session, replay_session
from vision.cameras.base import Frame
from vision.config import VisionConfig
from vision.engine import VisionEngine
from vision.events import EventType
from vision.recording.format import read_frame_index, write_ground_truth
from vision.recording.recorder import SessionRecorder
from vision.simulation.rig import default_rig
from vision.simulation.world import SimulatedWorld, ThrowParams

pytestmark = pytest.mark.slow


def test_record_and_replay(tmp_path) -> None:
    rig = default_rig(960, 540, jitter_seed=3)
    clock = {"t": 0.0}
    world = SimulatedWorld(rig, seed=9, clock=lambda: clock["t"])
    cfg = VisionConfig()
    live = VisionEngine(cfg, dict(rig))
    live_events = []
    live.subscribe(live_events.append)
    rec = SessionRecorder(tmp_path, "s1", "png")
    rec.set_metadata(cameras=list(rig), synthetic=True, vision_config=cfg.model_dump(),
                     calibration={cid: {"pose": cam.to_dict()} for cid, cam in rig.items()})
    live.subscribe(lambda e: rec.add_event(e.to_dict()))
    world.throw(ThrowParams(target=(0, 103)), at=1.0)
    world.throw(ThrowParams(target=(-50, -80)), at=2.2)
    fps = 15.0
    n = 0
    t = 0.0
    while t < 3.6:
        frames = {}
        for cid in rig:
            clock["t"] = t
            frames[cid] = Frame(cid, world.render(cid, t), t, n)
            rec.add_frame(frames[cid])
        live.process_frameset(frames)
        n += 1
        t += 1 / fps
    summary = rec.stop()
    write_ground_truth(rec.dir, [g.to_dict() for g in world.ground_truth])
    assert summary["frame_counts"] == {cid: n for cid in rig}
    assert len(read_frame_index(rec.dir, "cam1")) == n
    meta = json.loads((rec.dir / "metadata.json").read_text())
    assert meta["synthetic"] is True

    live_darts = [e for e in live_events if e.type == EventType.DART]
    replay_events, info = replay_session(rec.dir)
    replay_darts = [e for e in replay_events if e.type == EventType.DART]
    assert info["framesets"] == n
    assert len(live_darts) == len(replay_darts) == 2
    for a, b in zip(live_darts, replay_darts):
        pa = np.array([a.data["impact"]["x_mm"], a.data["impact"]["y_mm"]])
        pb = np.array([b.data["impact"]["x_mm"], b.data["impact"]["y_mm"]])
        assert np.linalg.norm(pa - pb) < 1e-6  # deterministic (lossless PNG frames)
    ev = evaluate_session(rec.dir)
    assert ev["metrics"]["detected"] == 2 and ev["metrics"]["score_accuracy"] == 1.0
