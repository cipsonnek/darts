"""Edge-based refinement of the camera pose relative to the board.

The board model (every ring wire and sector wire) is projected into the image. For each
model sample we search along the projected wire normal for the colour boundary with the
*expected polarity* — e.g. the inner triple wire goes from single colour to ring colour,
the outer triple wire the other way round — so that neighbouring wires cannot be confused.
The pose (and optionally the focal length) is then solved by robust least squares on the
point-to-edge distances, and the correspondence search is repeated with a shrinking window
(an ICP-style "moving edges" scheme).

The quality metrics are actual measurements on the image: RMS edge residual, fraction of
model samples with a confirmed edge, and the statistical pose uncertainty propagated to
board millimetres.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

import cv2
import numpy as np
from scipy.optimize import least_squares

from vision.geometry.board import BoardGeometry
from vision.geometry.camera_model import CameraModel
from vision.imaging import linearize_u8

log = logging.getLogger("vision.calibration")

_SIDE_MM = 2.4  # where the colour on either side of a wire is evaluated
_N_CATEGORIES = 6


@dataclass
class EdgeMeasurement:
    pixels: np.ndarray  # (N,2) projected model samples
    normals: np.ndarray  # (N,2) unit image normals (towards the outer category)
    offsets: np.ndarray  # (N,) signed distance to the detected edge along the normal (px)
    strength: np.ndarray  # (N,) edge strength relative to expected contrast
    valid: np.ndarray  # (N,) bool: an edge with correct polarity was found
    visible: np.ndarray  # (N,) bool: sample projects inside the image


@dataclass
class RefineResult:
    camera: CameraModel
    edge_rms_px: float
    inlier_fraction: float
    n_visible: int
    n_inliers: int
    pose_sigma_mm: float
    iterations: int
    converged: bool
    focal_refined: bool
    initial_rms_px: float
    history: list[dict] = field(default_factory=list)

    def metrics(self) -> dict:
        return {
            "edge_rms_px": round(self.edge_rms_px, 3),
            "inlier_fraction": round(self.inlier_fraction, 3),
            "visible_samples": self.n_visible,
            "inlier_samples": self.n_inliers,
            "pose_sigma_mm": round(self.pose_sigma_mm, 3),
            "iterations": self.iterations,
            "converged": self.converged,
            "focal_refined": self.focal_refined,
            "initial_rms_px": round(self.initial_rms_px, 3),
        }


def to_linear(image_bgr: np.ndarray, blur_sigma: float = 0.6) -> np.ndarray:
    """Linear-light BGR scaled to [0, 100]; blur and edge profiles are linear here."""
    lin = linearize_u8(image_bgr)
    if blur_sigma > 0:
        lin = cv2.GaussianBlur(lin, (0, 0), blur_sigma)
    return lin


to_lab = to_linear  # backwards-compatible name used by callers


class EdgeAligner:
    def __init__(self, board: BoardGeometry, samples_per_mm: float = 0.5) -> None:
        self.board = board
        pts, normals = board.edge_model(samples_per_mm)
        cin = board.color_categories(pts[:, :2] - normals[:, :2] * _SIDE_MM)
        cout = board.color_categories(pts[:, :2] + normals[:, :2] * _SIDE_MM)
        keep = (cin != cout) & (cin != 5) & (cout != 5)
        self.points = pts[keep]
        self.normals3 = normals[keep]
        self.cat_in = cin[keep]
        self.cat_out = cout[keep]
        self.side_mm = _adjacent_width_mm(board, self.points)
        self._region_pts, self._region_cats = self._region_samples()

    def _region_samples(self) -> tuple[np.ndarray, np.ndarray]:
        b = self.board
        rr = b.ring_radii
        radii = [
            (rr["outer_bull"] + rr["triple_inner"]) / 2,
            (rr["triple_inner"] + rr["triple_outer"]) / 2,
            (rr["triple_outer"] + rr["double_inner"]) / 2,
            (rr["double_inner"] + rr["double_outer"]) / 2,
            rr["double_outer"] + 6.0,
        ]
        pts = []
        for r in radii:
            for i in range(b.n_sectors):
                for da in (-4.0, 0.0, 4.0):
                    pts.append(b.from_polar(r, i * b.sector_angle_deg + da))
        for r, n in ((rr["inner_bull"] * 0.4, 1), ((rr["inner_bull"] + rr["outer_bull"]) / 2, 12)):
            for k in range(n):
                pts.append(b.from_polar(r, k * 360.0 / n))
        pts_arr = np.array(pts)
        return np.concatenate([pts_arr, np.zeros((len(pts_arr), 1))], axis=1), b.color_categories(pts_arr)

    # ------------------------------------------------------------------ colours
    def category_colors(self, lab: np.ndarray, camera: CameraModel) -> np.ndarray:
        """Median observed Lab colour of every colour category (NaN when unseen)."""
        px = camera.project(self._region_pts)
        h, w = lab.shape[:2]
        inside = (px[:, 0] >= 1) & (px[:, 0] < w - 2) & (px[:, 1] >= 1) & (px[:, 1] < h - 2) \
            & camera.in_front(self._region_pts)
        out = np.full((_N_CATEGORIES, 3), np.nan, dtype=np.float32)
        if not inside.any():
            return out
        vals = cv2.remap(lab, px[inside, 0].astype(np.float32).reshape(-1, 1),
                         px[inside, 1].astype(np.float32).reshape(-1, 1), cv2.INTER_LINEAR).reshape(-1, 3)
        cats = self._region_cats[inside]
        for c in range(_N_CATEGORIES):
            sel = cats == c
            if sel.sum() >= 3:
                out[c] = np.median(vals[sel], axis=0)
        return out

    # ------------------------------------------------------------------ measurement
    def measure(self, lab: np.ndarray, camera: CameraModel, search_px: float,
                colors: np.ndarray | None = None, ignore_mask: np.ndarray | None = None) -> EdgeMeasurement:
        colors = self.category_colors(lab, camera) if colors is None else colors
        pts = self.points
        q = camera.project(pts)
        q2 = camera.project(pts + self.normals3 * 0.5)
        d = q2 - q
        # The image normal must be perpendicular to the *projected wire*: perspective does
        # not preserve right angles, so the projected 3D normal is oblique to the edge.
        tangent3 = np.cross(np.array([0.0, 0.0, 1.0]), self.normals3)
        qt = camera.project(pts + tangent3 * 0.5)
        t_img = qt - q
        t_img /= np.maximum(np.linalg.norm(t_img, axis=1), 1e-9)[:, None]
        n_img = np.stack([-t_img[:, 1], t_img[:, 0]], axis=1)
        n_img *= np.sign(np.einsum("ij,ij->i", n_img, d))[:, None]
        # Pixels per half millimetre across the wire, measured perpendicular to it.
        px_per_half_mm = np.abs(np.einsum("ij,ij->i", n_img, d))
        h, w = lab.shape[:2]
        px_per_mm = px_per_half_mm * 2
        wire_half_px = self.board.config.wire_width_mm / 2 * px_per_mm
        # The colour samples must stay inside the neighbouring regions: a baseline wider
        # than ~1/3 of a narrow ring (8 mm, a few px at grazing angles) biases the edge.
        band_px = self.side_mm * px_per_mm
        baseline = np.clip(np.minimum(wire_half_px + 0.8, 0.35 * band_px), 0.8, 4.0)
        margin = search_px + baseline + 2
        visible = (q[:, 0] > margin) & (q[:, 0] < w - margin) & (q[:, 1] > margin) & (q[:, 1] < h - margin) \
            & camera.in_front(pts) & (px_per_half_mm > 0.15)
        if ignore_mask is not None:
            qi = np.clip(np.round(q).astype(int), 0, [w - 1, h - 1])
            visible &= ignore_mask[qi[:, 1], qi[:, 0]] == 0
        expected = colors[self.cat_out] - colors[self.cat_in]
        exp_norm = np.linalg.norm(expected, axis=1)
        visible &= np.isfinite(exp_norm) & (exp_norm > 8.0)

        offsets = np.zeros(len(pts))
        strength = np.zeros(len(pts))
        valid = np.zeros(len(pts), dtype=bool)
        idx = np.nonzero(visible)[0]
        if len(idx) == 0:
            return EdgeMeasurement(q, n_img, offsets, strength, valid, visible)
        if search_px <= self.template_below_px:
            self._measure_template(lab, q, n_img, px_per_mm, band_px, colors, idx, search_px,
                                   offsets, strength, valid)
            return EdgeMeasurement(q, n_img, offsets, strength, valid, visible)
        steps = np.arange(-search_px, search_px + 1e-9, 0.5, dtype=np.float32)
        qn = q[idx].astype(np.float32)
        nn = n_img[idx].astype(np.float32)
        bl = baseline[idx].astype(np.float32)
        base = qn[:, None, :] + nn[:, None, :] * steps[None, :, None]
        out_pts = base + nn[:, None, :] * bl[:, None, None]
        in_pts = base - nn[:, None, :] * bl[:, None, None]
        c_out = cv2.remap(lab, out_pts[..., 0], out_pts[..., 1], cv2.INTER_LINEAR)
        c_in = cv2.remap(lab, in_pts[..., 0], in_pts[..., 1], cv2.INTER_LINEAR)
        e = (expected[idx] / exp_norm[idx, None]).astype(np.float32)
        score = np.einsum("nmc,nc->nm", c_out - c_in, e) / exp_norm[idx, None]
        best = np.argmax(score, axis=1)
        peak = score[np.arange(len(idx)), best]
        interior = (best > 0) & (best < len(steps) - 1)
        # Sub-pixel peak by parabola fit.
        b0 = np.clip(best - 1, 0, len(steps) - 1)
        b2 = np.clip(best + 1, 0, len(steps) - 1)
        y0 = score[np.arange(len(idx)), b0]
        y2 = score[np.arange(len(idx)), b2]
        denom = y0 - 2 * peak + y2
        frac = np.where(np.abs(denom) > 1e-9, 0.5 * (y0 - y2) / denom, 0.0)
        frac = np.clip(frac, -0.5, 0.5)
        offs = steps[best] + frac * 0.5
        ok = interior & (peak > 0.45)
        offsets[idx] = offs
        strength[idx] = peak
        valid[idx] = ok
        return EdgeMeasurement(q, n_img, offsets, strength, valid, visible)

    template_below_px = 4.0
    psf_sigma_px = 0.9
    chroma_psf_sigma_px = 0.9
    chroma_weight = 1.0

    def _measure_template(self, lab, q, n_img, px_per_mm, band_px, colors, idx, search_px,
                          offsets, strength, valid) -> None:
        """Sub-pixel edge location by matching an explicit blurred profile model
        (inside colour | wire | outside colour) along the normal. Unlike a two-sided
        colour difference, this is not biased by the bright wire between the regions."""
        step = 0.25
        wire_px = self.board.config.wire_width_mm * px_per_mm[idx]
        half = np.clip(wire_px / 2 + np.minimum(2.5, 0.45 * band_px[idx]), 1.25, 6.0)
        hmax = float(half.max())
        K = int(math.ceil(hmax / step))
        kk = np.arange(-K, K + 1)
        xk = kk * step
        t = np.arange(-search_px - K * step, search_px + K * step + 1e-9, step, dtype=np.float32)
        qn = q[idx].astype(np.float32)
        nn = n_img[idx].astype(np.float32)
        pts = qn[:, None, :] + nn[:, None, :] * t[None, :, None]
        O = cv2.remap(lab, pts[..., 0], pts[..., 1], cv2.INTER_LINEAR)  # (N, T, 3)
        W = (np.abs(xk)[None, :] <= half[:, None]).astype(np.float32)  # (N, Kn)
        c_in = colors[self.cat_in[idx]]
        c_out = colors[self.cat_out[idx]]
        # Wire colour: observed at the projected wire centres (the pose is already close
        # when this fine stage runs).
        centre = cv2.remap(lab, qn[:, 0].reshape(-1, 1), qn[:, 1].reshape(-1, 1), cv2.INTER_LINEAR).reshape(-1, 3)
        resolved = wire_px >= 2.0
        src = centre[resolved] if resolved.sum() >= 20 else centre
        c_wire = np.median(src, axis=0) if self.board.config.wire_width_mm > 0 else None
        from scipy.special import ndtr

        hw = (wire_px / 2)[:, None, None]
        # Per-channel blur: chroma is softer than luma (MJPEG 4:2:0 subsampling, Bayer
        # demosaicing), and it is down-weighted for the same reason.
        sig = np.array([self.psf_sigma_px, self.chroma_psf_sigma_px, self.chroma_psf_sigma_px],
                       dtype=np.float32)[None, None, :]
        f_lo = ndtr((xk[None, :, None] + hw) / sig)  # fraction past the inner wire edge
        f_hi = ndtr((xk[None, :, None] - hw) / sig)  # fraction past the outer wire edge
        T = c_in[:, None, :] * (1 - f_lo) + c_out[:, None, :] * f_hi
        if c_wire is not None:
            T = T + c_wire[None, None, :] * (f_lo - f_hi)
        cw = np.array([1.0, self.chroma_weight, self.chroma_weight], dtype=np.float32)
        T = (T * cw).astype(np.float32)
        O = O * cw
        c_in = c_in * cw
        c_out = c_out * cw
        TT = np.einsum("nk,nkc,nkc->n", W, T, T)
        contrast = np.einsum("nc,nc->n", c_out - c_in, c_out - c_in) * W.sum(1)
        n_off = int(round(search_px / step))
        costs = np.empty((len(idx), 2 * n_off + 1), dtype=np.float32)
        for j in range(2 * n_off + 1):
            Ow = O[:, j:j + 2 * K + 1, :]
            OT = np.einsum("nk,nkc,nkc->n", W, Ow, T)
            OO = np.einsum("nk,nkc,nkc->n", W, Ow, Ow)
            g = np.clip(OT / np.maximum(TT, 1e-9), 0.6, 1.6)
            costs[:, j] = (OO - 2 * g * OT + g * g * TT) / np.maximum(contrast, 1e-6)
        best = np.argmin(costs, axis=1)
        rows = np.arange(len(idx))
        cmin = costs[rows, best]
        interior = (best > 0) & (best < costs.shape[1] - 1)
        y0 = costs[rows, np.clip(best - 1, 0, costs.shape[1] - 1)]
        y2 = costs[rows, np.clip(best + 1, 0, costs.shape[1] - 1)]
        denom = y0 - 2 * cmin + y2
        frac = np.clip(np.where(np.abs(denom) > 1e-9, 0.5 * (y0 - y2) / denom, 0.0), -0.5, 0.5)
        offsets[idx] = (best - n_off + frac) * step
        strength[idx] = np.clip(1.0 - cmin, 0.0, 1.0) * 1.5
        valid[idx] = interior & (cmin < 0.35)

    # ------------------------------------------------------------------ refinement
    def refine(
        self,
        image_bgr: np.ndarray,
        camera: CameraModel,
        refine_focal: bool = False,
        refine_k1: bool = False,
        schedule: tuple[float, ...] = (14, 10, 7, 5, 4, 3, 2.5, 2, 2, 2, 2, 2, 2, 2),
        ignore_mask: np.ndarray | None = None,
        lab: np.ndarray | None = None,
    ) -> RefineResult:
        lab = to_lab(image_bgr) if lab is None else lab
        cam = camera
        history = []
        initial_rms = float("nan")
        converged = False
        it = 0
        for it, search in enumerate(schedule, start=1):
            colors = self.category_colors(lab, cam)
            m = self.measure(lab, cam, search, colors, ignore_mask)
            n_valid = int(m.valid.sum())
            if n_valid < 30:
                log.warning("edge refinement: too few edges", extra={"valid": n_valid, "iteration": it})
                break
            rms = float(np.sqrt(np.mean(m.offsets[m.valid] ** 2)))
            if it == 1:
                initial_rms = rms
            history.append({"iteration": it, "search_px": search, "valid": n_valid, "rms_px": rms})
            targets = m.pixels[m.valid] + m.normals[m.valid] * m.offsets[m.valid, None]
            new_cam = _solve(cam, self.points[m.valid], targets, m.normals[m.valid],
                             np.clip(m.strength[m.valid], 0.2, 1.5), refine_focal, refine_k1)
            shift = _max_shift_px(cam, new_cam, self.points[m.valid])
            cam = new_cam
            if search <= schedule[-1] and shift < 0.05:
                converged = True
                break
        # Final measurement with a tight window.
        colors = self.category_colors(lab, cam)
        final = self.measure(lab, cam, 2.5, colors, ignore_mask)
        vis = int(final.visible.sum())
        inl_mask = final.valid & (np.abs(final.offsets) <= 1.5)
        n_inl = int(inl_mask.sum())
        rms = float(np.sqrt(np.mean(final.offsets[final.valid] ** 2))) if final.valid.any() else float("inf")
        sigma_mm = pose_uncertainty_mm(cam, self.points[inl_mask], final.normals[inl_mask],
                                       max(rms, 0.1), refine_focal) if n_inl > 20 else float("inf")
        return RefineResult(camera=cam, edge_rms_px=rms, inlier_fraction=n_inl / max(vis, 1), n_visible=vis,
                            n_inliers=n_inl, pose_sigma_mm=sigma_mm, iterations=it, converged=converged,
                            focal_refined=refine_focal, initial_rms_px=initial_rms, history=history)


def _params(cam: CameraModel, refine_focal: bool, refine_k1: bool) -> np.ndarray:
    p = list(cam.rvec) + list(cam.t)
    if refine_focal:
        p.append(0.0)
    if refine_k1:
        p.append(float(cam.dist[0]) if len(cam.dist) else 0.0)
    return np.array(p, dtype=np.float64)


def _camera_from(base: CameraModel, p: np.ndarray, refine_focal: bool, refine_k1: bool) -> CameraModel:
    K = base.K.copy()
    dist = base.dist.copy() if len(base.dist) else np.zeros(5)
    i = 6
    if refine_focal:
        s = math.exp(p[i])
        K[0, 0] *= s
        K[1, 1] *= s
        i += 1
    if refine_k1:
        if len(dist) < 5:
            dist = np.concatenate([dist, np.zeros(5 - len(dist))])
        dist[0] = p[i]
    return CameraModel.from_rvec(K, dist, p[:3], p[3:6], base.image_size, base.camera_id)


def _solve(cam: CameraModel, pts: np.ndarray, targets: np.ndarray, normals: np.ndarray,
           weights: np.ndarray, refine_focal: bool, refine_k1: bool) -> CameraModel:
    p0 = _params(cam, refine_focal, refine_k1)
    sw = np.sqrt(weights)
    obj = pts.reshape(-1, 1, 3)

    def residuals(p: np.ndarray) -> np.ndarray:
        K = cam.K.copy()
        dist = cam.dist.copy() if len(cam.dist) else np.zeros(5)
        i = 6
        if refine_focal:
            s = math.exp(p[i])
            K[0, 0] *= s
            K[1, 1] *= s
            i += 1
        if refine_k1:
            if len(dist) < 5:
                dist = np.concatenate([dist, np.zeros(5 - len(dist))])
            dist[0] = p[i]
        proj, _ = cv2.projectPoints(obj, p[:3], p[3:6], K, dist)
        proj = proj.reshape(-1, 2)
        return sw * np.einsum("ij,ij->i", proj - targets, normals)

    res = least_squares(residuals, p0, loss="huber", f_scale=1.0, x_scale="jac", max_nfev=60,
                        method="trf")
    return _camera_from(cam, res.x, refine_focal, refine_k1)


def _max_shift_px(a: CameraModel, b: CameraModel, pts: np.ndarray) -> float:
    return float(np.max(np.linalg.norm(a.project(pts) - b.project(pts), axis=1)))


def pose_uncertainty_mm(cam: CameraModel, pts: np.ndarray, normals: np.ndarray, sigma_px: float,
                        include_focal: bool = False, n_draws: int = 200, seed: int = 0) -> float:
    """RMS board-plane error (mm) caused by the statistical uncertainty of the pose, for
    points on the playing area. The pose covariance is σ²(JᵀJ)⁻¹ of the edge residuals."""
    p0 = _params(cam, include_focal, False)
    obj = pts.reshape(-1, 1, 3)

    def proj_normal(p: np.ndarray) -> np.ndarray:
        K = cam.K.copy()
        if include_focal:
            s = math.exp(p[6])
            K[0, 0] *= s
            K[1, 1] *= s
        pr, _ = cv2.projectPoints(obj, p[:3], p[3:6], K, cam.dist)
        return np.einsum("ij,ij->i", pr.reshape(-1, 2), normals)

    eps = np.array([1e-5] * 3 + [1e-3] * 3 + ([1e-5] if include_focal else []))
    J = np.empty((len(pts), len(p0)))
    for k in range(len(p0)):
        dp = np.zeros_like(p0)
        dp[k] = eps[k]
        J[:, k] = (proj_normal(p0 + dp) - proj_normal(p0 - dp)) / (2 * eps[k])
    try:
        cov = sigma_px ** 2 * np.linalg.inv(J.T @ J)
    except np.linalg.LinAlgError:
        return float("inf")
    rng = np.random.default_rng(seed)
    draws = rng.multivariate_normal(p0, cov, size=n_draws)
    test = []
    for r in (20.0, 60.0, 103.0, 140.0, 166.0):
        for a in range(0, 360, 30):
            t = math.radians(a)
            test.append([r * math.sin(t), r * math.cos(t), 0.0])
    test_arr = np.array(test)
    pix = cam.project(test_arr)
    errs = []
    for p in draws:
        c = _camera_from(cam, p, include_focal, False)
        xy, valid = c.pixels_to_board(pix)
        errs.append(np.linalg.norm(xy[valid] - test_arr[valid, :2], axis=1))
    all_err = np.concatenate(errs)
    return float(np.sqrt(np.mean(all_err ** 2)))


def _adjacent_width_mm(board: BoardGeometry, pts: np.ndarray) -> np.ndarray:
    """Width (mm) of the narrower of the two regions that meet at each edge sample."""
    radii = np.array(sorted(board.ring_radii.values()))
    r = np.hypot(pts[:, 0], pts[:, 1])
    out = np.empty(len(pts))
    for i, ri in enumerate(r):
        k = int(np.argmin(np.abs(radii - ri)))
        if abs(radii[k] - ri) < 1e-6:  # ring wire
            inner = radii[k] - (radii[k - 1] if k > 0 else 0.0)
            outer = (radii[k + 1] - radii[k]) if k + 1 < len(radii) else 40.0
            out[i] = min(inner, outer)
        else:  # sector wire: arc width of a sector at this radius
            out[i] = ri * math.radians(board.sector_angle_deg)
    return out
