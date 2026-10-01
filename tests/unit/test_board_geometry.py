import math

import numpy as np
import pytest

from vision.config import BoardConfig
from vision.geometry.board import BoardGeometry, DartScore, Ring

B = BoardGeometry()
ORDER = [20, 1, 18, 4, 13, 6, 10, 15, 2, 17, 3, 19, 7, 16, 8, 11, 14, 9, 12, 5]

RING_RADII = {  # a radius safely inside each ring
    Ring.INNER_SINGLE: 60.0,
    Ring.TRIPLE: 103.0,
    Ring.OUTER_SINGLE: 135.0,
    Ring.DOUBLE: 166.0,
}
MULT = {Ring.INNER_SINGLE: 1, Ring.TRIPLE: 3, Ring.OUTER_SINGLE: 1, Ring.DOUBLE: 2}


@pytest.mark.parametrize("index,sector", list(enumerate(ORDER)))
@pytest.mark.parametrize("ring", list(RING_RADII))
def test_every_sector_and_ring(index: int, sector: int, ring: Ring) -> None:
    theta = index * 18.0  # centre of the sector, clockwise from the 20
    for offset in (-8.0, 0.0, 8.0):  # stay 1° away from the wires
        x, y = B.from_polar(RING_RADII[ring], theta + offset)
        s = B.score(x, y)
        assert s.sector == sector
        assert s.ring == ring
        assert s.multiplier == MULT[ring]
        assert s.score == sector * MULT[ring]


def test_orientation_convention() -> None:
    # +Y is up (towards the 20), +X right (towards the 6).
    assert B.score(0, 103).label == "T20"
    assert B.score(103, 0).label == "T6"
    assert B.score(0, -103).label == "T3"
    assert B.score(-103, 0).label == "T11"


@pytest.mark.parametrize("r,label", [(0.0, "BULL"), (6.0, "BULL"), (6.5, "25"), (15.5, "25"), (16.5, "S20"),
                                     (170.5, "MISS"), (200.0, "MISS")])
def test_bull_and_miss_radii(r: float, label: str) -> None:
    assert B.score(0, r).label == label


def test_regulation_dimensions() -> None:
    rr = B.ring_radii
    assert rr["inner_bull"] == pytest.approx(6.35)
    assert rr["outer_bull"] == pytest.approx(15.9)
    assert rr["triple_outer"] - rr["triple_inner"] == pytest.approx(8.0)
    assert rr["double_outer"] - rr["double_inner"] == pytest.approx(8.0)
    assert rr["double_outer"] == pytest.approx(170.0)


@pytest.mark.parametrize("ring_name,inside,outside", [
    ("triple_inner", "S20", "T20"), ("triple_outer", "T20", "S20"),
    ("double_inner", "S20", "D20"), ("double_outer", "D20", "MISS"),
])
def test_ring_boundaries(ring_name: str, inside: str, outside: str) -> None:
    r = B.ring_radii[ring_name]
    assert B.score(0, r - 0.05).label == inside
    assert B.score(0, r + 0.05).label == outside


def test_sector_boundaries() -> None:
    # The wire between 20 and 1 is at +9°.
    for r in (60.0, 103.0, 166.0):
        assert B.score(*B.from_polar(r, 8.9)).sector == 20
        assert B.score(*B.from_polar(r, 9.1)).sector == 1
    # Wrap-around between 5 and 20 at -9°.
    assert B.score(*B.from_polar(60, -8.9)).sector == 20
    assert B.score(*B.from_polar(60, -9.1)).sector == 5


def test_score_many_matches_score() -> None:
    rng = np.random.default_rng(0)
    pts = rng.uniform(-180, 180, (2000, 2))
    keys = B.score_many(pts)
    for p, k in zip(pts, keys):
        assert BoardGeometry.score_from_key(k).label == B.score(*p).label


@pytest.mark.parametrize("label,sector,mult", [("T20", 20, 3), ("d16", 16, 2), ("S5", 5, 1), ("7", 7, 1),
                                               ("25", 25, 1), ("BULL", 25, 2), ("MISS", 0, 0)])
def test_label_parsing(label: str, sector: int, mult: int) -> None:
    s = DartScore.from_label(label)
    assert (s.sector, s.multiplier) == (sector, mult)


@pytest.mark.parametrize("bad", ["T21", "X5", "D0", "", "T"])
def test_label_parsing_rejects(bad: str) -> None:
    with pytest.raises(ValueError):
        DartScore.from_label(bad)


def test_polar_roundtrip() -> None:
    for r, t in [(10, 0), (50, 90), (100, 225.5), (166, 359)]:
        x, y = B.from_polar(r, t)
        r2, t2 = B.to_polar(x, y)
        assert r2 == pytest.approx(r)
        assert t2 == pytest.approx(t % 360)


def test_distance_to_boundary() -> None:
    assert B.distance_to_boundary(0, 103) == pytest.approx(4.0)
    assert B.distance_to_boundary(*B.from_polar(60, 9.0)) == pytest.approx(0.0, abs=1e-6)


def test_custom_dimensions_and_validation() -> None:
    cfg = BoardConfig(triple_inner_radius_mm=95.0, triple_outer_radius_mm=105.0)
    b = BoardGeometry(cfg)
    assert b.score(0, 96).label == "T20"
    with pytest.raises(ValueError):
        BoardConfig(triple_inner_radius_mm=120.0)  # not increasing
    with pytest.raises(ValueError):
        BoardConfig(sector_order=[1] * 20)


def test_edge_model_normals_are_unit() -> None:
    pts, normals = B.edge_model(0.5)
    assert len(pts) > 2000
    assert np.allclose(np.linalg.norm(normals, axis=1), 1.0)
    assert np.allclose(pts[:, 2], 0.0)


def test_color_categories_standard_board() -> None:
    cats = B.color_categories(np.array([[0, 103], [0, 60], [*B.from_polar(60, 18)], [0, 166], [0, 3], [0, 10], [0, 190]]))
    assert list(cats) == [2, 0, 1, 2, 2, 3, 4]  # red T20, black S20, white S1, red D20, red bull, green 25, surround
    assert math.isclose(B.sector_center_angle(6), 90.0)
