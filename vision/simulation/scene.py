"""Scene description for the synthetic renderer: dart models, occluders and lighting."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class DartStyle:
    """Physical dimensions (mm) and colours (BGR) of a steel-tip dart."""

    point_length: float = 32.0
    point_radius: float = 1.15
    barrel_length: float = 48.0
    barrel_radius: float = 3.4
    barrel_color: tuple[int, int, int] = (118, 118, 124)
    barrel_knurl_bands: int = 9
    shaft_length: float = 35.0
    shaft_radius: float = 2.5
    shaft_color: tuple[int, int, int] = (35, 35, 35)
    flight_length: float = 36.0
    flight_span: float = 16.0  # wing width measured from the axis
    flight_overlap: float = 14.0  # how far the shaft is inside the flight
    flight_color: tuple[int, int, int] = (40, 40, 200)
    flight_pattern_color: tuple[int, int, int] | None = (230, 230, 230)
    specular: float = 0.45

    @property
    def total_length(self) -> float:
        return (self.point_length + self.barrel_length + self.shaft_length
                + self.flight_length - self.flight_overlap)


DART_STYLES: dict[str, DartStyle] = {
    "classic_red": DartStyle(),
    "blue_black": DartStyle(barrel_color=(95, 95, 100), shaft_color=(180, 90, 20),
                            flight_color=(30, 30, 30), flight_pattern_color=(220, 120, 20)),
    "white_green": DartStyle(barrel_color=(150, 150, 152), shaft_color=(230, 230, 230),
                             flight_color=(40, 170, 40), flight_pattern_color=None),
    "gold_slim": DartStyle(barrel_radius=3.0, barrel_length=52.0, barrel_color=(60, 150, 190),
                           shaft_color=(20, 20, 20), flight_color=(30, 200, 230),
                           flight_pattern_color=(20, 20, 20), flight_span=14.0),
    "dark_stealth": DartStyle(barrel_color=(45, 45, 48), shaft_color=(25, 25, 25),
                              flight_color=(28, 28, 30), flight_pattern_color=None),
}


@dataclass
class DartInstance:
    """A dart in the scene. ``impact`` is where the axis meets the board plane (Z=0);
    ``axis`` is the unit direction from the impact point towards the flight (axis_z > 0)."""

    impact: np.ndarray  # (2,) mm
    axis: np.ndarray  # (3,) unit
    style: DartStyle = field(default_factory=DartStyle)
    roll_deg: float = 0.0
    embed_depth: float = 9.0
    # Additional axis offsets for motion blur (in-flight darts); each entry is a full pose
    # (impact (2,) or 3D tip position (3,), axis (3,)) rendered and averaged.
    blur_poses: list[tuple[np.ndarray, np.ndarray]] = field(default_factory=list)
    tip_position: np.ndarray | None = None  # 3D tip for darts not in the board (flight)
    dart_id: str = ""

    def __post_init__(self) -> None:
        self.impact = np.asarray(self.impact, dtype=np.float64).reshape(2)
        a = np.asarray(self.axis, dtype=np.float64).reshape(3)
        self.axis = a / np.linalg.norm(a)

    @staticmethod
    def from_angles(impact_xy, tilt_up_deg: float = 10.0, tilt_right_deg: float = 0.0,
                    **kwargs) -> "DartInstance":
        """Axis from two tilt angles relative to the board normal: positive ``tilt_up``
        raises the flight towards +Y, positive ``tilt_right`` moves it towards +X."""
        ty = math.tan(math.radians(tilt_up_deg))
        tx = math.tan(math.radians(tilt_right_deg))
        axis = np.array([tx, ty, 1.0])
        return DartInstance(impact=np.asarray(impact_xy, float), axis=axis, **kwargs)

    def surface_point(self) -> np.ndarray:
        """3D start of the visible dart (board entry point), or the tip in flight."""
        if self.tip_position is not None:
            return np.asarray(self.tip_position, dtype=np.float64)
        return np.array([self.impact[0], self.impact[1], 0.0])

    def visible_point_length(self) -> float:
        if self.tip_position is not None:
            return self.style.point_length
        return max(self.style.point_length - self.embed_depth, 1.0)


@dataclass
class Sphere:
    center: np.ndarray
    radius: float
    color: tuple[int, int, int]


@dataclass
class Capsule:
    p0: np.ndarray
    p1: np.ndarray
    radius: float
    color: tuple[int, int, int]


@dataclass
class Occluder:
    """A hand/arm or other object in front of the board, built from simple primitives."""

    spheres: list[Sphere] = field(default_factory=list)
    capsules: list[Capsule] = field(default_factory=list)

    @staticmethod
    def hand(position_xy: np.ndarray, z: float = 60.0, scale: float = 1.0,
             skin: tuple[int, int, int] = (120, 150, 200),
             arm_direction: np.ndarray | None = None) -> "Occluder":
        """A rough hand reaching towards the board at ``position_xy`` with the arm coming
        from below/in front."""
        c = np.array([position_xy[0], position_xy[1], z], dtype=np.float64)
        arm_dir = np.array([0.15, -0.6, 1.0]) if arm_direction is None else np.asarray(arm_direction, float)
        arm_dir /= np.linalg.norm(arm_dir)
        palm = Sphere(c, 45 * scale, skin)
        fingers = [
            Capsule(c + np.array([dx, 30 * scale, -10]), c + np.array([dx * 1.2, 85 * scale, -30]),
                    9 * scale, skin)
            for dx in (-27 * scale, -9 * scale, 9 * scale, 27 * scale)
        ]
        thumb = Capsule(c + np.array([-40 * scale, 0, 0]), c + np.array([-70 * scale, 35 * scale, -15]),
                        10 * scale, skin)
        sleeve = (60, 60, 80)
        arm = Capsule(c - arm_dir * 30, c + arm_dir * 700, 42 * scale, sleeve)
        return Occluder(spheres=[palm], capsules=fingers + [thumb, arm])


@dataclass
class Lighting:
    """Directional key light + ambient, a smooth illumination gradient over the board and a
    colour tint. ``direction`` points from the scene towards the light."""

    gain: float = 1.0
    ambient: float = 0.55
    diffuse: float = 0.6
    direction: np.ndarray = field(default_factory=lambda: np.array([0.25, 0.55, 0.8]))
    shadow_strength: float = 0.35
    shadow_blur_mm: float = 1.5
    gradient: tuple[float, float] = (0.0, 0.0)  # relative gain change per 200 mm in x / y
    tint: tuple[float, float, float] = (1.0, 1.0, 1.0)  # BGR multipliers

    def __post_init__(self) -> None:
        d = np.asarray(self.direction, dtype=np.float64)
        self.direction = d / np.linalg.norm(d)


LIGHTING_PRESETS: dict[str, Lighting] = {
    "neutral": Lighting(),
    # LED ring around the board: bright, diffuse, almost no shadows.
    "led_ring": Lighting(gain=1.1, ambient=0.75, diffuse=0.35, direction=np.array([0.0, 0.2, 1.0]),
                         shadow_strength=0.12, shadow_blur_mm=4.0),
    "warm": Lighting(gain=0.95, tint=(0.82, 0.97, 1.12), gradient=(0.08, -0.05)),
    "dim": Lighting(gain=0.45, ambient=0.5, diffuse=0.5, shadow_strength=0.3),
    "bright": Lighting(gain=1.45, ambient=0.6, diffuse=0.7, shadow_strength=0.45),
    "uneven": Lighting(gain=1.0, gradient=(0.35, -0.3), direction=np.array([-0.7, 0.3, 0.6]),
                       shadow_strength=0.5),
    "side_light": Lighting(gain=1.0, ambient=0.45, diffuse=0.8, direction=np.array([0.9, 0.1, 0.4]),
                           shadow_strength=0.55, shadow_blur_mm=1.0),
}


def perpendicular_basis(axis: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    a = axis / np.linalg.norm(axis)
    hint = np.array([0.0, 0.0, 1.0]) if abs(a[2]) < 0.9 else np.array([0.0, 1.0, 0.0])
    e1 = np.cross(a, hint)
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(a, e1)
    return e1, e2
