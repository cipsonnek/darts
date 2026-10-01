"""Dart candidates in one camera: from the *added* change mask to a dart axis line and a
tip estimate.

A dart seen from the side is a thin, straight structure (point, barrel, shaft) ending in a
wide flight. The scoring geometry only needs the **axis line** (very well determined from
the thin part) and, as a weaker cue, the **visible entry point** where the dart meets the
board. Steps:

1. Connected components of the added mask; collinear fragments (a dart partly hidden
   behind an existing dart) are merged.
2. RANSAC on *thin* pixels only (small distance-transform value) finds the axis without
   being pulled by the flight; up to two axes per group (crossing darts).
3. The axis is refined from per-slice centres of the thin part, in **undistorted**
   coordinates, because a straight dart is only straight after removing lens distortion.
4. The tip end is the end closer to the board along the projected board normal; the tip is
   localised to sub-pixel accuracy from the change profile along the axis.
5. Plausibility: projected length vs. the length a dart would have at that position,
   elongation, straightness.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import cv2
import numpy as np

from vision.config import DetectionConfig
from vision.geometry.camera_model import CameraModel
from vision.geometry.lines import Line2D, fit_line, ransac_line


@dataclass(eq=False)
class DartCandidate:
    camera_id: str
    tip_px: np.ndarray  # (2,) distorted pixel: visible entry point
    tail_px: np.ndarray  # (2,) distorted pixel: far end of the thin part along the axis
    axis_ideal: Line2D  # axis in ideal (undistorted) pixel coordinates
    line_rms_px: float
    n_slices: int
    length_px: float
    width_px: float
    tip_visible: bool
    confidence: float
    pixel_count: int
    mask_bbox: tuple[int, int, int, int]  # full-frame x0, y0, x1, y1
    mask: np.ndarray  # uint8 crop of the candidate's pixels
    factors: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "camera_id": self.camera_id,
            "tip_px": [round(float(v), 2) for v in self.tip_px],
            "tail_px": [round(float(v), 2) for v in self.tail_px],
            "line_rms_px": round(self.line_rms_px, 3),
            "length_px": round(self.length_px, 1),
            "width_px": round(self.width_px, 2),
            "tip_visible": self.tip_visible,
            "confidence": round(self.confidence, 3),
            "pixel_count": self.pixel_count,
            "factors": {k: round(v, 3) for k, v in self.factors.items()},
        }


def extract_candidates(
    added: np.ndarray,
    bbox: tuple[int, int, int, int],
    diff: np.ndarray,
    camera: CameraModel | None,
    cfg: DetectionConfig,
    camera_id: str = "",
    occluders: np.ndarray | None = None,
    roi: np.ndarray | None = None,
    dart_length_mm: float | None = None,
) -> list[DartCandidate]:
    """``added``/``diff`` are bbox-sized crops; ``occluders`` (bbox-sized) marks pixels of
    darts that were already in the board (they can hide the new dart's tip).

    Darts are extracted one at a time: the line with the longest *coverage* (number of
    distinct positions along it that contain changed pixels, allowing short occlusion
    gaps) is the best dart axis — a line through a wide flight is short, the true axis runs
    from the point through barrel and shaft into the flight."""
    x0, y0, _, _ = bbox
    scale = (camera.image_size[0] if camera else added.shape[1]) / 1280.0
    mask = fill_holes(added, max_area=2500 * scale * scale)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    keep = np.zeros(n, dtype=bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= 4
    ys, xs = np.nonzero(keep[labels])
    if len(xs) < max(12, cfg.min_dart_pixels * scale * scale):
        return []
    pts_crop = np.stack([xs, ys], 1)
    ideal = _ideal(pts_crop.astype(np.float64) + [x0, y0], camera)
    dt = cv2.distanceTransform(mask, cv2.DIST_L2, 3)[ys, xs]
    thin_w = 1.0 / (1.0 + dt ** 2)
    rng = np.random.default_rng(0)
    band = max(2.0, 2.5 * scale)
    max_gap = max(10, int(round(60 * scale / 2.0)))  # in 2-px bins (barrel may be invisible)
    min_cov_px = cfg.min_axis_length_px * scale
    remaining = np.ones(len(xs), dtype=bool)
    # Hypotheses are scored on a 2x2-subsampled point set (4x fewer points); the winner is
    # refined on all points.
    grid = ((xs % 2) == 0) & ((ys % 2) == 0)
    candidates: list[DartCandidate] = []
    for _ in range(cfg.max_candidates_per_camera):
        idx = np.nonzero(remaining)[0]
        if len(idx) < 12:
            break
        found = coverage_ransac(ideal[idx], thin_w[idx], rng, cfg.line_ransac_iterations, band, max_gap,
                                search=grid[idx])
        if found is None:
            break
        line, cov_px, s_lo, s_hi = found
        if cov_px < min_cov_px:
            break
        # Pixels belonging to this structure: a generous band around the axis within the
        # covered extent.
        s_all = line.project_scalar(ideal[idx])
        d_all = np.abs(line.distances(ideal[idx]))
        member = (d_all <= max(14.0 * scale, 4.0)) & (s_all >= s_lo - 4) & (s_all <= s_hi + 4)
        cand = _axis_candidate(pts_crop[idx[member]], mask, diff, bbox, camera, cfg, camera_id, occluders,
                               roi, scale, rng, dart_length_mm or cfg.dart_length_mm, line)
        # Remove the structure before the next search: its own thin band along the whole
        # axis, and a wide band only around its tail third (the flight). A wide band along
        # the whole line would erase other darts crossing it.
        thin_band = max(6.0 * scale, 1.5 * (cand.width_px if cand else 6.0))
        remove = (d_all <= thin_band) & (s_all >= s_lo - 6) & (s_all <= s_hi + 6)
        if cand is not None:
            tail_s = float(line.project_scalar(_ideal(cand.tail_px[None], camera))[0])
            tip_s = float(line.project_scalar(_ideal(cand.tip_px[None], camera))[0])
            third = tip_s + (tail_s - tip_s) * 0.66
            in_tail = (s_all - third) * np.sign(tail_s - tip_s) >= 0
            remove |= in_tail & (d_all <= max(40.0 * scale, 3.0 * cand.width_px)) \
                & (s_all >= s_lo - 10) & (s_all <= s_hi + 10)
        remaining[idx[remove]] = False
        if cand is not None:
            candidates.append(cand)
    candidates.sort(key=lambda c: -c.confidence)
    return candidates


def fill_holes(mask: np.ndarray, max_area: float) -> np.ndarray:
    """Fill enclosed holes (e.g. a low-contrast barrel whose outline changed but whose
    interior did not)."""
    contours, hier = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hier is None:
        return mask
    out = mask.copy()
    for i, h in enumerate(hier[0]):
        if h[3] >= 0 and cv2.contourArea(contours[i]) <= max_area:
            cv2.drawContours(out, contours, i, 255, -1)
    return out


def coverage_ransac(pts: np.ndarray, weights: np.ndarray, rng: np.random.Generator, iterations: int,
                    band: float, max_gap_bins: int, bin_px: float = 2.0, search: np.ndarray | None = None
                    ) -> tuple[Line2D, float, float, float] | None:
    """Line maximising the length of its longest covered run (gaps ≤ max_gap_bins).
    Returns (line, covered length px, s_start, s_end) with s along the returned line.
    ``search`` optionally selects the (subsampled) points used to score hypotheses."""
    n = len(pts)
    if n < 2:
        return None
    sp = pts if search is None or search.sum() < 20 else pts[search]
    sw = weights if search is None or search.sum() < 20 else weights[search]
    ns = len(sp)
    if ns < 2:
        return None
    p = sw / sw.sum()
    # Subsampling thins the coverage: bins are scored at twice the size.
    sbin = bin_px * (1.0 if sp is pts else 2.0)
    sgap = max_gap_bins if sp is pts else max(1, max_gap_bins // 2)
    sband = band if sp is pts else band + 1.0
    pairs = rng.choice(ns, size=(iterations, 2), replace=True, p=p)
    best = None
    best_score = -1.0
    for i, j in pairs:
        d = sp[j] - sp[i]
        L = math.hypot(d[0], d[1])
        if L < 15.0:
            continue
        u = d / L
        rel = sp - sp[i]
        inb = np.abs(rel[:, 0] * -u[1] + rel[:, 1] * u[0]) <= sband
        if inb.sum() < 6:
            continue
        r_in = rel[inb]
        cov, lo, hi = _longest_run(r_in[:, 0] * u[0] + r_in[:, 1] * u[1], sbin, sgap)
        if cov > best_score:
            best_score = cov
            best = (sp[i].copy(), u, lo, hi)
    if best is None:
        return None
    origin, u, lo, hi = best
    # Refit on the covered run and recompute.
    for _ in range(2):
        rel = pts - origin
        s = rel @ u
        inb = (np.abs(rel @ np.array([-u[1], u[0]])) <= band) & (s >= lo - 2) & (s <= hi + 2)
        if inb.sum() < 8:
            break
        line = fit_line(pts[inb], weights[inb])
        origin, u = line.point, line.direction
        rel = pts - origin
        inb2 = np.abs(rel @ np.array([-u[1], u[0]])) <= band
        _, lo, hi = _longest_run(rel[inb2] @ u, bin_px, max_gap_bins)
    line = Line2D(point=origin, direction=u)
    rel = pts - origin
    inb = np.abs(rel @ line.normal) <= band
    cov, lo, hi = _longest_run(rel[inb] @ u, bin_px, max_gap_bins)
    return line, cov, lo, hi


def _longest_run(s: np.ndarray, bin_px: float, max_gap: int) -> tuple[float, float, float]:
    if s.size == 0:
        return 0.0, 0.0, 0.0
    raw = np.floor(s / bin_px).astype(np.int64)
    lo = int(raw.min())
    bins = np.nonzero(np.bincount(raw - lo))[0] + lo
    if bins.size == 1:
        return bin_px, bins[0] * bin_px, (bins[0] + 1) * bin_px
    breaks = np.nonzero(np.diff(bins) > max_gap)[0]
    starts = np.concatenate([[0], breaks + 1])
    ends = np.concatenate([breaks, [bins.size - 1]])
    counts = ends - starts + 1
    spans = bins[ends] - bins[starts] + 1
    # A dart covers its axis densely (gaps only where it is occluded or low-contrast);
    # scattered noise along a line does not. Coverage is discounted below 60 % fill.
    fill = counts / spans
    score = counts * np.minimum(1.0, fill / 0.6)
    k = int(np.argmax(score))
    return float(score[k] * bin_px), float(bins[starts[k]] * bin_px), float((bins[ends[k]] + 1) * bin_px)


def _ideal(px_full: np.ndarray, camera: CameraModel | None) -> np.ndarray:
    if camera is None or not np.any(camera.dist):
        return px_full.astype(np.float64)
    return camera.undistort_pixels(px_full.astype(np.float64))


def _axis_candidate(pts_crop, added, diff, bbox, camera, cfg, camera_id, occluders, roi, scale, rng,
                    dart_length_mm, line: Line2D) -> DartCandidate | None:
    x0, y0, x1, y1 = bbox
    offset = np.array([x0, y0], dtype=np.float64)
    if len(pts_crop) < 10:
        return None
    full = pts_crop.astype(np.float64) + offset
    ideal = _ideal(full, camera)
    weights = np.clip(diff[pts_crop[:, 1].astype(int), pts_crop[:, 0].astype(int)].astype(np.float64), 1.0, None)
    # Slice the structure along the axis and keep slice centres of the thin part.
    s = line.project_scalar(ideal)
    d = line.distances(ideal)
    band = np.ones(len(s), dtype=bool)
    if band.sum() < 10:
        return None
    sb, db, wb = s[band], d[band], weights[band]
    step = max(1.0, 1.5 * scale)
    bins = np.floor((sb - sb.min()) / step).astype(np.int64)
    # Per-slice statistics, vectorised: centre along the axis, weighted perpendicular
    # centre, and width (extent across the axis).
    order = np.argsort(bins, kind="stable")
    bsorted = bins[order]
    starts = np.nonzero(np.r_[True, bsorted[1:] != bsorted[:-1]])[0]
    counts = np.diff(np.r_[starts, len(bsorted)])
    if len(starts) < 6:
        return None
    cs = np.add.reduceat(sb[order], starts) / counts
    cd = np.add.reduceat(db[order] * wb[order], starts) / np.add.reduceat(wb[order], starts)
    cw = np.maximum.reduceat(db[order], starts) - np.minimum.reduceat(db[order], starts) + 1.0
    # Reference width from the tip half (point/barrel); the flight is in the tail half.
    tip_low = _tip_at_low_end(line, float(cs.min()), float(cs.max()), camera, cw, cs, line)
    mid_s = (cs.min() + cs.max()) / 2
    tip_half = cs <= mid_s if tip_low else cs >= mid_s
    w_ref = float(np.median(cw[tip_half])) if tip_half.sum() >= 3 else float(np.percentile(cw, 35))
    thin = cw <= max(1.8 * w_ref, w_ref + 3)
    if thin.sum() < 5:
        return None
    centre_pts = line.at(cs) + cd[:, None] * line.normal[None, :]
    refined = ransac_line(centre_pts[thin], threshold=max(1.0, 0.8 * scale), iterations=150,
                          weights=1.0 / np.maximum(cw[thin], 1.0) ** 2, rng=rng, min_inliers=5)
    if refined is None:
        return None
    axis, inl = refined
    line_rms = float(np.sqrt(np.mean(axis.distances(centre_pts[thin][inl]) ** 2)))
    s_all = axis.project_scalar(ideal[band])
    s_thin = axis.project_scalar(centre_pts[thin][inl])
    s_lo, s_hi = float(s_all.min()), float(s_all.max())
    length = s_hi - s_lo

    # Which end touches the board? The tail lies towards +Z (out of the board).
    tip_at_low = _tip_at_low_end(axis, s_lo, s_hi, camera, cw, cs, line)
    # Visible entry point: extreme of the contiguous thin structure at the tip end,
    # refined with the change profile.
    s_tip_coarse = float(s_thin.min() if tip_at_low else s_thin.max())
    s_ext = float(s_lo if tip_at_low else s_hi)
    s_tip_coarse = s_ext if abs(s_ext - s_tip_coarse) < 12 * scale else s_tip_coarse
    tip_ideal, profile_ok = _refine_tip(axis, s_tip_coarse, -1.0 if tip_at_low else 1.0, diff, offset, camera)
    tail_s = s_hi if tip_at_low else s_lo
    tail_ideal = axis.at(tail_s)
    tip_px = _distort(tip_ideal, camera)
    tail_px = _distort(tail_ideal, camera)

    # Tip occluded by an older dart, or cut by the region border?
    tip_visible = profile_ok
    probe_dir = -axis.direction if tip_at_low else axis.direction
    probe = [tip_ideal + probe_dir * k for k in (2.0, 4.0, 6.0)]
    for p in probe:
        q = _distort(p, camera) - offset
        xi, yi = int(round(q[0])), int(round(q[1]))
        if not (0 <= xi < added.shape[1] and 0 <= yi < added.shape[0]):
            tip_visible = False
            break
        if occluders is not None and occluders[yi, xi] > 0:
            tip_visible = False
        if roi is not None:
            fx, fy = xi + x0, yi + y0
            if 0 <= fy < roi.shape[0] and 0 <= fx < roi.shape[1] and roi[fy, fx] == 0:
                tip_visible = False

    # Plausibility factors.
    f_elong = _soft(length / max(w_ref, 1.0), cfg.min_elongation, cfg.min_elongation * 2)
    f_straight = _soft(1.0 / max(line_rms, 0.05), 1.0 / max(1.5 * scale, 0.5), 1.0 / max(0.6 * scale, 0.2))
    f_len = 1.0
    expected = _expected_length_px(camera, tip_px, dart_length_mm) if camera is not None else None
    if expected:
        ratio = length / expected
        lo = 1.0 - cfg.dart_length_tolerance
        hi = 1.0 + cfg.dart_length_tolerance
        f_len = 1.0 if lo <= ratio <= hi else max(0.05, 1.0 - min(abs(ratio - lo), abs(ratio - hi)) * 2.5)
    f_support = _soft(float(inl.sum()), 5, 15)
    conf = float(f_elong * f_straight * f_len * f_support)
    if length < cfg.min_axis_length_px * scale * 0.5:
        return None

    xs_full = full[band][:, 0]
    ys_full = full[band][:, 1]
    bx0, by0 = int(xs_full.min()), int(ys_full.min())
    bx1, by1 = int(xs_full.max()) + 1, int(ys_full.max()) + 1
    cmask = np.zeros((by1 - by0, bx1 - bx0), dtype=np.uint8)
    cmask[(ys_full - by0).astype(int), (xs_full - bx0).astype(int)] = 255
    return DartCandidate(
        camera_id=camera_id, tip_px=tip_px, tail_px=tail_px, axis_ideal=axis, line_rms_px=line_rms,
        n_slices=int(inl.sum()), length_px=length, width_px=w_ref, tip_visible=bool(tip_visible),
        confidence=conf, pixel_count=int(band.sum()), mask_bbox=(bx0, by0, bx1, by1), mask=cmask,
        factors={"elongation": f_elong, "straightness": f_straight, "length": f_len, "support": f_support,
                 "expected_length_px": expected or 0.0},
    )


def _tip_at_low_end(axis: Line2D, s_lo: float, s_hi: float, camera: CameraModel | None,
                    widths: np.ndarray, centres_s: np.ndarray, coarse: Line2D) -> bool:
    if camera is not None:
        mid = axis.at((s_lo + s_hi) / 2)
        mid_px = _distort(mid, camera)
        p = camera.pixel_to_board(tuple(mid_px))
        if p is not None:
            base = np.array([p[0], p[1], 0.0])
            a, b = camera.project(np.array([base, base + [0, 0, 40.0]]))
            up = camera.undistort_pixels(np.array([a, b]))
            vz = up[1] - up[0]
            if np.linalg.norm(vz) > 1e-6:
                return float(axis.direction @ vz) > 0  # tail at +s ⇒ tip at the low end
    # Fallback: the flight (wide) is at the tail.
    order = np.argsort(centres_s)
    w = widths[order]
    k = max(1, len(w) // 4)
    return float(np.mean(w[:k])) < float(np.mean(w[-k:]))


def _refine_tip(axis: Line2D, s0: float, sign: float, diff: np.ndarray, offset: np.ndarray,
                camera: CameraModel | None) -> tuple[np.ndarray, bool]:
    """Find where the change contrast along the axis falls to half of the point's contrast."""
    ts = np.arange(-10.0, 10.0, 0.25)
    pts_ideal = axis.at(s0 + sign * ts)
    pts = _distort(pts_ideal, camera) - offset
    vals = cv2.remap(diff, pts[:, 0].astype(np.float32).reshape(-1, 1), pts[:, 1].astype(np.float32).reshape(-1, 1),
                     cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0).ravel()
    inside = vals[ts < -2.0]
    if inside.size == 0 or float(np.median(inside)) <= 1e-3:
        return axis.at(s0), False
    level = 0.5 * float(np.median(inside))
    above = vals >= level
    # Last position (moving outward from inside the dart) where the contrast is above level.
    idx = np.nonzero(above)[0]
    if idx.size == 0:
        return axis.at(s0), False
    k = idx.max()
    if k + 1 < len(ts):
        v0, v1 = vals[k], vals[k + 1]
        f = (v0 - level) / (v0 - v1) if v0 != v1 else 0.0
        t_edge = ts[k] + f * 0.25
    else:
        return axis.at(s0 + sign * ts[k]), False
    return axis.at(s0 + sign * t_edge), True


def _distort(p_ideal: np.ndarray, camera: CameraModel | None) -> np.ndarray:
    p = np.asarray(p_ideal, dtype=np.float64)
    single = p.ndim == 1
    p2 = p.reshape(-1, 2)
    if camera is None or not np.any(camera.dist):
        out = p2
    else:
        n = (p2 - camera.K[:2, 2]) / np.array([camera.K[0, 0], camera.K[1, 1]])
        out = camera.normalized_to_pixels(n)
    return out[0] if single else out


def _expected_length_px(camera: CameraModel, tip_px: np.ndarray, dart_length_mm: float) -> float | None:
    p = camera.pixel_to_board((float(tip_px[0]), float(tip_px[1])))
    if p is None:
        return None
    base = np.array([p[0], p[1], 0.0])
    # Visible part of a typical dart standing roughly perpendicular (tip partly embedded).
    a, b = camera.project(np.array([base, base + [0, 0.15 * dart_length_mm, 0.92 * dart_length_mm]]))
    return float(np.linalg.norm(b - a))


def _soft(v: float, lo: float, hi: float) -> float:
    if v >= hi:
        return 1.0
    if v <= lo:
        return 0.1 if v > 0 else 0.0
    return 0.1 + 0.9 * (v - lo) / (hi - lo)
