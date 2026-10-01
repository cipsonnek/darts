"""Automatic dartboard detection from the coloured double/triple rings.

1. Segment red and green pixels (HSV).
2. The double ring is the largest red/green structure; its outer contour is the image of
   a circle (an ellipse), fitted robustly.
3. Walk along the ring's centre line and read the sequence of red/green segments. Each
   colour change is a sector wire: 20 points at *known* board angles, up to the cyclic
   assignment.
4. The assignment has two discrete ambiguities: traversal direction (resolved by the
   orientation of the plane-to-image mapping) and a rotation by multiples of 36° (the
   colour pattern repeats every two sectors). The rotation is resolved by the camera's
   configured mounting position, or by a single user click inside the 20.
5. With the resulting homography, the triple ring and bull are sampled exactly to add
   correspondences, and a PnP pose is computed. Edge refinement (calibration/refine.py)
   then makes it sub-pixel accurate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import cv2
import numpy as np

from vision.config import BoardDetectionConfig
from vision.geometry.board import BoardGeometry
from vision.geometry.camera_model import CameraModel

RED, GREEN = 1, 2


@dataclass
class RotationCandidate:
    offset: int  # board boundary index of the first detected transition
    direction: int  # +1: increasing ellipse parameter = clockwise on the board
    homography: np.ndarray  # board (x, y) → undistorted pixel
    camera: CameraModel | None
    reprojection_rms_px: float
    azimuth_deg: float | None  # camera position around the board (clock angle)


@dataclass
class BoardDetection:
    ok: bool
    reason: str | None = None
    ellipse: tuple | None = None
    transitions_px: np.ndarray | None = None  # (20, 2) distorted pixels
    candidates: list[RotationCandidate] = field(default_factory=list)
    chosen: RotationCandidate | None = None
    ambiguous: bool = False
    correspondences: list[tuple[tuple[float, float, float], tuple[float, float]]] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "ok": self.ok,
            "reason": self.reason,
            "ambiguous": self.ambiguous,
            "n_transitions": 0 if self.transitions_px is None else int(len(self.transitions_px)),
            "n_correspondences": len(self.correspondences),
            "candidates": [
                {"offset": c.offset, "direction": c.direction, "rms_px": round(c.reprojection_rms_px, 3),
                 "azimuth_deg": None if c.azimuth_deg is None else round(c.azimuth_deg, 1)}
                for c in self.candidates
            ],
        }


def segment_ring_colors(image_bgr: np.ndarray, cfg: BoardDetectionConfig) -> tuple[np.ndarray, np.ndarray]:
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    sat = (s >= cfg.min_saturation) & (v >= cfg.min_value)
    red = sat & ((h <= cfg.red_hue_low_max) | (h >= cfg.red_hue_high_min))
    green = sat & (h >= cfg.green_hue_min) & (h <= cfg.green_hue_max)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    red = cv2.morphologyEx(red.astype(np.uint8) * 255, cv2.MORPH_OPEN, k)
    green = cv2.morphologyEx(green.astype(np.uint8) * 255, cv2.MORPH_OPEN, k)
    return red, green


def _fit_outer_ellipse(ring_mask: np.ndarray, min_area: float) -> tuple | None:
    res = _fit_outer_ellipse_pts(ring_mask, min_area)
    return None if res is None else res[0]


def _fit_outer_ellipse_pts(ring_mask: np.ndarray, min_area: float) -> tuple[tuple, np.ndarray] | None:
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    closed = cv2.morphologyEx(ring_mask, cv2.MORPH_CLOSE, k)
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    # The thin far side of the double ring often breaks into pieces, so do not rely on a
    # single component: nothing red/green lies outside the double ring, so the outermost
    # coloured contour point in every direction belongs to its outer edge.
    contours = [c for c in contours if cv2.contourArea(c) >= 12]
    if not contours or sum(cv2.contourArea(c) for c in contours) < min_area:
        return None
    pts = np.concatenate([c.reshape(-1, 2) for c in contours]).astype(np.float64)
    # If the band has a gap the external contour also runs along the inner edge; keep only
    # the outermost point in each angular bin around the centre.
    c = pts.mean(axis=0)
    d = pts - c
    ang = np.arctan2(d[:, 1], d[:, 0])
    rad = np.hypot(d[:, 0], d[:, 1])
    bins = ((ang + np.pi) / (2 * np.pi) * 720).astype(int) % 720
    order = np.lexsort((-rad, bins))
    first = np.ones(len(order), dtype=bool)
    first[1:] = bins[order][1:] != bins[order][:-1]
    pts = pts[order[first]]
    if len(pts) < 20:
        return None
    ellipse = cv2.fitEllipse(pts.astype(np.float32))
    keep = np.ones(len(pts), dtype=bool)
    for _ in range(3):
        rho = _ellipse_radius(pts, ellipse)
        k2 = np.abs(rho - 1.0) < 0.02
        if k2.sum() < 20:
            break
        keep = k2
        ellipse = cv2.fitEllipse(pts[keep].astype(np.float32))
    return ellipse, pts[keep]


def _ellipse_radius(pts: np.ndarray, ellipse: tuple) -> np.ndarray:
    (cx, cy), (w, h), angle = ellipse
    a, b = w / 2.0, h / 2.0
    t = math.radians(angle)
    c, s = math.cos(t), math.sin(t)
    dx, dy = pts[:, 0] - cx, pts[:, 1] - cy
    u = dx * c + dy * s
    v = -dx * s + dy * c
    return np.sqrt((u / a) ** 2 + (v / b) ** 2)


def _ellipse_points(ellipse: tuple, params: np.ndarray, scale: float = 1.0) -> np.ndarray:
    (cx, cy), (w, h), angle = ellipse
    a, b = w / 2.0 * scale, h / 2.0 * scale
    t = math.radians(angle)
    c, s = math.cos(t), math.sin(t)
    x = a * np.cos(params)
    y = b * np.sin(params)
    return np.stack([cx + x * c - y * s, cy + x * s + y * c], axis=1)


def _labels_at(red: np.ndarray, green: np.ndarray, pts: np.ndarray) -> np.ndarray:
    h, w = red.shape
    xi = np.clip(np.round(pts[:, 0]).astype(int), 0, w - 1)
    yi = np.clip(np.round(pts[:, 1]).astype(int), 0, h - 1)
    lab = np.zeros(len(pts), dtype=np.int8)
    lab[red[yi, xi] > 0] = RED
    lab[green[yi, xi] > 0] = GREEN
    inside = (pts[:, 0] >= 0) & (pts[:, 0] < w) & (pts[:, 1] >= 0) & (pts[:, 1] < h)
    lab[~inside] = -1
    return lab


def _transitions(labels: np.ndarray, min_run: int) -> list[tuple[float, int]]:
    """Cyclic colour changes. Returns [(position index (float), colour before)] in order of
    increasing index. Short runs and unlabelled gaps (wires, glare) are bridged."""
    n = len(labels)
    runs: list[list[int]] = []  # [label, start, end] (inclusive, may wrap past n)
    i = 0
    while i < n:
        lab = labels[i]
        j = i
        while j + 1 < n and labels[j + 1] == lab:
            j += 1
        runs.append([int(lab), i, j])
        i = j + 1
    if len(runs) > 1 and runs[0][0] == runs[-1][0]:
        runs[0][1] = runs[-1][1] - n
        runs.pop()
    colour_runs = [r for r in runs if r[0] in (RED, GREEN) and (r[2] - r[1] + 1) >= min_run]
    merged: list[list[int]] = []
    for r in colour_runs:
        if merged and merged[-1][0] == r[0]:
            merged[-1][2] = r[2]
        else:
            merged.append(list(r))
    if len(merged) > 1 and merged[0][0] == merged[-1][0]:
        merged[0][1] = merged[-1][1] - n
        merged.pop()
    out = []
    for k in range(len(merged)):
        a = merged[k]
        b = merged[(k + 1) % len(merged)]
        b_start = b[1] if b[1] > a[2] else b[1] + n
        out.append((((a[2] + b_start) / 2.0) % n, a[0]))
    out.sort(key=lambda x: x[0])
    return out


class BoardDetector:
    def __init__(self, board: BoardGeometry, config: BoardDetectionConfig | None = None) -> None:
        self.board = board
        self.cfg = config or BoardDetectionConfig()

    def detect(self, image_bgr: np.ndarray, K: np.ndarray, dist: np.ndarray,
               azimuth_prior_deg: float | None = None, hint_px: tuple[float, float] | None = None,
               camera_id: str = "") -> BoardDetection:
        h, w = image_bgr.shape[:2]
        red, green = segment_ring_colors(image_bgr, self.cfg)
        ring = cv2.bitwise_or(red, green)
        fit = _fit_outer_ellipse_pts(ring, self.cfg.min_ring_area_fraction * w * h)
        ellipse, self._edge_pts = (None, None) if fit is None else fit
        if ellipse is None:
            return BoardDetection(False, "no red/green double ring found — is the whole board visible and lit?")
        rr = self.board.ring_radii
        mid_scale = ((rr["double_inner"] + rr["double_outer"]) / 2) / rr["double_outer"]
        n_samples = 2880
        params = np.linspace(0, 2 * np.pi, n_samples, endpoint=False)
        pts = _ellipse_points(ellipse, params, mid_scale)
        # The far side of the band can be only 2-3 px thick: vote across the band.
        inner_scale = rr["double_inner"] / rr["double_outer"]
        votes = np.stack([_labels_at(red, green, _ellipse_points(ellipse, params, s))
                          for s in np.linspace(inner_scale - 0.01, 0.995, 9)])
        n_red = (votes == RED).sum(0)
        n_green = (votes == GREEN).sum(0)
        labels = np.where(n_red > n_green, RED, np.where(n_green > n_red, GREEN, 0)).astype(np.int8)
        labels[(votes == -1).any(0)] = -1
        if (labels == -1).mean() > 0.02:
            return BoardDetection(False, "the double ring is partly outside the image", ellipse)
        trans = _transitions(labels, min_run=max(3, n_samples // 400))
        n = self.board.n_sectors
        if len(trans) < 6:
            return BoardDetection(False, f"found only {len(trans)} colour transitions on the double ring "
                                  "(remove darts and obstructions, check lighting)", ellipse)
        tparams = np.array([p for p, _ in trans]) * (2 * np.pi / n_samples)
        trans_px = _ellipse_points(ellipse, tparams, mid_scale)
        colours = [c for _, c in trans]

        und = _undistort(trans_px, K, dist)
        r_mid = (rr["double_inner"] + rr["double_outer"]) / 2
        angles = self.board.sector_boundary_angles()
        first_red = self.board.config.first_sector_ring_color == "red"
        candidates: list[RotationCandidate] = []
        if len(trans) != n:
            # Thin far-side segments can vanish entirely. Assign the transitions that were
            # found through a metric pose of the double-ring circle instead of by count.
            candidates = self._candidates_from_circle_pose(
                red, green, ellipse, trans_px, K, dist, (w, h), camera_id)
            if not candidates:
                return BoardDetection(False, f"found {len(trans)} of {n} colour transitions and could not "
                                      "assign them (remove darts and obstructions, check lighting)", ellipse)
        for direction in ((1, -1) if len(trans) == n else ()):
            for offset in range(n):
                # Colour before boundary j (moving clockwise) is that of sector j-1;
                # moving anticlockwise it is that of sector j.
                ok = True
                for k, colour in enumerate(colours):
                    j = (offset + direction * k) % n
                    sector = (j - 1) % n if direction == 1 else j
                    expected_red = (sector % 2 == 0) == first_red
                    if (colour == RED) != expected_red:
                        ok = False
                        break
                if not ok:
                    continue
                board_pts = np.array([self.board.from_polar(r_mid, angles[(offset + direction * k) % n])
                                      for k in range(n)])
                H, _ = cv2.findHomography(board_pts, und, 0)
                if H is None or not _orientation_ok(H):
                    continue
                cam, rms = _pnp(board_pts, trans_px, K, dist, (w, h), camera_id)
                az = None
                if cam is not None:
                    c = cam.center
                    az = math.degrees(math.atan2(c[0], c[1])) % 360.0
                candidates.append(RotationCandidate(offset, direction, H, cam, rms, az))
        candidates = [c for c in candidates if c.camera is not None and c.camera.center[2] > 0]
        if not candidates:
            return BoardDetection(False, "could not find a consistent sector assignment", ellipse, trans_px)
        det = BoardDetection(True, None, ellipse, trans_px, candidates)
        det.chosen, det.ambiguous = self._choose(candidates, azimuth_prior_deg, hint_px, K, dist)
        if det.chosen is None:
            det.ok = False
            det.reason = ("board found, but its rotation is ambiguous: set the camera's mounting position "
                          "(clock angle) or click once inside the 20 segment")
            return det
        det.correspondences = self._collect(image_bgr, red, green, det.chosen, K, dist)
        bxy = np.array([c[0] for c in det.correspondences])[:, :2]
        cpx = np.array([c[1] for c in det.correspondences])
        cam, rms = _pnp(bxy, cpx, K, dist, (w, h), camera_id)
        H_all, _ = cv2.findHomography(bxy, _undistort(cpx, K, dist), 0)
        if cam is None or H_all is None or _homography_rms(H_all, bxy, _undistort(cpx, K, dist)) > self.cfg.max_pnp_rms_px:
            det.ok = False
            det.reason = f"pose estimate failed (reprojection {rms:.1f}px)"
            return det
        det.chosen.camera = cam
        det.chosen.reprojection_rms_px = rms
        return det

    def _candidates_from_circle_pose(self, red, green, ellipse, trans_px, K, dist, size, camera_id
                                     ) -> list[RotationCandidate]:
        rr = self.board.ring_radii
        r_mid = (rr["double_inner"] + rr["double_outer"]) / 2
        n = self.board.n_sectors
        step = self.board.sector_angle_deg
        first_red = self.board.config.first_sector_ring_color == "red"
        self.trace: list[str] = []
        best: tuple[int, float, CameraModel, np.ndarray, np.ndarray] | None = None
        for cam in fit_circle_poses(self._edge_pts, ellipse, K, dist, rr["double_outer"], size, camera_id):
            xy, valid = cam.pixels_to_board(trans_px)
            if not valid.all():
                continue
            theta = np.degrees(np.arctan2(xy[:, 0], xy[:, 1])) % 360.0
            order = np.argsort(theta)
            gaps = np.diff(np.append(theta[order], theta[order][0] + 360.0)) / step
            steps_k = np.round(gaps)
            worst = float(np.max(np.abs(gaps - steps_k)))
            idx = np.zeros(len(theta), dtype=int)
            use = np.zeros(len(theta), dtype=bool)
            if np.all(steps_k >= 1) and int(steps_k.sum()) == n and worst <= 0.45:
                # Every wire indexed from the gap to its neighbour.
                idx[order] = np.concatenate([[0], np.cumsum(steps_k[:-1])]).astype(int)
                use[:] = True
            else:
                # Robust alternative: the longest chain of consecutive wires 18° apart
                # (the dense near side); the far side is recovered later by re-sampling.
                ok = np.abs(gaps - 1.0) < 0.35  # gap from order[k] to order[k+1]
                best_len, best_start = 0, 0
                m = len(theta)
                for start in range(m):
                    length = 0
                    while length < m - 1 and ok[(start + length) % m]:
                        length += 1
                    if length > best_len:
                        best_len, best_start = length, start
                chain = [order[(best_start + k) % m] for k in range(best_len + 1)]
                if len(chain) < 6:
                    self.trace.append(f"pose hypothesis rejected: wire spacing inconsistent (worst {worst:.2f}, "
                                      f"longest regular chain {len(chain)})")
                    continue
                for k, i in enumerate(chain):
                    idx[i] = k
                    use[i] = True
            score = int(use.sum())
            if best is None or score > best[0] or (score == best[0] and worst < best[1]):
                best = (score, worst, cam, idx, use)
        if best is None:
            self.trace.append("no pose hypothesis with regular 18° wire spacing")
            return []
        _, _, cam, jrel, use = best
        trans_px = trans_px[use]
        jrel = jrel[use]
        # jrel: index of each detected wire relative to an unknown rotation (k·18°).
        cands: list[RotationCandidate] = []
        # Colour of the sector anticlockwise of each wire (smaller θ), read in the fitted frame.
        xy_t, _ = cam.pixels_to_board(trans_px)
        th_abs = np.degrees(np.arctan2(xy_t[:, 0], xy_t[:, 1])) % 360.0
        before = np.array([cam.project(np.array([[*self.board.from_polar(r_mid, t - step / 3), 0.0]]))[0]
                           for t in th_abs])
        lab_before = _labels_at(red, green, before)
        angles = self.board.sector_boundary_angles()
        w, h = size
        for m in range(n):
            score = 0
            total = 0
            for k, j in enumerate(jrel):
                if lab_before[k] not in (RED, GREEN):
                    continue
                total += 1
                sector = (j + m - 1) % n
                expected_red = (sector % 2 == 0) == first_red
                score += int((lab_before[k] == RED) == expected_red)
            if total == 0 or score < 0.85 * total:
                self.trace.append(f"rotation {m}: colour parity {score}/{total}")
                continue
            board_pts = np.array([self.board.from_polar(r_mid, angles[(j + m) % n]) for j in jrel])
            und = _undistort(trans_px, K, dist)
            # Far-side transitions on a 1-2 px band are imprecise: fit robustly.
            H, inl = cv2.findHomography(board_pts, und, cv2.RANSAC, 3.0)
            if H is None or not _orientation_ok(H):
                self.trace.append(f"rotation {m}: mirrored or no homography")
                continue
            inl = inl.ravel().astype(bool)
            if inl.sum() < max(8, len(jrel) // 2):
                self.trace.append(f"rotation {m}: only {int(inl.sum())} homography inliers")
                continue
            board_pts, und, trans_used = board_pts[inl], und[inl], trans_px[inl]
            # Gate on the homography fit: with approximate intrinsics the PnP residual also
            # contains the focal-length error, which edge refinement corrects later.
            h_rms = _homography_rms(H, board_pts, und)
            if h_rms > self.cfg.max_pnp_rms_px:
                self.trace.append(f"rotation {m}: homography residual {h_rms:.1f}px")
                continue
            c2, rms = _pnp(board_pts, trans_used, K, dist, (w, h), camera_id)
            if c2 is None:
                continue
            cc = c2.center
            cands.append(RotationCandidate(m, 0, H, c2, rms, math.degrees(math.atan2(cc[0], cc[1])) % 360.0))
        return cands

    def _choose(self, cands: list[RotationCandidate], prior: float | None, hint_px, K, dist
                ) -> tuple[RotationCandidate | None, bool]:
        if hint_px is not None:
            und = _undistort(np.array([hint_px], float), K, dist)[0]
            best, best_d = None, 1e9
            for c in cands:
                p = np.linalg.inv(c.homography) @ np.array([und[0], und[1], 1.0])
                x, y = p[0] / p[2], p[1] / p[2]
                theta = math.degrees(math.atan2(x, y)) % 360.0
                d = min(theta, 360 - theta)
                if d < best_d:
                    best, best_d = c, d
            return (best if best_d < self.board.sector_angle_deg else None), False
        if prior is not None:
            def gap(c: RotationCandidate) -> float:
                d = abs(((c.azimuth_deg or 0) - prior + 180) % 360 - 180)
                return d
            ranked = sorted(cands, key=gap)
            # Candidates are 36° apart; the prior must be closer than half of that.
            ok = gap(ranked[0]) < 18.0
            return (ranked[0] if ok else None), not ok
        return None, True

    def _collect(self, image, red, green, cand: RotationCandidate, K, dist
                 ) -> list[tuple[tuple[float, float, float], tuple[float, float]]]:
        """Re-sample double and triple ring centre circles exactly through the homography
        and collect sector-wire correspondences, plus the bull centre."""
        rr = self.board.ring_radii
        H = cand.homography
        out: list[tuple[tuple[float, float, float], tuple[float, float]]] = []
        angles = np.array(self.board.sector_boundary_angles())
        for r in ((rr["double_inner"] + rr["double_outer"]) / 2, (rr["triple_inner"] + rr["triple_outer"]) / 2):
            thetas = np.linspace(0, 360, 2880, endpoint=False)
            bpts = np.array([self.board.from_polar(r, t) for t in thetas])
            und = cv2.perspectiveTransform(bpts.reshape(-1, 1, 2), H).reshape(-1, 2)
            px = _distort(und, K, dist)
            labels = _labels_at(red, green, px)
            for pos, _ in _transitions(labels, min_run=4):
                theta = float(np.interp(pos, np.arange(len(thetas)), thetas))
                diff = (angles - theta + 180) % 360 - 180
                j = int(np.argmin(np.abs(diff)))
                if abs(diff[j]) > 3.0:
                    continue
                k = int(pos)
                f = pos - k
                p = px[k % len(px)] * (1 - f) + px[(k + 1) % len(px)] * f
                bx, by = self.board.from_polar(r, angles[j])
                out.append(((bx, by, 0.0), (float(p[0]), float(p[1]))))
        # Bull centre: centroid of the red inner bull blob near the predicted centre.
        c_und = cv2.perspectiveTransform(np.array([[[0.0, 0.0]]]), H).reshape(2)
        c_px = _distort(c_und.reshape(1, 2), K, dist)[0]
        n_lbl, lbl, stats, cents = cv2.connectedComponentsWithStats(red)
        best, best_d = None, 1e9
        for i in range(1, n_lbl):
            d = float(np.hypot(*(cents[i] - c_px)))
            if d < best_d and stats[i, cv2.CC_STAT_AREA] >= 6:
                best, best_d = i, d
        if best is not None and best_d < 12:
            out.append(((0.0, 0.0, 0.0), (float(cents[best][0]), float(cents[best][1]))))
        return out


def _homography_rms(H: np.ndarray, board_xy: np.ndarray, und_px: np.ndarray) -> float:
    pred = cv2.perspectiveTransform(board_xy.reshape(-1, 1, 2).astype(np.float64), H).reshape(-1, 2)
    return float(np.sqrt(np.mean(np.sum((pred - und_px) ** 2, axis=1))))


def _orientation_ok(H: np.ndarray) -> bool:
    """A camera in front of the board sees board +X/+Y (right/up) as image right/up, i.e.
    the board→image map reverses orientation (image y points down): det(J) < 0."""
    def f(x, y):
        p = H @ np.array([x, y, 1.0])
        return p[:2] / p[2]
    p0, px, py = f(0, 0), f(1, 0), f(0, 1)
    J = np.column_stack([px - p0, py - p0])
    return float(np.linalg.det(J)) < 0


def _undistort(px: np.ndarray, K: np.ndarray, dist: np.ndarray) -> np.ndarray:
    pts = cv2.undistortPoints(px.reshape(-1, 1, 2).astype(np.float64), K, dist, P=K)
    return pts.reshape(-1, 2)


def _distort(und_px: np.ndarray, K: np.ndarray, dist: np.ndarray) -> np.ndarray:
    n = (und_px - K[:2, 2]) / np.array([K[0, 0], K[1, 1]])
    pts = np.concatenate([n, np.ones((len(n), 1))], axis=1).reshape(-1, 1, 3)
    out, _ = cv2.projectPoints(pts, np.zeros(3), np.zeros(3), K, dist)
    return out.reshape(-1, 2)


def _pnp(board_xy: np.ndarray, px: np.ndarray, K: np.ndarray, dist: np.ndarray, size, camera_id
         ) -> tuple[CameraModel | None, float]:
    obj = np.concatenate([board_xy, np.zeros((len(board_xy), 1))], axis=1).astype(np.float64)
    img = px.astype(np.float64).reshape(-1, 1, 2)
    if len(obj) < 4:
        return None, float("inf")
    ok, rvec, tvec = cv2.solvePnP(obj, img, K, dist, flags=cv2.SOLVEPNP_IPPE)
    if not ok:
        return None, float("inf")
    rvec, tvec = cv2.solvePnPRefineLM(obj, img, K, dist, rvec, tvec)
    cam = CameraModel.from_rvec(K, dist, rvec, tvec, size, camera_id)
    rms = float(np.sqrt(np.mean(np.sum((cam.project(obj) - px) ** 2, axis=1))))
    return cam, rms


def fit_circle_poses(edge_px: np.ndarray, ellipse: tuple, K: np.ndarray, dist: np.ndarray,
                     radius_mm: float, size, camera_id: str = "") -> list[CameraModel]:
    """Metric pose of a circle of known radius from points on its image. The rotation about
    the circle's axis is not observable and is left arbitrary. Parametrised with 5 degrees
    of freedom (plane normal as two angles, 3D centre) so the problem is well posed; both
    tilt hypotheses are refined and returned (those with the camera in front)."""
    from scipy.optimize import least_squares

    rays = cv2.undistortPoints(edge_px.reshape(-1, 1, 2).astype(np.float64), K, dist).reshape(-1, 2)
    rays = np.concatenate([rays, np.ones((len(rays), 1))], axis=1)
    (cx, cy), (ew, eh), ang = ellipse
    a, b = max(ew, eh) / 2.0, min(ew, eh) / 2.0
    major = math.radians(ang if ew >= eh else ang + 90.0)
    f = float(K[0, 0])
    c_n = cv2.undistortPoints(np.array([[[cx, cy]]], np.float64), K, dist).reshape(2)
    r0 = np.array([c_n[0], c_n[1], 1.0])
    r0 /= np.linalg.norm(r0)
    d0 = f * radius_mm / a
    u = np.array([math.cos(major), math.sin(major), 0.0])
    u -= (u @ r0) * r0
    u /= np.linalg.norm(u)
    tilt = math.acos(min(1.0, b / a))

    def normal(p: np.ndarray) -> np.ndarray:
        th, ph = p[0], p[1]
        return np.array([math.sin(th) * math.cos(ph), math.sin(th) * math.sin(ph), -math.cos(th)])

    def resid(p: np.ndarray) -> np.ndarray:
        n = normal(p)
        c = p[2:5]
        den = rays @ n
        s = (n @ c) / np.where(np.abs(den) < 1e-9, 1e-9, den)
        X = rays * s[:, None]
        r = np.linalg.norm(X - c, axis=1)
        out = (r - radius_mm) * f / np.maximum(np.abs(s), 1.0)
        # Intersections behind the camera are impossible.
        return np.where(s > 1.0, out, 1e3)

    out = []
    for sgn in (1.0, -1.0):
        n0 = _rot(-r0, u, sgn * tilt)
        th0 = math.acos(max(-1.0, min(1.0, -n0[2])))
        ph0 = math.atan2(n0[1], n0[0])
        # Stage 1: centre only (normal fixed) — keeps each hypothesis in its own branch of
        # the two-fold circle-pose ambiguity. Stage 2: all five parameters.
        c_res = least_squares(lambda c: resid(np.array([th0, ph0, *c])), d0 * r0, loss="huber",
                              f_scale=1.5, max_nfev=200)
        p0 = np.array([th0, ph0, *c_res.x])
        res = least_squares(resid, p0, loss="huber", f_scale=1.5, max_nfev=300)
        n = normal(res.x)
        c = res.x[2:5]
        if n @ c > 0:  # orient the normal towards the camera
            n = -n
        z = n
        x = np.cross(np.array([0.0, 1.0, 0.0]), z)
        if np.linalg.norm(x) < 1e-6:
            x = np.cross(np.array([1.0, 0.0, 0.0]), z)
        x /= np.linalg.norm(x)
        y = np.cross(z, x)
        Rm = np.column_stack([x, y, z])
        rvec, _ = cv2.Rodrigues(Rm)
        cam = CameraModel.from_rvec(K, dist, rvec, c, size, camera_id)
        if cam.center[2] > 0:
            out.append(cam)
    return out


def _rot(v: np.ndarray, axis: np.ndarray, angle: float) -> np.ndarray:
    k = axis / np.linalg.norm(axis)
    return v * math.cos(angle) + np.cross(k, v) * math.sin(angle) + k * (k @ v) * (1 - math.cos(angle))
