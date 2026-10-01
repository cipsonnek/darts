"""Debug overlays drawn onto camera frames (served to the web UI as images/streams)."""

from __future__ import annotations

import math

import cv2
import numpy as np

from vision.geometry.board import BoardGeometry
from vision.geometry.camera_model import CameraModel

LAYERS = ("board", "sectors", "roi", "change", "candidates", "darts", "lines", "labels", "info")

_GREEN = (80, 220, 80)
_CYAN = (255, 220, 0)
_MAGENTA = (255, 0, 255)
_YELLOW = (0, 230, 255)
_RED = (60, 60, 255)
_WHITE = (255, 255, 255)


def _poly(img: np.ndarray, pts: np.ndarray, color, thickness: int = 1, closed: bool = True, scale: float = 1.0) -> None:
    if len(pts) < 2:
        return
    p = np.round(pts * scale * 16).astype(np.int32).reshape(-1, 1, 2)
    cv2.polylines(img, [p], closed, color, thickness, cv2.LINE_AA, shift=4)


def draw_board(img: np.ndarray, cam: CameraModel, board: BoardGeometry, scale: float = 1.0,
               sectors: bool = True, labels: bool = True) -> None:
    for name, r in board.ring_radii.items():
        pts3 = board.circle_points(r, 180)
        ok = cam.in_front(pts3)
        _poly(img, cam.project(pts3[ok]), _GREEN if "double" in name or "triple" in name else _CYAN, 1, True, scale)
    if sectors:
        r0, r1 = board.ring_radii["outer_bull"], board.ring_radii["double_outer"]
        for a in board.sector_boundary_angles():
            t = math.radians(a)
            seg = np.array([[r * math.sin(t), r * math.cos(t), 0.0] for r in np.linspace(r0, r1, 12)])
            _poly(img, cam.project(seg), _CYAN, 1, False, scale)
    c = cam.project(np.zeros((1, 3)))[0] * scale
    cv2.drawMarker(img, (int(c[0]), int(c[1])), _RED, cv2.MARKER_CROSS, 14, 1, cv2.LINE_AA)
    if labels:
        r = (board.ring_radii["double_outer"] + board.config.board_radius_mm) / 2
        for i, s in enumerate(board.sector_order):
            x, y = board.from_polar(r, i * board.sector_angle_deg)
            p = cam.project(np.array([[x, y, 0.0]]))[0] * scale
            cv2.putText(img, str(s), (int(p[0]) - 7, int(p[1]) + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.45, _YELLOW, 1,
                        cv2.LINE_AA)


def draw_debug(
    img: np.ndarray,
    cam: CameraModel | None,
    board: BoardGeometry,
    layers: set[str],
    roi: np.ndarray | None = None,
    change=None,
    candidates=None,
    darts: list[dict] | None = None,
    info: list[str] | None = None,
    scale: float = 1.0,
) -> np.ndarray:
    """Return a copy of ``img`` (already resized by ``scale``) with the requested layers."""
    out = img.copy()
    h, w = out.shape[:2]
    if "roi" in layers and roi is not None:
        r = cv2.resize(roi, (w, h), interpolation=cv2.INTER_NEAREST)
        contours, _ = cv2.findContours(r, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(out, contours, -1, (180, 180, 180), 1, cv2.LINE_AA)
    if "change" in layers and change is not None:
        full = np.zeros((int(round(h / scale)), int(round(w / scale))), np.uint8)
        x0, y0, x1, y1 = change.bbox
        full[y0:y1, x0:x1] = change.added
        m = cv2.resize(full, (w, h), interpolation=cv2.INTER_NEAREST) > 0
        tint = out.copy()
        tint[m] = (0, 230, 255)
        out = cv2.addWeighted(out, 0.55, tint, 0.45, 0)
    if cam is not None and ("board" in layers or "sectors" in layers):
        draw_board(out, cam, board, scale, sectors="sectors" in layers, labels="labels" in layers)
    if "candidates" in layers and candidates:
        for i, c in enumerate(candidates):
            p0 = c.tip_px * scale
            p1 = c.tail_px * scale
            cv2.line(out, (int(p0[0]), int(p0[1])), (int(p1[0]), int(p1[1])), _MAGENTA, 1, cv2.LINE_AA)
            cv2.circle(out, (int(p0[0]), int(p0[1])), 5, _RED if c.tip_visible else (0, 140, 255), 1, cv2.LINE_AA)
            cv2.putText(out, f"#{i} {c.confidence:.2f}", (int(p0[0]) + 6, int(p0[1]) - 6), cv2.FONT_HERSHEY_SIMPLEX,
                        0.45, _MAGENTA, 1, cv2.LINE_AA)
    if "darts" in layers and darts and cam is not None:
        for d in darts:
            imp = np.array([[d["x_mm"], d["y_mm"], 0.0]])
            p = cam.project(imp)[0] * scale
            color = _YELLOW if d.get("uncertain") else _GREEN
            cv2.circle(out, (int(p[0]), int(p[1])), 7, color, 2, cv2.LINE_AA)
            if d.get("axis") is not None:
                a = np.asarray(d["axis"], float)
                seg = imp + np.linspace(0, 140, 15)[:, None] * a[None, :]
                _poly(out, cam.project(seg), color, 1, False, scale)
            if "lines" in layers and d.get("board_lines"):
                for ln in d["board_lines"]:
                    n = np.asarray(ln["normal"], float)
                    p0 = n * ln["offset"]
                    dvec = np.array([-n[1], n[0]])
                    pts = np.array([[*(p0 + s * dvec), 0.0] for s in np.linspace(-60, 60, 30)])
                    _poly(out, cam.project(pts), (0, 140, 255), 1, False, scale)
            label = d.get("label", "")
            cv2.putText(out, label, (int(p[0]) + 9, int(p[1]) + 18), cv2.FONT_HERSHEY_DUPLEX, 0.6, color, 1,
                        cv2.LINE_AA)
    if "info" in layers and info:
        y = 20
        for line in info:
            cv2.putText(out, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3, cv2.LINE_AA)
            cv2.putText(out, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, _WHITE, 1, cv2.LINE_AA)
            y += 20
    return out


def undistort_image(img: np.ndarray, cam: CameraModel) -> np.ndarray:
    return cv2.undistort(img, cam.K, cam.dist)


def topdown_view(img: np.ndarray, cam: CameraModel, board: BoardGeometry, size: int = 600,
                 extent_mm: float = 240.0) -> np.ndarray:
    """Rectify the camera image onto the board plane (useful to judge calibration and to
    annotate ground truth). Strongly oblique cameras give a smeared far side."""
    s = size / (2 * extent_mm)
    # top-down pixel (u, v) -> board (x, y)
    T = np.array([[1 / s, 0, -extent_mm], [0, -1 / s, extent_mm], [0, 0, 1.0]])
    H = cam.homography() @ T
    und = cv2.undistort(img, cam.K, cam.dist)
    return cv2.warpPerspective(und, H, (size, size), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP)
