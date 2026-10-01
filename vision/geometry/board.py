"""Mathematical model of a dartboard in polar coordinates.

Board frame (see docs/ARCHITECTURE.md §5): millimetres, origin at the bull centre on the
board surface, +X right, +Y up (towards the 20), +Z out of the board. The polar angle θ is
measured clockwise from +Y, so the 20 is centred on θ = 0 and the 1 on θ = 18°.

Scoring regions are defined exclusively by the radii and sector order in
:class:`vision.config.BoardConfig` — there are no hard-coded regions anywhere else.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

import numpy as np

from vision.config import BoardConfig


class Ring(str, Enum):
    INNER_BULL = "inner_bull"  # 50
    OUTER_BULL = "outer_bull"  # 25
    INNER_SINGLE = "inner_single"  # between outer bull and triple
    TRIPLE = "triple"
    OUTER_SINGLE = "outer_single"  # between triple and double
    DOUBLE = "double"
    MISS = "miss"  # outside the double ring


_RING_MULTIPLIER = {
    Ring.INNER_BULL: 2,
    Ring.OUTER_BULL: 1,
    Ring.INNER_SINGLE: 1,
    Ring.TRIPLE: 3,
    Ring.OUTER_SINGLE: 1,
    Ring.DOUBLE: 2,
    Ring.MISS: 0,
}


@dataclass(frozen=True)
class DartScore:
    """The value of one dart, independent of any game rules."""

    sector: int  # 1..20, 25 for bull, 0 for a miss
    multiplier: int  # 1, 2, 3; 0 for a miss
    ring: Ring

    @property
    def score(self) -> int:
        return self.sector * self.multiplier

    @property
    def label(self) -> str:
        if self.ring == Ring.MISS:
            return "MISS"
        if self.ring == Ring.INNER_BULL:
            return "BULL"
        if self.ring == Ring.OUTER_BULL:
            return "25"
        prefix = {1: "S", 2: "D", 3: "T"}[self.multiplier]
        return f"{prefix}{self.sector}"

    @property
    def key(self) -> str:
        """Region identifier: distinguishes inner and outer singles (used for probability
        bookkeeping, since they are physically different regions with the same value)."""
        if self.ring in (Ring.MISS, Ring.INNER_BULL, Ring.OUTER_BULL):
            return self.ring.value
        return f"{self.ring.value}:{self.sector}"

    def to_dict(self) -> dict:
        return {
            "sector": self.sector,
            "multiplier": self.multiplier,
            "score": self.score,
            "ring": self.ring.value,
            "label": self.label,
        }

    @staticmethod
    def from_label(label: str) -> "DartScore":
        """Parse 'T20', 'D16', 'S5', '5', '25', 'BULL', 'DB', 'MISS'."""
        s = label.strip().upper()
        if not s:
            raise ValueError("empty dart label")
        if s in ("MISS", "M", "0", "OUT"):
            return DartScore(0, 0, Ring.MISS)
        if s in ("BULL", "DB", "D25", "50", "BE"):
            return DartScore(25, 2, Ring.INNER_BULL)
        if s in ("25", "SB", "S25", "OB"):
            return DartScore(25, 1, Ring.OUTER_BULL)
        prefix, num = (s[0], s[1:]) if s[0] in "SDT" else ("S", s)
        if not num.isdigit():
            raise ValueError(f"invalid dart label {label!r}")
        sector = int(num)
        if not 1 <= sector <= 20:
            raise ValueError(f"invalid sector in {label!r}")
        ring = {"S": Ring.OUTER_SINGLE, "D": Ring.DOUBLE, "T": Ring.TRIPLE}[prefix]
        return DartScore(sector, {"S": 1, "D": 2, "T": 3}[prefix], ring)


class BoardGeometry:
    def __init__(self, config: BoardConfig | None = None) -> None:
        self.config = config or BoardConfig()
        c = self.config
        self.sector_order: tuple[int, ...] = tuple(c.sector_order)
        self.n_sectors = len(self.sector_order)
        self.sector_angle_deg = 360.0 / self.n_sectors
        # Ring boundaries, ordered from the centre outwards.
        self.ring_radii: dict[str, float] = {
            "inner_bull": c.inner_bull_radius_mm,
            "outer_bull": c.outer_bull_radius_mm,
            "triple_inner": c.triple_inner_radius_mm,
            "triple_outer": c.triple_outer_radius_mm,
            "double_inner": c.double_inner_radius_mm,
            "double_outer": c.double_outer_radius_mm,
        }
        self._sector_index = {s: i for i, s in enumerate(self.sector_order)}

    # ------------------------------------------------------------------ polar helpers
    @staticmethod
    def to_polar(x_mm: float, y_mm: float) -> tuple[float, float]:
        """(r, θ) with θ in degrees clockwise from +Y, in [0, 360)."""
        r = math.hypot(x_mm, y_mm)
        theta = math.degrees(math.atan2(x_mm, y_mm)) % 360.0
        return r, theta

    @staticmethod
    def from_polar(r_mm: float, theta_deg: float) -> tuple[float, float]:
        t = math.radians(theta_deg)
        return r_mm * math.sin(t), r_mm * math.cos(t)

    def sector_at_angle(self, theta_deg: float) -> int:
        half = self.sector_angle_deg / 2.0
        index = int(((theta_deg + half) % 360.0) // self.sector_angle_deg)
        return self.sector_order[index % self.n_sectors]

    def sector_center_angle(self, sector: int) -> float:
        return self._sector_index[sector] * self.sector_angle_deg

    def sector_boundary_angles(self) -> list[float]:
        """The 20 wire angles between sectors; boundary k is the left edge of sector index k."""
        half = self.sector_angle_deg / 2.0
        return [(k * self.sector_angle_deg - half) % 360.0 for k in range(self.n_sectors)]

    def ring_at_radius(self, r_mm: float) -> Ring:
        rr = self.ring_radii
        if r_mm <= rr["inner_bull"]:
            return Ring.INNER_BULL
        if r_mm <= rr["outer_bull"]:
            return Ring.OUTER_BULL
        if r_mm < rr["triple_inner"]:
            return Ring.INNER_SINGLE
        if r_mm <= rr["triple_outer"]:
            return Ring.TRIPLE
        if r_mm < rr["double_inner"]:
            return Ring.OUTER_SINGLE
        if r_mm <= rr["double_outer"]:
            return Ring.DOUBLE
        return Ring.MISS

    # ------------------------------------------------------------------ scoring
    def score(self, x_mm: float, y_mm: float) -> DartScore:
        r, theta = self.to_polar(x_mm, y_mm)
        ring = self.ring_at_radius(r)
        if ring == Ring.MISS:
            return DartScore(0, 0, ring)
        if ring in (Ring.INNER_BULL, Ring.OUTER_BULL):
            return DartScore(25, _RING_MULTIPLIER[ring], ring)
        return DartScore(self.sector_at_angle(theta), _RING_MULTIPLIER[ring], ring)

    def score_many(self, xy_mm: np.ndarray) -> list[str]:
        """Vectorised region keys (see DartScore.key) for an (N, 2) array."""
        x = xy_mm[:, 0]
        y = xy_mm[:, 1]
        r = np.hypot(x, y)
        theta = np.degrees(np.arctan2(x, y)) % 360.0
        half = self.sector_angle_deg / 2.0
        idx = (((theta + half) % 360.0) // self.sector_angle_deg).astype(int) % self.n_sectors
        sectors = np.asarray(self.sector_order)[idx]
        rr = self.ring_radii
        keys: list[str] = []
        for ri, si in zip(r, sectors):
            if ri <= rr["inner_bull"]:
                keys.append(Ring.INNER_BULL.value)
            elif ri <= rr["outer_bull"]:
                keys.append(Ring.OUTER_BULL.value)
            elif ri < rr["triple_inner"]:
                keys.append(f"{Ring.INNER_SINGLE.value}:{si}")
            elif ri <= rr["triple_outer"]:
                keys.append(f"{Ring.TRIPLE.value}:{si}")
            elif ri < rr["double_inner"]:
                keys.append(f"{Ring.OUTER_SINGLE.value}:{si}")
            elif ri <= rr["double_outer"]:
                keys.append(f"{Ring.DOUBLE.value}:{si}")
            else:
                keys.append(Ring.MISS.value)
        return keys

    @staticmethod
    def score_from_key(key: str) -> DartScore:
        if ":" not in key:
            ring = Ring(key)
            if ring == Ring.MISS:
                return DartScore(0, 0, ring)
            return DartScore(25, _RING_MULTIPLIER[ring], ring)
        ring_name, sector = key.split(":")
        ring = Ring(ring_name)
        return DartScore(int(sector), _RING_MULTIPLIER[ring], ring)

    def distance_to_boundary(self, x_mm: float, y_mm: float) -> float:
        """Euclidean distance (mm) from a point to the nearest scoring boundary (ring wire or
        sector wire). Used for quick sanity checks; scoring confidence is computed from the
        full covariance in scoring/probability.py."""
        r, theta = self.to_polar(x_mm, y_mm)
        d_ring = min(abs(r - rb) for rb in self.ring_radii.values())
        if r <= self.ring_radii["outer_bull"] or r > self.ring_radii["double_outer"]:
            return d_ring
        # Distance to the nearest radial wire: r * sin(angular distance).
        half = self.sector_angle_deg / 2.0
        rel = (theta + half) % self.sector_angle_deg
        dtheta = min(rel, self.sector_angle_deg - rel)
        d_sector = r * math.sin(math.radians(dtheta))
        return min(d_ring, d_sector)

    # ------------------------------------------------------------------ model points
    def ring_color(self, sector_index: int) -> str:
        first = self.config.first_sector_ring_color
        other = "green" if first == "red" else "red"
        return first if sector_index % 2 == 0 else other

    def color_categories(self, xy: np.ndarray) -> np.ndarray:
        """Nominal colour category of board points (N,2): 0 black single, 1 white single,
        2 red, 3 green, 4 black surround (outside the double ring), 5 wall (off the board).
        Standard boards: the 20's single is black and its double/triple red."""
        xy = np.asarray(xy, dtype=np.float64).reshape(-1, 2)
        r = np.hypot(xy[:, 0], xy[:, 1])
        theta = np.degrees(np.arctan2(xy[:, 0], xy[:, 1])) % 360.0
        half = self.sector_angle_deg / 2.0
        idx = (((theta + half) % 360.0) // self.sector_angle_deg).astype(int) % self.n_sectors
        even = idx % 2 == 0
        first_red = self.config.first_sector_ring_color == "red"
        rr = self.ring_radii
        cat = np.where(even, 0, 1)
        ring = ((r >= rr["triple_inner"]) & (r <= rr["triple_outer"])) | \
               ((r >= rr["double_inner"]) & (r <= rr["double_outer"]))
        cat = np.where(ring, np.where(even == first_red, 2, 3), cat)
        cat = np.where((r <= rr["outer_bull"]) & (r > rr["inner_bull"]), 3, cat)
        cat = np.where(r <= rr["inner_bull"], 2, cat)
        cat = np.where(r > rr["double_outer"], 4, cat)
        cat = np.where(r > self.config.board_radius_mm, 5, cat)
        return cat

    def circle_points(self, radius_mm: float, n: int) -> np.ndarray:
        """n points on a circle of the board plane, as (n, 3) board-frame coordinates."""
        t = np.linspace(0.0, 2.0 * np.pi, n, endpoint=False)
        return np.stack([radius_mm * np.sin(t), radius_mm * np.cos(t), np.zeros(n)], axis=1)

    def sector_boundary_points(self, radius_mm: float) -> np.ndarray:
        pts = [self.from_polar(radius_mm, a) for a in self.sector_boundary_angles()]
        return np.array([[x, y, 0.0] for x, y in pts])

    def edge_model(self, samples_per_mm: float = 0.25) -> tuple[np.ndarray, np.ndarray]:
        """Points sampled along every wire of the board, with the unit in-plane normal of
        the wire at each sample. Returns (points (N,3), normals (N,3)). Used for edge-based
        pose refinement and calibration validation."""
        pts: list[np.ndarray] = []
        normals: list[np.ndarray] = []
        for radius in self.ring_radii.values():
            n = max(24, int(2 * math.pi * radius * samples_per_mm))
            p = self.circle_points(radius, n)
            pts.append(p)
            normals.append(p / radius)
        r0 = self.ring_radii["outer_bull"]
        r1 = self.ring_radii["double_outer"]
        n_rad = max(8, int((r1 - r0) * samples_per_mm))
        radii = np.linspace(r0 + 2.0, r1 - 2.0, n_rad)
        for angle in self.sector_boundary_angles():
            t = math.radians(angle)
            direction = np.array([math.sin(t), math.cos(t), 0.0])
            normal = np.array([math.cos(t), -math.sin(t), 0.0])
            pts.append(radii[:, None] * direction[None, :])
            normals.append(np.repeat(normal[None, :], n_rad, axis=0))
        return np.concatenate(pts), np.concatenate(normals)

    def describe(self) -> dict:
        return {
            "radii_mm": dict(self.ring_radii),
            "board_radius_mm": self.config.board_radius_mm,
            "sector_order": list(self.sector_order),
            "sector_angle_deg": self.sector_angle_deg,
            "wire_width_mm": self.config.wire_width_mm,
            "coordinate_system": {
                "units": "mm",
                "origin": "bull centre on the board surface",
                "x": "right (towards 6)",
                "y": "up (towards 20)",
                "z": "out of the board towards the player",
                "theta": "degrees clockwise from +Y (centre of the 20)",
            },
        }
