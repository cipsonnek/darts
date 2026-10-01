"""Pinhole camera with lens distortion and a pose relative to the board.

OpenCV conventions: ``X_cam = R @ X_board + t``; image y points down; distortion uses the
OpenCV model (k1, k2, p1, p2[, k3...]). All board coordinates are in the board frame
described in vision/geometry/board.py.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import cv2
import numpy as np


@dataclass
class BoardLine:
    """A line on the board plane: ``normal · p = offset`` with a unit ``normal``.

    Produced by back-projecting an image line (the dart axis seen by one camera): the true
    impact point lies on it. ``sigma_mm`` is the 1-σ uncertainty perpendicular to the line.
    """

    normal: np.ndarray  # (2,)
    offset: float
    sigma_mm: float = 1.0
    camera_id: str = ""

    def distance(self, p: np.ndarray) -> float:
        return float(self.normal @ np.asarray(p, dtype=np.float64)[:2] - self.offset)

    @property
    def direction(self) -> np.ndarray:
        return np.array([-self.normal[1], self.normal[0]])


@dataclass
class CameraModel:
    K: np.ndarray
    dist: np.ndarray
    R: np.ndarray
    t: np.ndarray
    image_size: tuple[int, int]  # (width, height)
    camera_id: str = ""
    _R_inv: np.ndarray = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.K = np.asarray(self.K, dtype=np.float64).reshape(3, 3)
        self.dist = np.asarray(self.dist, dtype=np.float64).reshape(-1)
        self.R = np.asarray(self.R, dtype=np.float64).reshape(3, 3)
        self.t = np.asarray(self.t, dtype=np.float64).reshape(3)
        self.image_size = (int(self.image_size[0]), int(self.image_size[1]))
        self._R_inv = self.R.T

    # ------------------------------------------------------------------ construction
    @classmethod
    def from_rvec(cls, K, dist, rvec, tvec, image_size, camera_id: str = "") -> "CameraModel":
        R, _ = cv2.Rodrigues(np.asarray(rvec, dtype=np.float64).reshape(3, 1))
        return cls(K=K, dist=dist, R=R, t=np.asarray(tvec).reshape(3), image_size=image_size,
                   camera_id=camera_id)

    @classmethod
    def look_at(
        cls,
        position: np.ndarray,
        target: np.ndarray,
        K: np.ndarray,
        image_size: tuple[int, int],
        dist: np.ndarray | None = None,
        up_hint: np.ndarray | None = None,
        roll_deg: float = 0.0,
        camera_id: str = "",
    ) -> "CameraModel":
        """Camera at ``position`` looking at ``target``. ``up_hint`` is the board-frame
        direction that should appear upwards in the image (default: +Z, out of the board)."""
        position = np.asarray(position, dtype=np.float64)
        z_axis = np.asarray(target, dtype=np.float64) - position
        z_axis /= np.linalg.norm(z_axis)
        up = np.array([0.0, 0.0, 1.0]) if up_hint is None else np.asarray(up_hint, float)
        # Image y points down, so the camera's y axis is the negative projected up vector.
        y_axis = -(up - (up @ z_axis) * z_axis)
        if np.linalg.norm(y_axis) < 1e-9:
            y_axis = np.cross(z_axis, np.array([1.0, 0.0, 0.0]))
        y_axis /= np.linalg.norm(y_axis)
        x_axis = np.cross(y_axis, z_axis)
        R = np.stack([x_axis, y_axis, z_axis], axis=0)
        if roll_deg:
            c, s = math.cos(math.radians(roll_deg)), math.sin(math.radians(roll_deg))
            R = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]]) @ R
        t = -R @ position
        return cls(K=K, dist=np.zeros(5) if dist is None else dist, R=R, t=t,
                   image_size=image_size, camera_id=camera_id)

    # ------------------------------------------------------------------ properties
    @property
    def rvec(self) -> np.ndarray:
        rvec, _ = cv2.Rodrigues(self.R)
        return rvec.reshape(3)

    @property
    def center(self) -> np.ndarray:
        """Camera centre in board coordinates."""
        return -self._R_inv @ self.t

    @property
    def optical_axis(self) -> np.ndarray:
        return self._R_inv @ np.array([0.0, 0.0, 1.0])

    def homography(self) -> np.ndarray:
        """Board plane (x, y, 1) → *undistorted* pixel homography: K [r1 r2 t]."""
        H = self.K @ np.column_stack([self.R[:, 0], self.R[:, 1], self.t])
        return H / H[2, 2]

    # ------------------------------------------------------------------ projection
    def to_camera(self, pts_board: np.ndarray) -> np.ndarray:
        pts = np.asarray(pts_board, dtype=np.float64).reshape(-1, 3)
        return pts @ self.R.T + self.t

    def project(self, pts_board: np.ndarray) -> np.ndarray:
        """Board points (N,3) → distorted pixels (N,2)."""
        pts = np.asarray(pts_board, dtype=np.float64).reshape(-1, 1, 3)
        if pts.shape[0] == 0:
            return np.zeros((0, 2))
        px, _ = cv2.projectPoints(pts, self.rvec, self.t, self.K, self.dist)
        return px.reshape(-1, 2)

    def in_front(self, pts_board: np.ndarray) -> np.ndarray:
        return self.to_camera(pts_board)[:, 2] > 1e-6

    def undistort_normalized(self, px: np.ndarray) -> np.ndarray:
        """Distorted pixels (N,2) → normalised camera coordinates (x/z, y/z)."""
        pts = np.asarray(px, dtype=np.float64).reshape(-1, 1, 2)
        if pts.shape[0] == 0:
            return np.zeros((0, 2))
        und = cv2.undistortPoints(pts, self.K, self.dist,
                                  criteria=(cv2.TERM_CRITERIA_COUNT | cv2.TERM_CRITERIA_EPS, 40, 1e-9))
        return und.reshape(-1, 2)

    def undistort_pixels(self, px: np.ndarray) -> np.ndarray:
        """Distorted pixels → ideal (distortion-free) pixels with the same K."""
        n = self.undistort_normalized(px)
        return n @ self.K[:2, :2].T + self.K[:2, 2]

    def normalized_to_pixels(self, n: np.ndarray) -> np.ndarray:
        """Normalised coordinates → distorted pixels."""
        n = np.asarray(n, dtype=np.float64).reshape(-1, 2)
        pts = np.concatenate([n, np.ones((len(n), 1))], axis=1).reshape(-1, 1, 3)
        px, _ = cv2.projectPoints(pts, np.zeros(3), np.zeros(3), self.K, self.dist)
        return px.reshape(-1, 2)

    # ------------------------------------------------------------------ back-projection
    def rays(self, px: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Pixels → (origin (3,), unit directions (N,3)) in board coordinates."""
        n = self.undistort_normalized(px)
        d_cam = np.concatenate([n, np.ones((len(n), 1))], axis=1)
        d = d_cam @ self._R_inv.T
        d /= np.linalg.norm(d, axis=1, keepdims=True)
        return self.center, d

    def pixels_to_board(self, px: np.ndarray, plane_z: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
        """Intersect pixel rays with the plane Z = plane_z. Returns ((N,2) xy, valid mask)."""
        origin, d = self.rays(px)
        dz = d[:, 2]
        with np.errstate(divide="ignore", invalid="ignore"):
            s = (plane_z - origin[2]) / dz
        valid = (np.abs(dz) > 1e-9) & (s > 0)
        pts = origin[None, :] + s[:, None] * d
        return pts[:, :2], valid

    def pixel_to_board(self, px: tuple[float, float]) -> np.ndarray | None:
        xy, valid = self.pixels_to_board(np.array([px], dtype=np.float64))
        return xy[0] if valid[0] else None

    def board_jacobian(self, px: tuple[float, float], eps: float = 0.5) -> np.ndarray | None:
        """d(board xy)/d(pixel) at a pixel, by central differences (2x2)."""
        p = np.array(px, dtype=np.float64)
        probes = np.array([p + [eps, 0], p - [eps, 0], p + [0, eps], p - [0, eps]])
        xy, valid = self.pixels_to_board(probes)
        if not valid.all():
            return None
        return np.column_stack([(xy[0] - xy[1]) / (2 * eps), (xy[2] - xy[3]) / (2 * eps)])

    # ------------------------------------------------------------------ lines and planes
    def plane_from_normalized_line(self, a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, float]:
        """The 3D plane through the camera centre that contains the rays of two normalised
        image points. Returns (unit normal n, offset d) with n · X = d in board coordinates."""
        ra = np.array([a[0], a[1], 1.0])
        rb = np.array([b[0], b[1], 1.0])
        n_cam = np.cross(ra, rb)
        n = self._R_inv @ n_cam
        n /= np.linalg.norm(n)
        return n, float(n @ self.center)

    def board_line_from_plane(self, n: np.ndarray, d: float) -> BoardLine | None:
        """Intersection of a plane n·X = d with the board plane Z = 0."""
        nxy = np.asarray(n[:2], dtype=np.float64)
        norm = np.linalg.norm(nxy)
        if norm < 1e-6:
            return None
        return BoardLine(normal=nxy / norm, offset=float(d / norm), camera_id=self.camera_id)

    def board_line_from_image_line(self, p0_px: np.ndarray, p1_px: np.ndarray) -> BoardLine | None:
        """Back-project an image line given by two *distorted* pixel points."""
        n0, n1 = self.undistort_normalized(np.array([p0_px, p1_px], dtype=np.float64))
        n, d = self.plane_from_normalized_line(n0, n1)
        return self.board_line_from_plane(n, d)

    def project_board_line(self, line: BoardLine, half_length_mm: float = 250.0,
                           samples: int = 40) -> np.ndarray:
        """Sample a board line and project it into the image (for overlays)."""
        p0 = line.normal * line.offset
        s = np.linspace(-half_length_mm, half_length_mm, samples)
        pts = p0[None, :] + s[:, None] * line.direction[None, :]
        pts3 = np.concatenate([pts, np.zeros((samples, 1))], axis=1)
        mask = self.in_front(pts3)
        return self.project(pts3[mask])

    # ------------------------------------------------------------------ serialisation
    def to_dict(self) -> dict:
        return {
            "camera_id": self.camera_id,
            "K": self.K.tolist(),
            "dist": self.dist.tolist(),
            "R": self.R.tolist(),
            "rvec": self.rvec.tolist(),
            "t": self.t.tolist(),
            "image_size": list(self.image_size),
            "position_mm": self.center.tolist(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CameraModel":
        R = data.get("R")
        if R is None:
            R, _ = cv2.Rodrigues(np.asarray(data["rvec"], dtype=np.float64))
        return cls(K=np.asarray(data["K"]), dist=np.asarray(data["dist"]), R=np.asarray(R),
                   t=np.asarray(data["t"]), image_size=tuple(data["image_size"]),
                   camera_id=data.get("camera_id", ""))

    def scaled(self, sx: float, sy: float | None = None) -> "CameraModel":
        """The same camera for an image resized by (sx, sy)."""
        sy = sx if sy is None else sy
        S = np.diag([sx, sy, 1.0])
        K = S @ self.K
        # Pixel centres: u' = s·(u + 0.5) − 0.5.
        K[0, 2] += 0.5 * (sx - 1.0)
        K[1, 2] += 0.5 * (sy - 1.0)
        return CameraModel(K=K, dist=self.dist.copy(), R=self.R.copy(), t=self.t.copy(),
                           image_size=(round(self.image_size[0] * sx), round(self.image_size[1] * sy)),
                           camera_id=self.camera_id)


def default_intrinsics(width: int, height: int, hfov_deg: float = 70.0) -> np.ndarray:
    """A plausible K for an uncalibrated camera (square pixels, centred principal point)."""
    f = (width / 2.0) / math.tan(math.radians(hfov_deg) / 2.0)
    return np.array([[f, 0, width / 2.0], [0, f, height / 2.0], [0, 0, 1.0]])
