"""2D/3D line utilities: robust weighted line fitting and intersections."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Line2D:
    point: np.ndarray  # (2,) a point on the line (the weighted centroid)
    direction: np.ndarray  # (2,) unit direction
    rms: float = 0.0  # RMS orthogonal residual of the fitted points
    n_points: int = 0

    @property
    def normal(self) -> np.ndarray:
        return np.array([-self.direction[1], self.direction[0]])

    def distances(self, pts: np.ndarray) -> np.ndarray:
        return (np.asarray(pts, dtype=np.float64) - self.point) @ self.normal

    def project_scalar(self, pts: np.ndarray) -> np.ndarray:
        return (np.asarray(pts, dtype=np.float64) - self.point) @ self.direction

    def at(self, s: float | np.ndarray) -> np.ndarray:
        s = np.asarray(s, dtype=np.float64)
        return self.point + s[..., None] * self.direction


def fit_line(pts: np.ndarray, weights: np.ndarray | None = None) -> Line2D:
    """Weighted total-least-squares line fit."""
    pts = np.asarray(pts, dtype=np.float64)
    w = np.ones(len(pts)) if weights is None else np.asarray(weights, dtype=np.float64)
    wsum = w.sum()
    if len(pts) < 2 or wsum <= 0:
        raise ValueError("need at least two weighted points")
    c = (pts * w[:, None]).sum(0) / wsum
    d = pts - c
    cov = (d * w[:, None]).T @ d / wsum
    evals, evecs = np.linalg.eigh(cov)
    direction = evecs[:, 1]
    line = Line2D(point=c, direction=direction / np.linalg.norm(direction), n_points=len(pts))
    line.rms = float(np.sqrt(max(evals[0], 0.0)))
    return line


def ransac_line(
    pts: np.ndarray,
    threshold: float,
    iterations: int = 200,
    weights: np.ndarray | None = None,
    rng: np.random.Generator | None = None,
    min_inliers: int = 10,
) -> tuple[Line2D, np.ndarray] | None:
    """RANSAC + weighted refit. Returns (line, inlier mask) or None."""
    pts = np.asarray(pts, dtype=np.float64)
    n = len(pts)
    if n < max(2, min_inliers):
        return None
    rng = rng or np.random.default_rng(0)
    w = np.ones(n) if weights is None else np.asarray(weights, dtype=np.float64)
    p = w / w.sum()
    # Draw the pairs as before (the generator is shared with later steps), then score them
    # all at once; the first pair with the highest score wins, as in a loop.
    pairs = np.array([rng.choice(n, size=2, replace=False, p=p) for _ in range(iterations)]).reshape(-1, 2)
    best_mask: np.ndarray | None = None
    d = pts[pairs[:, 1]] - pts[pairs[:, 0]]
    norm = np.hypot(d[:, 0], d[:, 1])
    ok = norm >= 1e-6
    if ok.any():
        pairs, d, norm = pairs[ok], d[ok], norm[ok]
        nx, ny = -d[:, 1] / norm, d[:, 0] / norm
        batch = max(1, int(2_000_000 // n))
        best_score = -1.0
        for b0 in range(0, len(pairs), batch):
            sl = slice(b0, b0 + batch)
            o = pts[pairs[sl, 0]]
            dist = np.abs((pts[None, :, 0] - o[:, 0:1]) * nx[sl, None] + (pts[None, :, 1] - o[:, 1:2]) * ny[sl, None])
            masks = dist < threshold
            scores = masks @ w
            k = int(np.argmax(scores))
            if scores[k] > best_score:
                best_score, best_mask = float(scores[k]), masks[k].copy()
    if best_mask is None or best_mask.sum() < min_inliers:
        return None
    line = fit_line(pts[best_mask], w[best_mask])
    # Two refinement passes with the refitted model.
    for _ in range(2):
        mask = np.abs(line.distances(pts)) < threshold
        if mask.sum() < min_inliers:
            break
        line = fit_line(pts[mask], w[mask])
        best_mask = mask
    return line, best_mask


def intersect_board_lines(normals: np.ndarray, offsets: np.ndarray,
                          weights: np.ndarray) -> tuple[np.ndarray, np.ndarray] | None:
    """Weighted least-squares intersection of lines nᵢ·p = cᵢ. Returns (p, information
    matrix A = Σ wᵢ nᵢnᵢᵀ) or None when degenerate."""
    A = np.einsum("i,ij,ik->jk", weights, normals, normals)
    b = np.einsum("i,ij,i->j", weights, normals, offsets)
    if np.linalg.cond(A) > 1e8:
        return None
    return np.linalg.solve(A, b), A


def plane_plane_line(n1: np.ndarray, d1: float, n2: np.ndarray, d2: float
                     ) -> tuple[np.ndarray, np.ndarray] | None:
    """Intersection line of two planes n·X = d. Returns (point, unit direction)."""
    direction = np.cross(n1, n2)
    norm = np.linalg.norm(direction)
    if norm < 1e-9:
        return None
    direction /= norm
    A = np.stack([n1, n2, direction])
    b = np.array([d1, d2, 0.0])
    point = np.linalg.solve(A, b)
    return point, direction


def least_squares_line_from_planes(normals: np.ndarray, offsets: np.ndarray,
                                   weights: np.ndarray) -> tuple[np.ndarray, np.ndarray] | None:
    """3D line best contained in several planes (weighted). The direction is the
    eigenvector of Σ wᵢ nᵢnᵢᵀ with the smallest eigenvalue; the point is the minimum-norm
    least-squares solution of nᵢ·X = dᵢ restricted to the orthogonal complement."""
    M = np.einsum("i,ij,ik->jk", weights, normals, normals)
    evals, evecs = np.linalg.eigh(M)
    direction = evecs[:, 0]
    if evals[1] < 1e-9:
        return None
    # Solve in the 2D subspace orthogonal to the direction.
    basis = evecs[:, 1:]
    A = (normals @ basis) * np.sqrt(weights)[:, None]
    b = offsets * np.sqrt(weights)
    coeffs, *_ = np.linalg.lstsq(A, b, rcond=None)
    point = basis @ coeffs
    return point, direction / np.linalg.norm(direction)
