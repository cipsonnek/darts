"""Photometric change detection between two *settled* frames of one camera.

Existing darts are present in both the reference and the current frame and cancel out, so
only what changed since the last stable state remains. Compared with plain frame
differencing this adds:

* gain normalisation (global per channel + a smooth low-frequency field), so lighting
  drift and auto-exposure steps are not mistaken for darts;
* a noise-adaptive threshold estimated from the image itself;
* shadow suppression: a pixel that became darker by a moderate factor, kept its
  chromaticity and kept its local texture (normalised cross-correlation with the
  reference) is a shadow on the board, not a dart;
* classification of changed pixels against the empty-board image into *added* (now
  differs from the empty board) and *removed* (now looks like the empty board again).
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from vision.config import DetectionConfig


@dataclass
class ChangeResult:
    bbox: tuple[int, int, int, int]  # x0, y0, x1, y1 of the analysed region (full-res pixels)
    added: np.ndarray  # uint8 mask (bbox-sized)
    removed: np.ndarray  # uint8 mask
    changed: np.ndarray  # uint8 mask before added/removed split
    diff: np.ndarray  # float32 change magnitude (bbox-sized)
    threshold: float
    noise_sigma: float
    shadow_pixels: int
    roi_pixels: int

    @property
    def added_fraction(self) -> float:
        return float(np.count_nonzero(self.added)) / max(1, self.roi_pixels)

    @property
    def removed_fraction(self) -> float:
        return float(np.count_nonzero(self.removed)) / max(1, self.roi_pixels)

    @property
    def changed_fraction(self) -> float:
        return float(np.count_nonzero(self.changed)) / max(1, self.roi_pixels)

    def full_mask(self, which: str, shape: tuple[int, int]) -> np.ndarray:
        out = np.zeros(shape, dtype=np.uint8)
        x0, y0, x1, y1 = self.bbox
        out[y0:y1, x0:x1] = getattr(self, which)
        return out


def roi_bbox(roi: np.ndarray) -> tuple[int, int, int, int]:
    ys, xs = np.nonzero(roi)
    if len(xs) == 0:
        return 0, 0, roi.shape[1], roi.shape[0]
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def _normalise(ref: np.ndarray, cur: np.ndarray, roi: np.ndarray) -> np.ndarray:
    """Scale ``ref`` so its brightness matches ``cur`` (per channel, smooth field)."""
    sel = roi > 0
    out = ref.astype(np.float32)
    curf = cur.astype(np.float32)
    # Global per-channel gain from bright-enough pixels.
    for c in range(3):
        a = curf[..., c][sel]
        b = out[..., c][sel]
        ok = (a > 20) & (b > 20)
        if ok.sum() > 100:
            g = float(np.median(a[ok] / b[ok]))
            out[..., c] *= np.clip(g, 0.3, 3.0)
    # Residual smooth gain field (uneven lighting change), robust to small objects.
    ga = cv2.cvtColor(curf, cv2.COLOR_BGR2GRAY)
    gb = cv2.cvtColor(out, cv2.COLOR_BGR2GRAY)
    small = (max(1, ga.shape[1] // 16), max(1, ga.shape[0] // 16))
    ra = cv2.resize(ga, small, interpolation=cv2.INTER_AREA)
    rb = cv2.resize(gb, small, interpolation=cv2.INTER_AREA)
    ratio = np.clip((ra + 4.0) / (rb + 4.0), 0.5, 2.0).astype(np.float32)
    ratio = cv2.medianBlur(ratio, 5)
    field = cv2.resize(ratio, (ga.shape[1], ga.shape[0]), interpolation=cv2.INTER_LINEAR)
    return out * field[..., None]


def _magnitude(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.max(np.abs(a.astype(np.float32) - b.astype(np.float32)), axis=2)


def _threshold(diff: np.ndarray, roi: np.ndarray, cfg: DetectionConfig) -> tuple[float, float]:
    vals = diff[roi > 0]
    if vals.size == 0:
        return cfg.change_min_delta, 0.0
    # Median of a max-of-3 half-normal noise distribution ≈ 1.2σ.
    sigma = float(np.median(vals)) / 1.2
    return max(cfg.change_min_delta, cfg.change_noise_sigma_factor * sigma), sigma


def _local_ncc(a: np.ndarray, b: np.ndarray, k: int = 7) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Local normalised cross-correlation of a and b, and the local std of a and b."""
    ma = cv2.blur(a, (k, k))
    mb = cv2.blur(b, (k, k))
    va = cv2.blur(a * a, (k, k)) - ma * ma
    vb = cv2.blur(b * b, (k, k)) - mb * mb
    cov = cv2.blur(a * b, (k, k)) - ma * mb
    ncc = cov / np.sqrt(np.maximum(va, 1e-3) * np.maximum(vb, 1e-3))
    return ncc, np.sqrt(np.maximum(va, 0)), np.sqrt(np.maximum(vb, 0))


def _photometric_model(ref: np.ndarray, cur: np.ndarray, roi: np.ndarray, scale: int = 4
                       ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Gain model mapping ``ref`` brightness onto ``cur``: per-channel global gain and a
    smooth relative field, estimated at 1/scale resolution. Returns (gain (3,), field_small,
    ref_small_normalised, cur_small, roi_small)."""
    h, w = cur.shape[:2]
    small = (max(1, w // scale), max(1, h // scale))
    rs = cv2.resize(ref, small, interpolation=cv2.INTER_AREA).astype(np.float32)
    cs = cv2.resize(cur, small, interpolation=cv2.INTER_AREA).astype(np.float32)
    rr = cv2.resize(roi, small, interpolation=cv2.INTER_NEAREST) > 0
    gain = np.ones(3, dtype=np.float32)
    for c in range(3):
        a, b = cs[..., c][rr], rs[..., c][rr]
        ok = (a > 20) & (b > 20)
        if ok.sum() > 50:
            gain[c] = float(np.clip(np.median(a[ok] / b[ok]), 0.3, 3.0))
    rs = rs * gain
    ga = cv2.cvtColor(cs, cv2.COLOR_BGR2GRAY)
    gb = cv2.cvtColor(rs, cv2.COLOR_BGR2GRAY)
    ratio = np.clip((ga + 4.0) / (gb + 4.0), 0.5, 2.0).astype(np.float32)
    # Median over ~20 low-res px (~80 full-res px): follows lighting gradients, ignores darts.
    coarse = (max(1, small[0] // 4), max(1, small[1] // 4))
    field = cv2.medianBlur(cv2.resize(ratio, coarse, interpolation=cv2.INTER_AREA), 5)
    field = cv2.resize(field, small, interpolation=cv2.INTER_LINEAR)
    return gain, field, rs * field[..., None], cs, rr


def _regions(seed: np.ndarray, scale: int, pad: int, shape: tuple[int, int]) -> list[tuple[int, int, int, int]]:
    """Bounding boxes (full-res, crop coordinates) of changed blobs found at low
    resolution, padded and merged."""
    seed = cv2.dilate(seed.astype(np.uint8), np.ones((3, 3), np.uint8))
    n, _, stats, _ = cv2.connectedComponentsWithStats(seed, connectivity=8)
    boxes: list[list[int]] = []
    H, W = shape
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if area < 2:
            continue
        boxes.append([max(0, x * scale - pad), max(0, y * scale - pad),
                      min(W, (x + w) * scale + pad), min(H, (y + h) * scale + pad)])
    merged = True
    while merged and len(boxes) > 1:
        merged = False
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                a, b = boxes[i], boxes[j]
                if a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]:
                    boxes[i] = [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]
                    boxes.pop(j)
                    merged = True
                    break
            if merged:
                break
    return [(b[0], b[1], b[2], b[3]) for b in boxes]


def compute_change(
    reference: np.ndarray,
    current: np.ndarray,
    roi: np.ndarray,
    cfg: DetectionConfig,
    empty: np.ndarray | None = None,
    scale: int = 4,
) -> ChangeResult:
    """Changes are located at 1/scale resolution first; the full-resolution analysis
    (threshold, shadows, added/removed) runs only inside the padded changed regions."""
    x0, y0, x1, y1 = roi_bbox(roi)
    ref = reference[y0:y1, x0:x1]
    cur = current[y0:y1, x0:x1]
    r = roi[y0:y1, x0:x1]
    H, W = cur.shape[:2]
    if cfg.photometric_normalization:
        gain, field_s, rs_n, cs, rr = _photometric_model(ref, cur, r, scale)
    else:
        gain = np.ones(3, np.float32)
        field_s = None
        small = (max(1, W // scale), max(1, H // scale))
        rs_n = cv2.resize(ref, small, interpolation=cv2.INTER_AREA).astype(np.float32)
        cs = cv2.resize(cur, small, interpolation=cv2.INTER_AREA).astype(np.float32)
        rr = cv2.resize(r, small, interpolation=cv2.INTER_NEAREST) > 0

    # Noise level from a random sample of full-resolution pixels.
    ys, xs = np.nonzero(r[::3, ::3])
    rng = np.random.default_rng(0)
    pick = rng.choice(len(xs), size=min(20000, len(xs)), replace=False) if len(xs) else np.array([], int)
    sy, sx = ys[pick] * 3, xs[pick] * 3
    fs = _field_at(field_s, sx, sy, scale)[:, None] if field_s is not None else 1.0
    sample = np.max(np.abs(cur[sy, sx].astype(np.float32) - ref[sy, sx].astype(np.float32) * gain * fs), axis=1)
    sigma = float(np.median(sample)) / 1.2 if sample.size else 0.0
    thr = max(cfg.change_min_delta, cfg.change_noise_sigma_factor * sigma)

    d_small = np.max(np.abs(cs - rs_n), axis=2)
    seed = (d_small > 0.45 * thr) & rr

    added_u8 = np.zeros((H, W), np.uint8)
    removed_u8 = np.zeros((H, W), np.uint8)
    changed_u8 = np.zeros((H, W), np.uint8)
    diff_full = np.zeros((H, W), np.float32)
    shadow_count = 0
    gain_v = gain.astype(np.float32)
    for bx0, by0, bx1, by1 in _regions(seed, scale, 32, (H, W)):
        sl = (slice(by0, by1), slice(bx0, bx1))
        cf = cur[sl].astype(np.float32)
        rg = r[sl] > 0
        ref_n = cv2.multiply(ref[sl].astype(np.float32), gain_v.reshape(1, 1, 3).repeat(by1 - by0, 0).repeat(bx1 - bx0, 1))
        if field_s is not None:
            fld = _field_region(field_s, bx0, by0, bx1, by1, scale)
            ref_n = cv2.multiply(ref_n, cv2.merge([fld, fld, fld]))
        diff = cv2.GaussianBlur(_chan_max(cv2.absdiff(cf, ref_n)), (0, 0), 0.7)
        # Edge-aware threshold: compression artefacts and sub-pixel jitter make strong
        # edges (wires, ring borders, flights) noisy, so changes there must be larger.
        gref = cv2.cvtColor(ref_n, cv2.COLOR_BGR2GRAY)
        grad = cv2.GaussianBlur(cv2.magnitude(cv2.Sobel(gref, cv2.CV_32F, 1, 0, ksize=3),
                                              cv2.Sobel(gref, cv2.CV_32F, 0, 1, ksize=3)) * 0.25, (0, 0), 1.0)
        thr_map = thr + cfg.change_edge_gain * grad
        changed = _hysteresis(diff, thr_map, cfg.change_weak_factor * thr_map) & rg
        changed = _drop_specks(changed, cfg.change_min_component_px)
        if cfg.shadow_suppression and changed.any():
            # Shadow model: current ≈ reference × s(x) with a *smooth* attenuation s
            # (penumbrae included). A dart replaces the surface with its own structure
            # (edges, knurling, shading), which this model cannot explain. The per-pixel
            # tests are evaluated only on changed pixels.
            gc = cv2.cvtColor(cf, cv2.COLOR_BGR2GRAY)
            gr = cv2.cvtColor(ref_n, cv2.COLOR_BGR2GRAY)
            att = cv2.GaussianBlur((gc + 2.0) / (gr + 2.0), (0, 0), 2.0)
            iy, ix = np.nonzero(changed)
            c_px = cf[iy, ix]
            r_px = ref_n[iy, ix]
            ratio = (c_px + 2.0) / (r_px + 2.0)
            darker = np.all((ratio >= cfg.shadow_min_ratio) & (ratio <= cfg.shadow_max_ratio), axis=1)
            chroma = np.max(np.abs(c_px / (c_px.sum(1, keepdims=True) + 1e-3)
                                   - r_px / (r_px.sum(1, keepdims=True) + 1e-3)), axis=1)
            a_px = att[iy, ix]
            explained = np.abs(gc[iy, ix] - gr[iy, ix] * a_px) < 0.5 * thr
            smooth_dark = (a_px >= cfg.shadow_min_ratio) & (a_px <= cfg.shadow_max_ratio + 0.05)
            sh = (darker | smooth_dark) & (chroma <= cfg.shadow_max_chroma_shift) & explained
            shadow_count += int(sh.sum())
            changed[iy[sh], ix[sh]] = False
        if empty is not None:
            emp_n = _match_to(empty[y0:y1, x0:x1][sl].astype(np.float32), cf, rg)
            occ_cur = cv2.GaussianBlur(_chan_max(cv2.absdiff(cf, emp_n)), (0, 0), 0.7) > thr
            occ_ref = cv2.GaussianBlur(_chan_max(cv2.absdiff(ref_n, emp_n)), (0, 0), 0.7) > thr
            added = changed & occ_cur
            removed = changed & ~occ_cur & occ_ref
        else:
            added = changed
            removed = np.zeros_like(changed)
        diff_full[sl] = np.maximum(diff_full[sl], diff)
        changed_u8[sl] |= changed.astype(np.uint8) * 255
        added_u8[sl] |= added.astype(np.uint8) * 255
        removed_u8[sl] |= removed.astype(np.uint8) * 255
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    added_u8 = cv2.morphologyEx(added_u8, cv2.MORPH_CLOSE, k) & ((r > 0).astype(np.uint8) * 255)
    return ChangeResult((x0, y0, x1, y1), added_u8, removed_u8, changed_u8, diff_full, thr, sigma,
                        shadow_count, int(np.count_nonzero(r)))


def _chan_max(img: np.ndarray) -> np.ndarray:
    b, g, r = cv2.split(img)
    return cv2.max(cv2.max(b, g), r)


def _drop_specks(mask: np.ndarray, min_px: int) -> np.ndarray:
    if min_px <= 1 or not mask.any():
        return mask
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    keep = np.zeros(n, dtype=bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= min_px
    return keep[labels]


def _hysteresis(diff: np.ndarray, strong, weak) -> np.ndarray:
    """Pixels above ``weak`` that are connected to a pixel above ``strong`` (thresholds may
    be scalars or per-pixel maps)."""
    weak_mask = (diff > weak).astype(np.uint8)
    n, labels = cv2.connectedComponents(weak_mask, connectivity=8)
    if n <= 1:
        return diff > strong
    has_strong = np.zeros(n, dtype=bool)
    has_strong[np.unique(labels[diff > strong])] = True
    has_strong[0] = False
    return has_strong[labels]


def _field_at(field_s: np.ndarray, xs: np.ndarray, ys: np.ndarray, scale: int) -> np.ndarray:
    fx = np.clip(xs // scale, 0, field_s.shape[1] - 1)
    fy = np.clip(ys // scale, 0, field_s.shape[0] - 1)
    return field_s[fy, fx]


def _field_region(field_s: np.ndarray, x0: int, y0: int, x1: int, y1: int, scale: int) -> np.ndarray:
    xs = (np.arange(x0, x1, dtype=np.float32) + 0.5) / scale - 0.5
    ys = (np.arange(y0, y1, dtype=np.float32) + 0.5) / scale - 0.5
    mx, my = np.meshgrid(xs, ys)
    return cv2.remap(field_s, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def _match_to(src: np.ndarray, target: np.ndarray, region: np.ndarray) -> np.ndarray:
    """Per-channel gain matching of ``src`` to ``target`` within a region."""
    ts = target[::3, ::3][region[::3, ::3]]
    ss = src[::3, ::3][region[::3, ::3]]
    g = np.ones(3, dtype=np.float32)
    for c in range(3):
        a, b = ts[:, c], ss[:, c]
        ok = (a > 20) & (b > 20)
        if ok.sum() > 30:
            g[c] = float(np.clip(np.median(a[ok] / b[ok]), 0.3, 3.0))
    return src * g


def occupancy(frame: np.ndarray, empty: np.ndarray, roi: np.ndarray, cfg: DetectionConfig
              ) -> tuple[np.ndarray, tuple[int, int, int, int], float]:
    """Pixels that differ from the empty board (darts, hands...). Returns (mask, bbox, thr)."""
    x0, y0, x1, y1 = roi_bbox(roi)
    cur = frame[y0:y1, x0:x1]
    r = roi[y0:y1, x0:x1]
    emp_n = _normalise(empty[y0:y1, x0:x1], cur, r)
    d = cv2.GaussianBlur(_magnitude(cur.astype(np.float32), emp_n), (0, 0), 0.7)
    thr, _ = _threshold(d, r, cfg)
    return ((d > thr) & (r > 0)).astype(np.uint8) * 255, (x0, y0, x1, y1), thr
