"""Camera-to-board calibration: automatic or manual initialisation, edge-based refinement,
quality grading and the derived board parameters shown to the user."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

import cv2
import numpy as np

from vision.board_detection.rings import BoardDetector
from vision.calibration.intrinsics import IntrinsicsResult
from vision.calibration.refine import EdgeAligner, RefineResult
from vision.config import VisionConfig
from vision.geometry.board import BoardGeometry
from vision.geometry.camera_model import CameraModel, default_intrinsics

log = logging.getLogger("vision.calibration")

STANDARD_MANUAL_POINTS = ["double_outer:20|1", "double_outer:6|10", "double_outer:3|19", "double_outer:11|14"]


def landmarks(board: BoardGeometry) -> dict[str, tuple[float, float]]:
    """Named board points a user can click: the bull and every wire crossing of a sector
    wire with a ring wire, e.g. ``double_outer:20|1``."""
    out: dict[str, tuple[float, float]] = {"bull": (0.0, 0.0)}
    order = board.sector_order
    n = len(order)
    for ring in ("triple_inner", "triple_outer", "double_inner", "double_outer"):
        r = board.ring_radii[ring]
        for j, angle in enumerate(board.sector_boundary_angles()):
            out[f"{ring}:{order[(j - 1) % n]}|{order[j]}"] = board.from_polar(r, angle)
    return out


@dataclass
class BoardCalibration:
    ok: bool
    camera: CameraModel | None = None
    method: str = ""
    intrinsics_source: str = ""
    grade: str = "poor"
    metrics: dict = field(default_factory=dict)
    derived: dict = field(default_factory=dict)
    checks: list[dict] = field(default_factory=list)
    reason: str | None = None
    detection: dict | None = None

    def to_dict(self) -> dict:
        return {"ok": self.ok, "method": self.method, "intrinsics_source": self.intrinsics_source,
                "grade": self.grade, "metrics": self.metrics, "derived": self.derived, "checks": self.checks,
                "reason": self.reason, "detection": self.detection,
                "camera": self.camera.to_dict() if self.camera is not None else None}


def calibrate_board(
    image: np.ndarray,
    config: VisionConfig,
    camera_id: str,
    intrinsics: IntrinsicsResult | None = None,
    azimuth_prior_deg: float | None = None,
    hint_px: tuple[float, float] | None = None,
    manual_points: dict[str, tuple[float, float]] | None = None,
) -> BoardCalibration:
    board = BoardGeometry(config.board)
    h, w = image.shape[:2]
    if intrinsics is not None and tuple(intrinsics.image_size) == (w, h):
        K, dist, source = intrinsics.K.copy(), np.asarray(intrinsics.dist, float).copy(), "calibrated"
    else:
        K, dist, source = default_intrinsics(w, h), np.zeros(5), "estimated_from_board"

    detection_summary = None
    if manual_points:
        lm = landmarks(board)
        unknown = [k for k in manual_points if k not in lm]
        if unknown:
            return BoardCalibration(False, reason=f"unknown landmark ids: {unknown}")
        if len(manual_points) < 4:
            return BoardCalibration(False, reason="need at least 4 points")
        obj = np.array([[*lm[k], 0.0] for k in manual_points], dtype=np.float64)
        img = np.array([manual_points[k] for k in manual_points], dtype=np.float64)
        ok, rvec, tvec = cv2.solvePnP(obj, img.reshape(-1, 1, 2), K, dist, flags=cv2.SOLVEPNP_IPPE)
        if not ok:
            return BoardCalibration(False, reason="pose from clicked points failed")
        initial = CameraModel.from_rvec(K, dist, rvec, tvec, (w, h), camera_id)
        method = "manual"
    else:
        det = BoardDetector(board, config.board_detection).detect(
            image, K, dist, azimuth_prior_deg=azimuth_prior_deg, hint_px=hint_px, camera_id=camera_id)
        detection_summary = det.summary()
        if not det.ok or det.chosen is None or det.chosen.camera is None:
            return BoardCalibration(False, reason=det.reason, detection=detection_summary)
        initial = det.chosen.camera
        method = "auto"

    aligner = EdgeAligner(board)
    estimate = source != "calibrated"
    try:
        refined = aligner.refine(image, initial, refine_focal=estimate, refine_k1=estimate)
    except Exception as exc:  # noqa: BLE001 - surface as a calibration failure
        log.exception("edge refinement failed")
        return BoardCalibration(False, reason=f"refinement failed: {exc}", detection=detection_summary)

    grade, checks = grade_calibration(refined, config, source)
    result = BoardCalibration(
        ok=grade != "failed", camera=refined.camera, method=method, intrinsics_source=source, grade=grade,
        metrics=refined.metrics(), derived=derived_parameters(refined.camera, board), checks=checks,
        detection=detection_summary,
        reason=None if grade != "failed" else "board edges do not match the model (wrong points or not a standard board?)",
    )
    log.info("board calibration", extra={"camera": camera_id, "method": method, "grade": grade,
                                         **refined.metrics()})
    return result


def grade_calibration(r: RefineResult, config: VisionConfig, source: str) -> tuple[str, list[dict]]:
    c = config.calibration
    checks = [
        {"name": "Edge alignment RMS", "value": round(r.edge_rms_px, 3), "unit": "px",
         "status": _status(r.edge_rms_px, c.good_edge_rms_px, c.fair_edge_rms_px, lower_is_better=True)},
        {"name": "Model edges confirmed", "value": round(r.inlier_fraction * 100, 1), "unit": "%",
         "status": _status(r.inlier_fraction, c.good_inlier_fraction, c.fair_inlier_fraction, lower_is_better=False)},
        {"name": "Pose uncertainty (board)", "value": round(r.pose_sigma_mm, 3), "unit": "mm",
         "status": _status(r.pose_sigma_mm, c.good_pose_sigma_mm, c.fair_pose_sigma_mm, lower_is_better=True)},
        {"name": "Intrinsics", "value": source, "unit": "",
         "status": "good" if source == "calibrated" else "fair"},
    ]
    statuses = [ch["status"] for ch in checks]
    if r.inlier_fraction < 0.35 or not math.isfinite(r.edge_rms_px):
        return "failed", checks
    if "poor" in statuses:
        return "poor", checks
    if "fair" in statuses:
        return "fair", checks
    return "good", checks


def _status(v: float, good: float, fair: float, lower_is_better: bool) -> str:
    if lower_is_better:
        return "good" if v <= good else "fair" if v <= fair else "poor"
    return "good" if v >= good else "fair" if v >= fair else "poor"


def derived_parameters(cam: CameraModel, board: BoardGeometry) -> dict:
    """Human-meaningful quantities: where the board is in the image and how the camera sits."""
    center_px = cam.project(np.zeros((1, 3)))[0]
    top_px = cam.project(np.array([[0.0, board.ring_radii["double_outer"], 0.0]]))[0]
    J = cam.board_jacobian(tuple(center_px))
    mm_per_px = None
    worst_mm_per_px = None
    if J is not None:
        sv = np.linalg.svd(J, compute_uv=False)
        mm_per_px = float(math.sqrt(abs(np.linalg.det(J))))
        worst_mm_per_px = float(sv[0])
    c = cam.center
    normal_cam = cam.R[:, 2]
    view_angle = math.degrees(math.acos(min(1.0, abs(float(normal_cam @ (cam.to_camera(np.zeros((1, 3)))[0]
                                                                         / np.linalg.norm(cam.to_camera(np.zeros((1, 3)))[0])))))))
    outline = cam.project(board.circle_points(board.ring_radii["double_outer"], 72))
    return {
        "board_center_px": [round(float(center_px[0]), 2), round(float(center_px[1]), 2)],
        "orientation_deg": round(math.degrees(math.atan2(top_px[0] - center_px[0], -(top_px[1] - center_px[1]))), 2),
        "double_ring_extent_px": [round(float(np.ptp(outline[:, 0])), 1), round(float(np.ptp(outline[:, 1])), 1)],
        "mm_per_px_at_center": None if mm_per_px is None else round(mm_per_px, 4),
        "worst_mm_per_px_at_center": None if worst_mm_per_px is None else round(worst_mm_per_px, 4),
        "camera_position_mm": [round(float(v), 1) for v in c],
        "camera_distance_mm": round(float(np.linalg.norm(c)), 1),
        "camera_azimuth_deg": round(math.degrees(math.atan2(c[0], c[1])) % 360.0, 1),
        "camera_elevation_deg": round(math.degrees(math.atan2(c[2], math.hypot(c[0], c[1]))), 1),
        "viewing_angle_to_normal_deg": round(view_angle, 1),
        "focal_px": round(float(cam.K[0, 0]), 2),
    }
