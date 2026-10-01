"""Calibration recovers known camera poses from rendered images."""

from __future__ import annotations

import math

import cv2
import numpy as np
import pytest

from vision.calibration.board_pose import calibrate_board, landmarks
from vision.calibration.intrinsics import IntrinsicsCalibrator, IntrinsicsResult, make_charuco_board, render_charuco
from vision.calibration.refine import EdgeAligner
from vision.calibration.validation import board_shift_mm, validate_pose
from vision.config import CalibrationConfig, ValidationConfig, VisionConfig
from vision.geometry.camera_model import CameraModel
from vision.simulation.rig import default_rig_specs
from vision.simulation.world import SimulatedWorld


@pytest.fixture(scope="module")
def world(sim_rig):
    return SimulatedWorld(sim_rig, seed=4)


def _intr(cam: CameraModel) -> IntrinsicsResult:
    return IntrinsicsResult(K=cam.K.copy(), dist=cam.dist.copy(), image_size=cam.image_size, rms_px=0.3, n_views=20,
                            per_view_rms_px=[], coverage=1.0)


@pytest.mark.parametrize("cid", ["cam1", "cam2", "cam3"])
def test_automatic_board_calibration(world, sim_rig, cid) -> None:
    cam = sim_rig[cid]
    img = world.render(cid, 0.0)
    az = {s.camera_id: s.azimuth_deg for s in default_rig_specs(960, 540, jitter_seed=3)}[cid]
    res = calibrate_board(img, VisionConfig(), cid, intrinsics=_intr(cam), azimuth_prior_deg=round(az / 30) * 30)
    assert res.ok, res.reason
    assert res.grade in ("good", "fair")
    assert board_shift_mm(cam, res.camera) < 0.3
    assert res.metrics["edge_rms_px"] < 0.8


def test_board_only_intrinsics_estimate(world, sim_rig) -> None:
    cam = sim_rig["cam1"]
    res = calibrate_board(world.render("cam1", 0.0), VisionConfig(), "cam1", intrinsics=None, azimuth_prior_deg=0)
    assert res.ok, res.reason
    assert res.intrinsics_source == "estimated_from_board"
    assert abs(res.camera.K[0, 0] / cam.K[0, 0] - 1) < 0.02
    assert board_shift_mm(cam, res.camera) < 1.0


def test_manual_four_point_calibration(world, sim_rig, board) -> None:
    cam = sim_rig["cam2"]
    lm = landmarks(board)
    rng = np.random.default_rng(0)
    ids = ["double_outer:20|1", "double_outer:6|10", "double_outer:3|19", "double_outer:11|14", "bull"]
    pts = {}
    for k in ids:
        p = cam.project(np.array([[*lm[k], 0.0]]))[0] + rng.normal(0, 1.5, 2)  # imprecise clicks
        pts[k] = (float(p[0]), float(p[1]))
    res = calibrate_board(world.render("cam2", 0.0), VisionConfig(), "cam2", intrinsics=_intr(cam), manual_points=pts)
    assert res.ok and res.method == "manual"
    assert board_shift_mm(cam, res.camera) < 0.3


def test_rotation_ambiguity_requires_prior_or_hint(world, sim_rig) -> None:
    cam = sim_rig["cam1"]
    img = world.render("cam1", 0.0)
    res = calibrate_board(img, VisionConfig(), "cam1", intrinsics=_intr(cam), azimuth_prior_deg=None)
    assert not res.ok and "ambiguous" in (res.reason or "")
    # One click inside the single 20 resolves it.
    hint = cam.project(np.array([[0.0, 140.0, 0.0]]))[0]
    res2 = calibrate_board(img, VisionConfig(), "cam1", intrinsics=_intr(cam), hint_px=(float(hint[0]), float(hint[1])))
    assert res2.ok
    assert board_shift_mm(cam, res2.camera) < 0.3


def test_validation_detects_movement(world, sim_rig, board) -> None:
    cam = sim_rig["cam3"]
    img = world.render("cam3", 0.0)
    al = EdgeAligner(board)
    cfg = ValidationConfig()
    ok = validate_pose(img, cam, al, cfg)
    assert ok.status == "ok" and ok.shift_mm < 0.5
    moved_cam = CameraModel.from_rvec(cam.K, cam.dist, cam.rvec + np.array([0.0, 0.004, 0.0]),
                                      cam.t + np.array([3.0, 0.0, 0.0]), cam.image_size, "cam3")
    moved = validate_pose(img, moved_cam, al, cfg)
    assert moved.status in ("warning", "moved")
    assert moved.shift_mm > cfg.max_shift_mm


def _render_target(K, dist, size, rvec, tvec, target_img, mm_per_px):
    """Project a planar target image with a known pose (Z=0 plane, mm) into a camera."""
    w, h = size
    S = np.array([[mm_per_px, 0, 0], [0, mm_per_px, 0], [0, 0, 1.0]])
    R, _ = cv2.Rodrigues(rvec)
    H = K @ np.column_stack([R[:, 0], R[:, 1], tvec]) @ S
    ideal = cv2.warpPerspective(target_img, H, (w, h), borderValue=200)
    xs, ys = np.meshgrid(np.arange(w, dtype=np.float64), np.arange(h, dtype=np.float64))
    und = cv2.undistortPoints(np.stack([xs.ravel(), ys.ravel()], 1).reshape(-1, 1, 2), K, dist, P=K).reshape(h, w, 2)
    return cv2.remap(ideal, und[..., 0].astype(np.float32), und[..., 1].astype(np.float32), cv2.INTER_LINEAR,
                     borderValue=200)


def test_charuco_intrinsics_recovered() -> None:
    cfg = CalibrationConfig()
    w, h = 960, 540
    K = np.array([[700.0, 0, 483.0], [0, 700.0, 268.0], [0, 0, 1]])
    dist = np.array([-0.12, 0.04, 0.0005, -0.0003, 0.0])
    target = render_charuco(cfg, pixels_per_mm=4.0, margin_mm=0)
    if target.ndim == 2:
        target = cv2.cvtColor(target, cv2.COLOR_GRAY2BGR)
    cal = IntrinsicsCalibrator(cfg, (w, h))
    rng = np.random.default_rng(2)
    accepted = 0
    for i in range(30):
        rvec = np.array([rng.uniform(-0.5, 0.5), rng.uniform(-0.5, 0.5), rng.uniform(-0.3, 0.3)])
        tvec = np.array([rng.uniform(-150, 30), rng.uniform(-110, 10), rng.uniform(380, 650)])
        img = _render_target(K, dist, (w, h), rvec, tvec, target, 0.25)
        img = np.clip(img.astype(np.float32) + rng.normal(0, 1.5, img.shape), 0, 255).astype(np.uint8)
        if cal.add_view(img).accepted:
            accepted += 1
    assert accepted >= cfg.min_intrinsic_views
    res = cal.calibrate()
    assert res.rms_px < 0.5
    assert abs(res.K[0, 0] - 700.0) / 700.0 < 0.01
    assert abs(res.K[0, 2] - 483.0) < 4 and abs(res.K[1, 2] - 268.0) < 4
    # Held-out validation: new target poses, pose solved with the *estimated* intrinsics,
    # reprojection error must stay small (this is what matters for board calibration).
    board = make_charuco_board(cfg)
    errs = []
    for i in range(6):
        rvec = np.array([rng.uniform(-0.4, 0.4), rng.uniform(-0.4, 0.4), rng.uniform(-0.2, 0.2)])
        tvec = np.array([rng.uniform(-140, 20), rng.uniform(-100, 0), rng.uniform(400, 600)])
        img = _render_target(K, dist, (w, h), rvec, tvec, target, 0.25)
        det = cal.detect(img)
        if not det.accepted:
            continue
        obj, imgp = board.matchImagePoints(det.corners.reshape(-1, 1, 2), det.ids.reshape(-1, 1))
        ok, rv, tv = cv2.solvePnP(obj, imgp, res.K, res.dist)
        proj, _ = cv2.projectPoints(obj, rv, tv, res.K, res.dist)
        errs.append(float(np.sqrt(np.mean(np.sum((proj.reshape(-1, 2) - imgp.reshape(-1, 2)) ** 2, axis=1)))))
    assert len(errs) >= 3
    assert max(errs) < 0.6
    assert make_charuco_board(cfg) is not None
