"""Continuous calibration validation: is the stored pose still consistent with what the
camera sees? Detects moved cameras and a shifted/rotated board without user action."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np

from vision.calibration.refine import EdgeAligner, to_linear
from vision.config import ValidationConfig
from vision.geometry.camera_model import CameraModel

_TEST_POINTS = np.array([[r * math.sin(math.radians(a)), r * math.cos(math.radians(a)), 0.0]
                         for r in (0.0, 60.0, 103.0, 166.0) for a in range(0, 360, 45)])


@dataclass
class ValidationResult:
    camera_id: str
    status: str  # ok | warning | moved | unknown
    alignment: float  # fraction of visible model edges confirmed at the stored pose
    shift_mm: float  # how far board points move if the pose is re-fitted now
    message: str
    checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    refitted: CameraModel | None = None

    def to_dict(self) -> dict:
        return {"camera_id": self.camera_id, "status": self.status, "alignment": round(self.alignment, 3),
                "shift_mm": round(self.shift_mm, 3), "message": self.message, "checked_at": self.checked_at}


def board_shift_mm(a: CameraModel, b: CameraModel) -> float:
    """Max displacement of board points interpreted through pose b when they were imaged
    through pose a — i.e. the scoring error the old calibration would cause now."""
    px = a.project(_TEST_POINTS)
    xy, valid = b.pixels_to_board(px)
    if not valid.any():
        return float("inf")
    return float(np.max(np.linalg.norm(xy[valid] - _TEST_POINTS[valid, :2], axis=1)))


def validate_pose(image: np.ndarray, camera: CameraModel, aligner: EdgeAligner, cfg: ValidationConfig,
                  ignore_mask: np.ndarray | None = None) -> ValidationResult:
    lin = to_linear(image)
    m = aligner.measure(lin, camera, 4.0, ignore_mask=ignore_mask)
    visible = int(m.visible.sum())
    if visible < 50:
        return ValidationResult(camera.camera_id, "unknown", 0.0, float("nan"), "board not visible")
    confirmed = m.valid & (np.abs(m.offsets) <= cfg.edge_tolerance_px)
    alignment = float(confirmed.sum() / visible)
    refit = aligner.refine(image, camera, schedule=(6, 4, 3, 2.5, 2, 2), ignore_mask=ignore_mask, lab=lin)
    shift = board_shift_mm(camera, refit.camera) if refit.inlier_fraction > 0.5 else float("inf")
    if alignment >= cfg.min_alignment and shift <= cfg.max_shift_mm:
        status, msg = "ok", "calibration consistent with the current image"
    elif shift <= 3 * cfg.max_shift_mm and alignment >= cfg.min_alignment * 0.7:
        status, msg = "warning", f"possible small movement ({shift:.1f} mm) — recalibration recommended"
    else:
        status, msg = "moved", "camera or board has moved — recalibrate this camera"
    return ValidationResult(camera.camera_id, status, alignment, shift, msg, refitted=refit.camera)
