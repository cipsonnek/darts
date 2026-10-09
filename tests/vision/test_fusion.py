"""Fusion geometry with exact synthetic observations (no rendering)."""

from __future__ import annotations

import numpy as np

from vision.config import FusionConfig
from vision.dart_detection.candidates import DartCandidate
from vision.fusion.fusion import fuse, solve, make_observation
from vision.geometry.lines import Line2D
from vision.scoring.probability import score_distribution


def _cand(cam, p0, axis, cid, tip_offset_px=(0.0, 0.0), conf=1.0):
    pts = cam.project(np.array([p0, p0 + 120 * axis]))
    tip = pts[0] + np.asarray(tip_offset_px)
    und = cam.undistort_pixels(pts)
    d = und[1] - und[0]
    line = Line2D(point=und[0], direction=d / np.linalg.norm(d))
    x0, y0 = int(tip[0]) - 4, int(tip[1]) - 4  # small mask around the tip (distinct per dart)
    return DartCandidate(cid, tip, pts[1], line, 0.3, 40, float(np.linalg.norm(d)), 8.0, True, conf, 500,
                         (x0, y0, x0 + 8, y0 + 8), np.full((8, 8), 255, np.uint8))


def _dart(xy, tilt=(0.1, 0.2)):
    p0 = np.array([xy[0], xy[1], 0.0])
    a = np.array([tilt[0], tilt[1], 1.0])
    return p0, a / np.linalg.norm(a)


def test_three_camera_fusion_is_exact(sim_rig) -> None:
    p0, a = _dart((37.0, -82.0))
    cands = {cid: [_cand(cam, p0, a, cid)] for cid, cam in sim_rig.items()}
    res = fuse(sim_rig, cands, FusionConfig())
    assert len(res) == 1
    assert np.linalg.norm(res[0].impact - p0[:2]) < 0.05
    assert np.allclose(res[0].axis, a, atol=1e-3)


def test_wrong_tip_does_not_drag_solution(sim_rig) -> None:
    p0, a = _dart((-60.0, 40.0))
    cands = {cid: [_cand(cam, p0, a, cid)] for cid, cam in sim_rig.items()}
    # One camera reports a tip 25 px off along the dart (e.g. shadow attached to the point).
    cam = sim_rig["cam2"]
    pts = cam.project(np.array([p0, p0 + 120 * a]))
    along = (pts[1] - pts[0]) / np.linalg.norm(pts[1] - pts[0])
    cands["cam2"] = [_cand(cam, p0, a, "cam2", tip_offset_px=-25 * along)]
    res = fuse(sim_rig, cands, FusionConfig())
    assert np.linalg.norm(res[0].impact - p0[:2]) < 0.3


def test_outlier_camera_rejected(sim_rig) -> None:
    p0, a = _dart((10.0, 120.0))
    cands = {cid: [_cand(cam, p0, a, cid)] for cid, cam in sim_rig.items()}
    # cam3 sees a different object (e.g. an older dart) — offset by 15 mm.
    q0, qa = _dart((25.0, 110.0), (-0.1, 0.1))
    cands["cam3"] = [_cand(sim_rig["cam3"], q0, qa, "cam3")]
    res = fuse(sim_rig, cands, FusionConfig())
    best = res[0]
    assert np.linalg.norm(best.impact - p0[:2]) < 0.5
    assert "cam3" not in best.cameras


def test_correspondence_with_two_darts(sim_rig) -> None:
    d1 = _dart((-50.0, 80.0))
    d2 = _dart((70.0, -30.0), (-0.1, 0.25))
    cands = {cid: [_cand(cam, *d1, cid), _cand(cam, *d2, cid)] for cid, cam in sim_rig.items()}
    res = fuse(sim_rig, cands, FusionConfig(), max_darts=3)
    found = sorted([tuple(np.round(r.impact)) for r in res])
    assert found == sorted([(-50.0, 80.0), (70.0, -30.0)])


def test_single_camera_is_weak(sim_rig) -> None:
    p0, a = _dart((0.0, 103.0))
    cands = {"cam1": [_cand(sim_rig["cam1"], p0, a, "cam1")]}
    # Only one camera calibrated: a single view is accepted but poorly constrained.
    res = fuse({"cam1": sim_rig["cam1"]}, cands, FusionConfig())
    assert len(res) == 1
    assert res[0].sigma_mm > 1.0  # poorly constrained along the viewing direction


def test_single_camera_rejected_when_others_available(sim_rig) -> None:
    p0, a = _dart((0.0, 103.0))
    cands = {"cam1": [_cand(sim_rig["cam1"], p0, a, "cam1")]}
    assert fuse(sim_rig, cands, FusionConfig()) == []


def test_score_distribution_on_wire() -> None:
    from vision.geometry.board import BoardGeometry

    b = BoardGeometry()
    x, y = b.from_polar(103.0, 9.0)  # exactly on the 20/1 wire in the triple
    dist = score_distribution(b, np.array([x, y]), np.eye(2) * 0.25)
    labels = {d.score.label: d.probability for d in dist}
    assert set(labels) >= {"T20", "T1"}
    assert abs(labels["T20"] - labels["T1"]) < 0.1
    far = score_distribution(b, np.array([0.0, 60.0]), np.eye(2) * 0.25)
    assert far[0].score.label == "S20" and far[0].probability > 0.999


def test_solve_reports_covariance(sim_rig) -> None:
    p0, a = _dart((-20.0, -120.0))
    cfg = FusionConfig()
    obs = [make_observation(cam, _cand(cam, p0, a, cid), cfg) for cid, cam in sim_rig.items()]
    p, cov, chi2, dof, _ = solve(obs)
    assert np.linalg.norm(p - p0[:2]) < 0.05
    assert np.all(np.linalg.eigvalsh(cov) > 0)
