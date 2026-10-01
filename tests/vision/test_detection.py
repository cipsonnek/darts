"""Single-settle detection on rendered frames: change detection → candidates → fusion."""

from __future__ import annotations

import numpy as np
import pytest

from vision.config import VisionConfig
from vision.dart_detection.change import compute_change
from vision.dart_detection.candidates import extract_candidates
from vision.engine import board_roi
from vision.fusion.fusion import fuse
from vision.scoring.probability import score_distribution
from vision.simulation.world import SimulatedWorld, ThrowParams

CFG = VisionConfig()


def _detect(rig, board, before, after, empty):
    cands, support = {}, {}
    for cid, cam in rig.items():
        roi = board_roi(cam, board)
        ch = compute_change(before[cid], after[cid], roi, CFG.detection, empty=empty[cid])
        cands[cid] = extract_candidates(ch.added, ch.bbox, ch.diff, cam, CFG.detection, cid, roi=roi)
        support[cid] = ch.full_mask("changed", after[cid].shape[:2])
    return fuse(rig, cands, CFG.fusion, support=support), cands


def _render(world, t):
    return {cid: world.render(cid, t) for cid in world.cameras}


@pytest.fixture()
def world(sim_rig):
    return SimulatedWorld(sim_rig, seed=21)


@pytest.mark.parametrize("target", [(0.0, 103.0), (-95.0, 60.0), (40.0, -150.0), (3.0, 2.0), (120.0, -40.0)])
def test_single_dart_detected_and_scored(world, sim_rig, board, target) -> None:
    empty = _render(world, 0.0)
    gt = world.throw(ThrowParams(target=target, tilt_up_deg=10, tilt_right_deg=-4), at=1.0)
    after = _render(world, 2.0)
    fused, _ = _detect(sim_rig, board, empty, after, empty)
    assert len(fused) == 1
    f = fused[0]
    err = float(np.linalg.norm(f.impact - gt.impact))
    assert err < 2.0, err
    assert len(f.cameras) >= 2
    best = score_distribution(board, f.impact, f.cov + np.eye(2) * 0.36)[0]
    if board.distance_to_boundary(*gt.impact) > 2.0:
        assert best.score.label == gt.score.label


def test_existing_darts_are_not_rescored(world, sim_rig, board) -> None:
    empty = _render(world, 0.0)
    world.throw(ThrowParams(target=(0, 103)), at=1.0)
    world.throw(ThrowParams(target=(60, 90)), at=2.0)
    before = _render(world, 3.0)
    gt = world.throw(ThrowParams(target=(-70, -60)), at=3.5)
    after = _render(world, 4.5)
    fused, _ = _detect(sim_rig, board, before, after, empty)
    assert len(fused) == 1
    assert np.linalg.norm(fused[0].impact - gt.impact) < 2.5


def test_overlapping_dart_next_to_existing(world, sim_rig, board) -> None:
    """A new dart landing 6 mm from an existing one (partial occlusion in some views)."""
    empty = _render(world, 0.0)
    world.throw(ThrowParams(target=(0, 103), tilt_up_deg=8, tilt_right_deg=0), at=1.0)
    before = _render(world, 2.0)
    gt = world.throw(ThrowParams(target=(6, 101), tilt_up_deg=12, tilt_right_deg=5), at=2.5)
    after = _render(world, 3.5)
    fused, _ = _detect(sim_rig, board, before, after, empty)
    assert len(fused) >= 1
    assert np.linalg.norm(fused[0].impact - gt.impact) < 3.0


def test_lighting_change_produces_no_new_dart(world, sim_rig, board) -> None:
    """A lighting change can make an existing dart look different; anything found must be
    that existing dart (same place), which the engine then recognises as known."""
    empty = _render(world, 0.0)
    old = world.throw(ThrowParams(target=(30, 50)), at=1.0)
    before = _render(world, 2.0)
    world.set_lighting("warm", at=2.5)
    after = _render(world, 3.0)
    fused, _ = _detect(sim_rig, board, before, after, empty)
    for f in fused:
        assert np.linalg.norm(f.impact - old.impact) < 4.0


def test_dim_lighting_still_detects(sim_rig, board) -> None:
    world = SimulatedWorld(sim_rig, seed=22, lighting="dim")
    empty = _render(world, 0.0)
    gt = world.throw(ThrowParams(target=(-40, 120)), at=1.0)
    after = _render(world, 2.0)
    fused, _ = _detect(sim_rig, board, empty, after, empty)
    assert len(fused) == 1
    assert np.linalg.norm(fused[0].impact - gt.impact) < 2.5


def test_removed_dart_is_not_an_added_dart(world, sim_rig, board) -> None:
    empty = _render(world, 0.0)
    world.throw(ThrowParams(target=(0, 103)), at=1.0)
    before = _render(world, 2.0)
    world.remove_darts(at=2.2, duration=1.0)
    after = _render(world, 4.0)
    fused, _ = _detect(sim_rig, board, before, after, empty)
    assert fused == []
    for cid, cam in sim_rig.items():
        ch = compute_change(before[cid], after[cid], board_roi(cam, board), CFG.detection, empty=empty[cid])
        assert np.count_nonzero(ch.removed) > np.count_nonzero(ch.added)
