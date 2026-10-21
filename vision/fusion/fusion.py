"""Multi-camera fusion of dart observations into a board impact point.

Geometry (see docs/VISION.md §5):

* The dart axis seen by camera *c* is an image line. Back-projected, it spans a plane Πc
  through the camera centre that contains the 3D dart axis. Πc ∩ {Z = 0} is a line ℓc on
  the board; the impact point lies on ℓc. ℓc is precise *perpendicular* to itself.
* The visible entry point (tip) back-projected onto Z = 0 gives a point estimate qc, with
  an anisotropic covariance (poor along the viewing direction at grazing angles). Tips are
  often blurred, hidden or extended by a shadow, so they enter with robust (Huber) weights.
* The impact p minimises Σ (nc·p − dc)²/σc² + Σ ρ((p − qc)ᵀ Σc⁻¹ (p − qc)). The inverse
  information matrix is its covariance, which drives the score probability.
* With ≥2 cameras the planes also give the 3D axis (dart tilt). Every hypothesis must pass
  physical checks (plausible tilt, impact at the observed tip end, flight above the board),
  and cameras that should see the dart but show no change there count against it.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field

import numpy as np

from vision.config import FusionConfig
from vision.dart_detection.candidates import DartCandidate
from vision.geometry.camera_model import BoardLine, CameraModel
from vision.geometry.lines import least_squares_line_from_planes

_TIP_HIDDEN_FACTOR = 6.0  # tip sigma multiplier when the entry point may be occluded
_TIP_HUBER = 2.5  # tips beyond this Mahalanobis distance are down-weighted


@dataclass(eq=False)
class Observation:
    camera_id: str
    candidate: DartCandidate
    line: BoardLine
    plane_n: np.ndarray
    plane_d: float
    tip_xy: np.ndarray | None
    tip_cov: np.ndarray | None


@dataclass(eq=False)
class FusedDart:
    impact: np.ndarray  # (2,) mm
    cov: np.ndarray  # (2,2) mm²
    observations: list[Observation]
    residuals_mm: dict[str, float]
    normalized_residuals: dict[str, float]
    chi2: float
    dof: int
    axis: np.ndarray | None = None  # 3D unit direction (towards the flight)
    tilt_deg: float | None = None
    rejected: dict[str, str] = field(default_factory=dict)
    tip_weights: dict[str, float] = field(default_factory=dict)

    @property
    def line_chi2(self) -> float:
        return float(sum(v * v for v in self.normalized_residuals.values()))

    @property
    def line_consistency(self) -> float:
        """Agreement of the camera lines alone (tips are expected to disagree more)."""
        dof = len(self.observations) - 2
        if dof <= 0:
            return 1.0
        return float(math.exp(-0.5 * max(0.0, self.line_chi2 - dof) / dof))

    @property
    def cameras(self) -> list[str]:
        return [o.camera_id for o in self.observations]

    @property
    def sigma_mm(self) -> float:
        """RMS 1-σ radius of the impact uncertainty."""
        return float(math.sqrt(max(np.trace(self.cov), 0.0) / 2.0))

    @property
    def consistency(self) -> float:
        """Agreement of the cameras in [0, 1] (1 = residuals as expected from noise)."""
        if self.dof <= 0:
            return 1.0
        return float(math.exp(-0.5 * max(0.0, self.chi2 - self.dof) / max(self.dof, 1)))


def make_observation(cam: CameraModel, cand: DartCandidate, cfg: FusionConfig) -> Observation | None:
    line = cam.board_line_from_image_line(cand.tip_px, cand.tail_px)
    if line is None:
        return None
    n0, n1 = cam.undistort_normalized(np.array([cand.tip_px, cand.tail_px]))
    plane_n, plane_d = cam.plane_from_normalized_line(n0, n1)
    # Perpendicular uncertainty of the image line at the tip, propagated to the board.
    sigma_px = math.sqrt(cfg.line_sigma_px ** 2 + cand.line_rms_px ** 2 / max(1.0, cand.n_slices / 8.0))
    d = cand.tail_px - cand.tip_px
    nd = np.linalg.norm(d)
    if nd < 1e-6:
        return None
    perp = np.array([-d[1], d[0]]) / nd
    shifted = cam.board_line_from_image_line(cand.tip_px + perp * sigma_px, cand.tail_px + perp * sigma_px)
    tip_xy = cam.pixel_to_board(tuple(cand.tip_px))
    if shifted is None or tip_xy is None:
        return None
    sigma_mm = abs(shifted.distance(tip_xy) - line.distance(tip_xy))
    # Less plausible candidates (partly occluded, short, irregular) are trusted less.
    quality = max(cand.confidence, 0.2) ** 0.5
    line.sigma_mm = math.sqrt(sigma_mm ** 2 + cfg.line_sigma_floor_mm ** 2) / quality
    line.camera_id = cam.camera_id
    tip_cov = None
    J = cam.board_jacobian(tuple(cand.tip_px))
    if J is not None:
        s = cfg.tip_sigma_px * (1.0 if cand.tip_visible else _TIP_HIDDEN_FACTOR)
        tip_cov = (s * s) * (J @ J.T) + np.eye(2) * 1e-4
    return Observation(cam.camera_id, cand, line, plane_n, plane_d, tip_xy, tip_cov)


def _max_line_angle(observations: list[Observation]) -> float:
    best = 0.0
    for a, b in itertools.combinations(observations, 2):
        c = abs(float(a.line.normal @ b.line.normal))
        best = max(best, math.degrees(math.acos(min(1.0, c))))
    return best


def solve(observations: list[Observation], min_line_angle_deg: float = 12.0
          ) -> tuple[np.ndarray, np.ndarray, float, int, dict[str, float]] | None:
    """Robust weighted least squares (IRLS with Huber weights on tips).
    Returns (p, cov, robust chi², dof, tip weights by camera)."""
    A_l = np.zeros((2, 2))
    b_l = np.zeros(2)
    for o in observations:
        w = 1.0 / o.line.sigma_mm ** 2
        A_l += w * np.outer(o.line.normal, o.line.normal)
        b_l += w * o.line.normal * o.line.offset
    tips = [o for o in observations if o.tip_cov is not None and o.tip_xy is not None]
    infos = {o.camera_id: np.linalg.inv(o.tip_cov) for o in tips}
    weights = {o.camera_id: 1.0 for o in tips}
    # Start from the line intersection when the lines cross at a useful angle.
    if len(observations) >= 2 and _max_line_angle(observations) >= min_line_angle_deg \
            and np.linalg.cond(A_l) < 1e10:
        p0 = np.linalg.solve(A_l, b_l)
        for o in tips:
            r = p0 - o.tip_xy
            m = math.sqrt(max(float(r @ infos[o.camera_id] @ r), 0.0))
            weights[o.camera_id] = 1.0 if m <= _TIP_HUBER else _TIP_HUBER / m
    A = A_l
    p = None
    for _ in range(8):
        A = A_l.copy()
        b = b_l.copy()
        for o in tips:
            w = weights[o.camera_id]
            A += w * infos[o.camera_id]
            b += w * infos[o.camera_id] @ o.tip_xy
        if np.linalg.cond(A) > 1e10:
            return None
        p = np.linalg.solve(A, b)
        changed = False
        for o in tips:
            r = p - o.tip_xy
            m = math.sqrt(max(float(r @ infos[o.camera_id] @ r), 0.0))
            w = 1.0 if m <= _TIP_HUBER else _TIP_HUBER / m
            changed |= abs(w - weights[o.camera_id]) > 1e-3
            weights[o.camera_id] = w
        if not changed:
            break
    assert p is not None
    cov = np.linalg.inv(A)
    chi2 = sum((o.line.distance(p) / o.line.sigma_mm) ** 2 for o in observations)
    for o in tips:
        r = p - o.tip_xy
        m = math.sqrt(max(float(r @ infos[o.camera_id] @ r), 0.0))
        chi2 += m * m if m <= _TIP_HUBER else 2 * _TIP_HUBER * m - _TIP_HUBER ** 2
    dof = len(observations) + 2 * len(tips) - 2
    return p, cov, float(chi2), dof, weights


def _axis_3d(observations: list[Observation]) -> tuple[np.ndarray | None, float | None]:
    if len(observations) < 2:
        return None, None
    ns = np.array([o.plane_n for o in observations])
    ds = np.array([o.plane_d for o in observations])
    res = least_squares_line_from_planes(ns, ds, np.ones(len(ns)))
    if res is None:
        return None, None
    _, direction = res
    if direction[2] < 0:
        direction = -direction
    tilt = math.degrees(math.acos(min(1.0, abs(float(direction[2])))))
    return direction, tilt


def _evaluate(obs: list[Observation], cfg: FusionConfig) -> FusedDart | None:
    sol = solve(obs, cfg.min_line_angle_deg)
    if sol is None:
        return None
    p, cov, chi2, dof, tip_w = sol
    res_mm = {o.camera_id: abs(o.line.distance(p)) for o in obs}
    norm = {o.camera_id: abs(o.line.distance(p)) / o.line.sigma_mm for o in obs}
    axis, tilt = _axis_3d(obs)
    return FusedDart(p, cov, list(obs), res_mm, norm, chi2, dof, axis, tilt, tip_weights=tip_w)


def _reject_outliers(f: FusedDart, cfg: FusionConfig) -> FusedDart:
    while len(f.observations) > 2:
        worst = max(f.observations, key=lambda o: f.normalized_residuals[o.camera_id])
        if f.normalized_residuals[worst.camera_id] <= cfg.outlier_sigma and \
                f.residuals_mm[worst.camera_id] <= cfg.max_residual_mm:
            break
        rest = [o for o in f.observations if o is not worst]
        g = _evaluate(rest, cfg)
        if g is None:
            break
        g.rejected = dict(f.rejected)
        g.rejected[worst.camera_id] = "inconsistent with other cameras"
        f = g
    return f


def validate(f: FusedDart, cameras: dict[str, CameraModel], cfg: FusionConfig, max_tilt_deg: float,
             board_radius_mm: float = 225.5) -> str | None:
    """Physical checks a real dart must pass. Returns a rejection reason or None."""
    if float(np.hypot(*f.impact)) > board_radius_mm + 10.0:
        return "impact outside the board"
    if len(f.observations) == 1:
        # With several cameras around the board a real dart is seen by at least two; a
        # change only one camera sees is noise, a reflection or a dart it saw before.
        if len(cameras) >= cfg.min_cameras > 1:
            return "seen by one camera only"
        c = f.observations[0].candidate
        if c.confidence < 0.6 or not c.tip_visible:
            return "single weak observation"
    if len(f.observations) >= 2:
        if f.tilt_deg is None or f.tilt_deg > max_tilt_deg:
            return "implausible dart tilt"
        if max(f.residuals_mm.values()) > cfg.max_residual_mm:
            return "cameras disagree"
    impact3 = np.array([f.impact[0], f.impact[1], 0.0])
    for o in f.observations:
        cam = cameras[o.camera_id]
        c = o.candidate
        q = cam.project(impact3[None])[0]
        seg = c.tail_px - c.tip_px
        L = float(np.linalg.norm(seg))
        if L < 1e-6:
            return "degenerate observation"
        along = float((q - c.tip_px) @ seg) / L
        # The impact must project near the tip end of what this camera saw.
        if along < -max(40.0, 0.3 * L) or along > 0.45 * L:
            return f"impact not at the observed tip ({o.camera_id})"
        if f.axis is not None:
            # How far the observed tail reaches out of the board along the 3D axis.
            origin, dirs = cam.rays(np.array([c.tail_px]))
            d = dirs[0]
            a = f.axis
            w0 = origin - impact3
            ab = float(a @ d)
            den = 1.0 - ab * ab
            if den > 1e-6:
                t_axis = (float(a @ w0) - ab * float(d @ w0)) / den
                if t_axis < 25.0:
                    return f"observed dart too short above the board ({o.camera_id})"
    return None


def negative_evidence(f: FusedDart, cameras: dict[str, CameraModel],
                      support: dict[str, np.ndarray] | None, occluders: dict[str, np.ndarray] | None
                      ) -> float:
    """Penalty for cameras that should have seen this dart but show no change there."""
    if not support or f.axis is None:
        return 0.0
    penalty = 0.0
    used = set(f.cameras)
    impact3 = np.array([f.impact[0], f.impact[1], 0.0])
    pts3 = impact3[None, :] + np.linspace(5.0, 90.0, 18)[:, None] * f.axis[None, :]
    for cid, cam in cameras.items():
        if cid in used or cid not in support:
            continue
        mask = support[cid]
        px = cam.project(pts3)
        h, w = mask.shape
        inside = (px[:, 0] >= 0) & (px[:, 0] < w) & (px[:, 1] >= 0) & (px[:, 1] < h)
        if inside.sum() < 6:
            continue
        xi = px[inside, 0].astype(int)
        yi = px[inside, 1].astype(int)
        hit = mask[yi, xi] > 0
        if occluders and cid in occluders:
            hit = hit | (occluders[cid][yi, xi] > 0)
        if hit.mean() < 0.25:
            penalty += 8.0
    return penalty


def _score(f: FusedDart) -> float:
    """Higher is better: more cameras, then agreement and candidate quality."""
    s = len(f.observations) * 10.0
    s -= min(f.chi2 / max(f.dof, 1), 9.0)
    s += 2.0 * sum(o.candidate.confidence for o in f.observations)
    return s


def _independent_second_dart(f: FusedDart, accepted: list[FusedDart]) -> bool:
    """Several darts in one settled scene are rare (quick throws). An additional dart is
    only accepted with strong, independent evidence; otherwise it is far more likely to be
    a leftover fragment of the first one (flight, shadow, a second edge)."""
    if len(f.observations) < 2:
        return False
    if min(o.candidate.confidence for o in f.observations) < 0.6:
        return False
    for a in accepted:
        if np.linalg.norm(a.impact - f.impact) < 6.0:
            return False
        for o in f.observations:
            for ao in a.observations:
                if ao.camera_id == o.camera_id and _mask_overlap(ao.candidate, o.candidate) > 0.2:
                    return False
    return True


def _mask_overlap(a: DartCandidate, b: DartCandidate) -> float:
    ax0, ay0, ax1, ay1 = a.mask_bbox
    bx0, by0, bx1, by1 = b.mask_bbox
    x0, y0, x1, y1 = max(ax0, bx0), max(ay0, by0), min(ax1, bx1), min(ay1, by1)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    ma = a.mask[y0 - ay0:y1 - ay0, x0 - ax0:x1 - ax0] > 0
    mb = b.mask[y0 - by0:y1 - by0, x0 - bx0:x1 - bx0] > 0
    inter = np.count_nonzero(ma & mb)
    return inter / max(1, min(np.count_nonzero(a.mask), np.count_nonzero(b.mask)))


def fuse(
    cameras: dict[str, CameraModel],
    candidates: dict[str, list[DartCandidate]],
    cfg: FusionConfig,
    max_tilt_deg: float = 65.0,
    max_darts: int = 3,
    support: dict[str, np.ndarray] | None = None,
    occluders: dict[str, np.ndarray] | None = None,
    board_radius_mm: float = 225.5,
) -> list[FusedDart]:
    """Match candidates across cameras and fuse each matched set. Returns fused darts,
    best first. ``support`` (full-frame change masks) and ``occluders`` (pixels of darts
    already in the board) enable the negative-evidence check."""
    obs: dict[str, list[Observation]] = {}
    for cid, cands in candidates.items():
        cam = cameras.get(cid)
        if cam is None:
            continue
        lst = [o for c in cands if c.confidence >= cfg.min_candidate_confidence
               and (o := make_observation(cam, c, cfg)) is not None]
        if lst:
            obs[cid] = lst
    results: list[FusedDart] = []
    used: dict[str, set[int]] = {cid: set() for cid in obs}
    for _ in range(max_darts):
        best: FusedDart | None = None
        best_key: tuple | None = None
        best_score = -1e9
        cams = list(obs.keys())
        choices = [[None] + [i for i in range(len(obs[c])) if i not in used[c]] for c in cams]
        for combo in itertools.product(*choices):
            chosen = [(c, i) for c, i in zip(cams, combo) if i is not None]
            if not chosen:
                continue
            f = _evaluate([obs[c][i] for c, i in chosen], cfg)
            if f is None:
                continue
            f = _reject_outliers(f, cfg)
            if validate(f, cameras, cfg, max_tilt_deg, board_radius_mm) is not None:
                continue
            sc = _score(f) - negative_evidence(f, cameras, support, occluders)
            if sc > best_score:
                best, best_score = f, sc
                best_key = tuple((o.camera_id, obs[o.camera_id].index(o)) for o in f.observations)
        if best is None or best_key is None:
            break
        if results and not _independent_second_dart(best, results):
            break
        if results and negative_evidence(best, cameras, support, occluders) > 0:
            # An additional dart in the same scene must not be contradicted by a camera
            # with a clear view of it: two cameras' shadows or fragments can intersect on
            # the board and look like a dart the third camera plainly does not see.
            break
        results.append(best)
        for c, i in best_key:
            used[c].add(i)
        if all(len(used[c]) >= len(obs[c]) for c in obs):
            break
    return results
