import numpy as np
import pytest

from vision.geometry.camera_model import CameraModel, default_intrinsics
from vision.geometry.lines import fit_line, intersect_board_lines, least_squares_line_from_planes, ransac_line


@pytest.fixture
def cam() -> CameraModel:
    K = default_intrinsics(1280, 720, 70)
    return CameraModel.look_at(np.array([60.0, -330.0, 110.0]), np.zeros(3), K, (1280, 720),
                               dist=np.array([-0.1, 0.03, 0.001, -0.0005, 0.0]), camera_id="c")


def test_project_backproject_roundtrip(cam: CameraModel) -> None:
    rng = np.random.default_rng(1)
    pts = np.concatenate([rng.uniform(-170, 170, (200, 2)), np.zeros((200, 1))], axis=1)
    px = cam.project(pts)
    xy, valid = cam.pixels_to_board(px)
    assert valid.all()
    assert np.max(np.abs(xy - pts[:, :2])) < 1e-6


def test_undistort_inverse_of_distort(cam: CameraModel) -> None:
    n = np.array([[0.1, -0.2], [0.4, 0.3], [-0.5, 0.1]])
    px = cam.normalized_to_pixels(n)
    assert np.allclose(cam.undistort_normalized(px), n, atol=1e-8)


def test_homography_matches_projection_without_distortion() -> None:
    K = default_intrinsics(1280, 720, 70)
    cam = CameraModel.look_at(np.array([0.0, 300.0, 120.0]), np.zeros(3), K, (1280, 720))
    H = cam.homography()
    pts = np.array([[10.0, 20.0], [-100.0, 50.0], [80.0, -120.0]])
    hp = (H @ np.c_[pts, np.ones(3)].T).T
    hp = hp[:, :2] / hp[:, 2:]
    assert np.allclose(hp, cam.project(np.c_[pts, np.zeros(3)]), atol=1e-6)


def test_board_line_from_image_of_3d_line(cam: CameraModel) -> None:
    # A dart axis through (30, 40, 0) tilted towards the camera side.
    p0 = np.array([30.0, 40.0, 0.0])
    a = np.array([0.1, 0.2, 1.0])
    a /= np.linalg.norm(a)
    q = cam.project(np.array([p0, p0 + 100 * a]))
    line = cam.board_line_from_image_line(q[0], q[1])
    assert line is not None
    assert abs(line.distance(p0[:2])) < 1e-6


def test_planes_from_two_cameras_recover_axis(cam: CameraModel) -> None:
    K = default_intrinsics(1280, 720, 70)
    cam2 = CameraModel.look_at(np.array([-300.0, 150.0, 100.0]), np.zeros(3), K, (1280, 720))
    p0 = np.array([-20.0, 75.0, 0.0])
    a = np.array([-0.15, 0.25, 1.0])
    a /= np.linalg.norm(a)
    planes = []
    for c in (cam, cam2):
        q = c.project(np.array([p0, p0 + 90 * a]))
        n0, n1 = c.undistort_normalized(q)
        planes.append(c.plane_from_normalized_line(n0, n1))
    ns = np.array([p[0] for p in planes])
    ds = np.array([p[1] for p in planes])
    pt, d = least_squares_line_from_planes(ns, ds, np.ones(2))
    if d[2] < 0:
        d = -d
    assert np.allclose(d, a, atol=1e-6)
    lines = [c.board_line_from_plane(*p) for c, p in zip((cam, cam2), planes)]
    sol = intersect_board_lines(np.array([l.normal for l in lines]), np.array([l.offset for l in lines]), np.ones(2))
    assert np.allclose(sol[0], p0[:2], atol=1e-6)


def test_scaled_camera_maps_pixels(cam: CameraModel) -> None:
    half = cam.scaled(0.5)
    p = np.array([[25.0, -60.0, 0.0]])
    full_px = cam.project(p)[0]
    half_px = half.project(p)[0]
    assert np.allclose(half_px, (full_px + 0.5) * 0.5 - 0.5, atol=1e-6)


def test_serialization_roundtrip(cam: CameraModel) -> None:
    c2 = CameraModel.from_dict(cam.to_dict())
    assert np.allclose(c2.K, cam.K) and np.allclose(c2.R, cam.R) and np.allclose(c2.t, cam.t)


def test_line_fitting() -> None:
    rng = np.random.default_rng(3)
    s = rng.uniform(-50, 50, 200)
    pts = np.c_[10 + s * 0.6, 5 + s * 0.8] + rng.normal(0, 0.3, (200, 2))
    outliers = rng.uniform(-60, 60, (60, 2))
    line = fit_line(pts)
    assert abs(abs(line.direction @ np.array([0.6, 0.8])) - 1) < 1e-3
    res = ransac_line(np.r_[pts, outliers], threshold=1.0, iterations=300, rng=rng)
    assert res is not None
    assert abs(abs(res[0].direction @ np.array([0.6, 0.8])) - 1) < 1e-3
