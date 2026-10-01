"""Score probability: how likely is each scoring region given the impact estimate and its
covariance? This turns geometric uncertainty into a calibrated, explainable confidence and
yields meaningful alternatives (e.g. T20 vs. T5 for a dart on the wire)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from vision.geometry.board import BoardGeometry, DartScore


@dataclass
class ScoreProbability:
    score: DartScore
    probability: float

    def to_dict(self) -> dict:
        return {**self.score.to_dict(), "probability": round(self.probability, 4)}


def score_distribution(board: BoardGeometry, mean: np.ndarray, cov: np.ndarray, n_samples: int = 4000,
                       model_sigma_mm: float = 0.25, seed: int | None = None) -> list[ScoreProbability]:
    """Monte-Carlo integration of N(mean, cov + model²·I) over the board regions. Regions
    that share a value (inner/outer single of the same sector) are merged."""
    mean = np.asarray(mean, dtype=np.float64).reshape(2)
    c = np.asarray(cov, dtype=np.float64).reshape(2, 2) + np.eye(2) * model_sigma_mm ** 2
    c = (c + c.T) / 2
    if seed is None:
        seed = int(abs(mean[0] * 1000.0) + abs(mean[1] * 7919.0)) % (2 ** 31)
    rng = np.random.default_rng(seed)
    try:
        L = np.linalg.cholesky(c)
    except np.linalg.LinAlgError:
        w, v = np.linalg.eigh(c)
        L = v @ np.diag(np.sqrt(np.clip(w, 1e-9, None)))
    samples = mean[None, :] + rng.standard_normal((n_samples, 2)) @ L.T
    keys = board.score_many(samples)
    counts: dict[str, int] = {}
    for k in keys:
        label = BoardGeometry.score_from_key(k).label
        counts[label] = counts.get(label, 0) + 1
    out = []
    for label, cnt in counts.items():
        out.append(ScoreProbability(DartScore.from_label(label) if label != "MISS" else
                                    DartScore(0, 0, BoardGeometry.score_from_key("miss").ring),
                                    cnt / n_samples))
    # Use the exact region of the mean for the representative score object.
    exact = board.score(*mean)
    for sp in out:
        if sp.score.label == exact.label:
            sp.score = exact
    out.sort(key=lambda s: -s.probability)
    return out
