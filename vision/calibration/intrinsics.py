"""Camera intrinsics and lens distortion from a ChArUco target.

ChArUco is preferred over a plain chessboard because corners are identified individually,
so partially visible targets (common when covering the image corners) still contribute.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

import cv2
import numpy as np

from vision.config import CalibrationConfig

log = logging.getLogger("vision.calibration")

_GRID = (8, 6)  # coverage grid over the image


@dataclass
class IntrinsicsResult:
    K: np.ndarray
    dist: np.ndarray
    image_size: tuple[int, int]
    rms_px: float
    n_views: int
    per_view_rms_px: list[float]
    coverage: float
    method: str = "charuco"
    calibrated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "K": self.K.tolist(), "dist": self.dist.ravel().tolist(), "image_size": list(self.image_size),
            "rms_px": self.rms_px, "n_views": self.n_views, "per_view_rms_px": self.per_view_rms_px,
            "coverage": self.coverage, "method": self.method, "calibrated_at": self.calibrated_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "IntrinsicsResult":
        return cls(K=np.asarray(d["K"], float), dist=np.asarray(d["dist"], float),
                   image_size=tuple(d["image_size"]), rms_px=float(d.get("rms_px", 0.0)),
                   n_views=int(d.get("n_views", 0)), per_view_rms_px=list(d.get("per_view_rms_px", [])),
                   coverage=float(d.get("coverage", 0.0)), method=d.get("method", "charuco"),
                   calibrated_at=d.get("calibrated_at", ""))


def make_charuco_board(cfg: CalibrationConfig) -> cv2.aruco.CharucoBoard:
    dictionary = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, cfg.charuco_dictionary))
    return cv2.aruco.CharucoBoard((cfg.charuco_squares_x, cfg.charuco_squares_y),
                                  cfg.charuco_square_mm, cfg.charuco_marker_mm, dictionary)


def render_charuco(cfg: CalibrationConfig, pixels_per_mm: float = 10.0, margin_mm: float = 10.0) -> np.ndarray:
    """Printable target image (print at 100% scale: ``pixels_per_mm`` → DPI = ppm·25.4)."""
    board = make_charuco_board(cfg)
    w_mm = cfg.charuco_squares_x * cfg.charuco_square_mm + 2 * margin_mm
    h_mm = cfg.charuco_squares_y * cfg.charuco_square_mm + 2 * margin_mm
    size = (int(round(w_mm * pixels_per_mm)), int(round(h_mm * pixels_per_mm)))
    return board.generateImage(size, marginSize=int(round(margin_mm * pixels_per_mm)), borderBits=1)


@dataclass
class ViewDetection:
    accepted: bool
    n_corners: int
    reason: str | None = None
    corners: np.ndarray | None = None
    ids: np.ndarray | None = None


class IntrinsicsCalibrator:
    """Collect ChArUco views (from the live camera, via the web UI) and solve."""

    def __init__(self, cfg: CalibrationConfig, image_size: tuple[int, int]) -> None:
        self.cfg = cfg
        self.board = make_charuco_board(cfg)
        self.detector = cv2.aruco.CharucoDetector(self.board)
        self.image_size = image_size
        self.views: list[tuple[np.ndarray, np.ndarray]] = []
        self.coverage_grid = np.zeros(_GRID[::-1], dtype=int)

    def detect(self, image: np.ndarray) -> ViewDetection:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
        corners, ids, _, _ = self.detector.detectBoard(gray)
        n = 0 if ids is None else len(ids)
        if n < 6:
            return ViewDetection(False, n, "target not found (need ≥6 ChArUco corners)")
        return ViewDetection(True, n, None, corners.reshape(-1, 2), ids.reshape(-1))

    def add_view(self, image: np.ndarray) -> ViewDetection:
        if (image.shape[1], image.shape[0]) != self.image_size:
            return ViewDetection(False, 0, "image size differs from the calibration size")
        det = self.detect(image)
        if not det.accepted:
            return det
        assert det.corners is not None and det.ids is not None
        # Reject near-duplicates: the same pose adds nothing.
        for c, i in self.views:
            common, a, b = np.intersect1d(i, det.ids, return_indices=True)
            if len(common) >= 0.8 * len(det.ids) and np.median(np.linalg.norm(c[a] - det.corners[b], axis=1)) < 12:
                return ViewDetection(False, det.n_corners, "too similar to a previous view — move the target")
        self.views.append((det.corners, det.ids))
        w, h = self.image_size
        gx = np.clip((det.corners[:, 0] / w * _GRID[0]).astype(int), 0, _GRID[0] - 1)
        gy = np.clip((det.corners[:, 1] / h * _GRID[1]).astype(int), 0, _GRID[1] - 1)
        self.coverage_grid[gy, gx] += 1
        return det

    @property
    def coverage(self) -> float:
        return float((self.coverage_grid > 0).mean())

    def status(self) -> dict:
        return {"views": len(self.views), "min_views": self.cfg.min_intrinsic_views,
                "coverage": round(self.coverage, 3), "coverage_grid": self.coverage_grid.tolist()}

    def calibrate(self) -> IntrinsicsResult:
        if len(self.views) < self.cfg.min_intrinsic_views:
            raise ValueError(f"need at least {self.cfg.min_intrinsic_views} views, have {len(self.views)}")
        obj_pts, img_pts = [], []
        for corners, ids in self.views:
            o, i = self.board.matchImagePoints(corners.reshape(-1, 1, 2), ids.reshape(-1, 1))
            if o is not None and len(o) >= 6:
                obj_pts.append(o.astype(np.float32))
                img_pts.append(i.astype(np.float32))
        flags = cv2.CALIB_RATIONAL_MODEL if len(obj_pts) >= 20 else 0
        rms, K, dist, rvecs, tvecs = cv2.calibrateCamera(obj_pts, img_pts, self.image_size, None, None, flags=flags)
        per_view = []
        for o, i, r, t in zip(obj_pts, img_pts, rvecs, tvecs):
            p, _ = cv2.projectPoints(o, r, t, K, dist)
            per_view.append(float(np.sqrt(np.mean(np.sum((p.reshape(-1, 2) - i.reshape(-1, 2)) ** 2, axis=1)))))
        res = IntrinsicsResult(K=K, dist=dist.ravel(), image_size=self.image_size, rms_px=float(rms),
                               n_views=len(obj_pts), per_view_rms_px=per_view, coverage=self.coverage)
        log.info("intrinsics calibrated", extra={"rms_px": res.rms_px, "views": res.n_views,
                                                 "coverage": res.coverage})
        return res
