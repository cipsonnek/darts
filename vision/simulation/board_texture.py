"""Top-down texture of a dartboard face (and the wall around it), in board millimetres."""

from __future__ import annotations

from functools import lru_cache

import cv2
import numpy as np

from vision.config import BoardConfig
from vision.geometry.board import BoardGeometry
from vision.imaging import srgb_to_linear

# BGR colours of a typical bristle board under neutral light.
COLORS = {
    "black": (32, 30, 30),
    "cream": (178, 208, 222),
    "red": (48, 40, 196),
    "green": (70, 135, 40),
    "wire": (190, 192, 196),
    "surround": (24, 24, 24),
    "number": (225, 225, 225),
    "wall": (150, 160, 168),
}


class BoardTexture:
    """A square BGR image covering ``[-extent_mm, extent_mm]²`` of the board plane.

    Pixel (u, v) ↔ board (x, y): x = (u + 0.5) / ppm - extent, y = extent - (v + 0.5) / ppm.
    """

    def __init__(self, board: BoardGeometry, pixels_per_mm: float = 4.0,
                 extent_mm: float = 330.0, seed: int = 7) -> None:
        self.board = board
        self.ppm = pixels_per_mm
        self.extent = extent_mm
        self.size = int(round(2 * extent_mm * pixels_per_mm))
        self.image = _render_texture(board, pixels_per_mm, extent_mm, seed)
        # Linear-light copy (0..255 scale) used by the renderer for physically correct blending.
        self.linear = srgb_to_linear(self.image) * 255.0

    def board_to_texture(self) -> np.ndarray:
        """3x3 affine (as homography) mapping board (x, y, 1) → texture pixel (u, v, 1)."""
        p = self.ppm
        return np.array([[p, 0, self.extent * p - 0.5],
                         [0, -p, self.extent * p - 0.5],
                         [0, 0, 1.0]])


def _render_texture(board: BoardGeometry, ppm: float, extent: float, seed: int) -> np.ndarray:
    size = int(round(2 * extent * ppm))
    coords = (np.arange(size, dtype=np.float32) + 0.5) / ppm - extent
    x = coords[None, :].repeat(size, 0)
    y = -coords[:, None].repeat(size, 1)
    r = np.hypot(x, y)
    theta = np.degrees(np.arctan2(x, y)) % 360.0
    half = board.sector_angle_deg / 2.0
    sector_idx = (((theta + half) % 360.0) // board.sector_angle_deg).astype(np.int32)
    rr = board.ring_radii
    cfg = board.config
    rng = np.random.default_rng(seed)

    img = np.empty((size, size, 3), dtype=np.float32)
    img[:] = COLORS["wall"]
    # Subtle wall texture.
    wall_noise = cv2.GaussianBlur(rng.normal(0, 1, (size, size)).astype(np.float32), (0, 0), 6)
    img += (wall_noise * 25.0)[..., None]

    inside = r <= cfg.board_radius_mm
    img[inside] = COLORS["surround"]

    even = (sector_idx % 2) == 0
    single = (r < rr["double_outer"]) & ~((r >= rr["triple_inner"]) & (r <= rr["triple_outer"])) \
        & ~((r >= rr["double_inner"])) & (r > rr["outer_bull"])
    img[single & even] = COLORS["black"]
    img[single & ~even] = COLORS["cream"]

    first_red = cfg.first_sector_ring_color == "red"
    ring = ((r >= rr["triple_inner"]) & (r <= rr["triple_outer"])) | \
        ((r >= rr["double_inner"]) & (r <= rr["double_outer"]))
    red_mask = ring & (even == first_red)
    green_mask = ring & (even != first_red)
    img[red_mask] = COLORS["red"]
    img[green_mask] = COLORS["green"]
    img[(r <= rr["outer_bull"]) & (r > rr["inner_bull"])] = COLORS["green"]
    img[r <= rr["inner_bull"]] = COLORS["red"]

    # Sisal fibre texture on the playing surface.
    fibre = rng.normal(0, 1, (size, size)).astype(np.float32)
    fibre = cv2.GaussianBlur(fibre, (0, 0), 0.8) * 9.0
    playing = r <= rr["double_outer"]
    img[playing] += fibre[playing][:, None]

    # Wires: rings and radial spokes.
    hw = cfg.wire_width_mm / 2.0
    wire = np.zeros((size, size), dtype=bool)
    for radius in rr.values():
        wire |= np.abs(r - radius) <= hw
    spoke_zone = (r >= rr["outer_bull"]) & (r <= rr["double_outer"])
    rel = (theta + half) % board.sector_angle_deg
    ang_dist = np.minimum(rel, board.sector_angle_deg - rel)
    wire |= spoke_zone & (r * np.sin(np.radians(ang_dist)) <= hw)
    img[wire] = COLORS["wire"]

    img = np.clip(img, 0, 255).astype(np.uint8)
    _draw_numbers(img, board, ppm, extent)
    return img


def _draw_numbers(img: np.ndarray, board: BoardGeometry, ppm: float, extent: float) -> None:
    radius = (board.ring_radii["double_outer"] + board.config.board_radius_mm) / 2.0
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.085 * ppm * 3.2
    thickness = max(1, int(round(ppm * 0.9)))
    for i, sector in enumerate(board.sector_order):
        angle = i * board.sector_angle_deg
        x, y = board.from_polar(radius, angle)
        text = str(sector)
        (tw, th), _ = cv2.getTextSize(text, font, scale, thickness)
        patch = np.zeros((th * 3, tw + th * 2), dtype=np.uint8)
        cv2.putText(patch, text, (th, int(th * 2)), font, scale, 255, thickness, cv2.LINE_AA)
        # Numbers are upright relative to the board centre (rotated with their sector).
        M = cv2.getRotationMatrix2D((patch.shape[1] / 2, patch.shape[0] / 2), -angle, 1.0)
        rotated = cv2.warpAffine(patch, M, (patch.shape[1], patch.shape[0]))
        u = int(round((x + extent) * ppm - rotated.shape[1] / 2))
        v = int(round((extent - y) * ppm - rotated.shape[0] / 2))
        h, w = rotated.shape
        if u < 0 or v < 0 or u + w > img.shape[1] or v + h > img.shape[0]:
            continue
        alpha = (rotated.astype(np.float32) / 255.0)[..., None]
        roi = img[v:v + h, u:u + w].astype(np.float32)
        roi = roi * (1 - alpha) + np.array(COLORS["number"], np.float32) * alpha
        img[v:v + h, u:u + w] = roi.astype(np.uint8)


@lru_cache(maxsize=4)
def cached_texture(board_cfg_json: str, pixels_per_mm: float = 4.0, extent_mm: float = 330.0) -> BoardTexture:
    cfg = BoardConfig.model_validate_json(board_cfg_json)
    return BoardTexture(BoardGeometry(cfg), pixels_per_mm, extent_mm)
