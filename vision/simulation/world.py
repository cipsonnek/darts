"""A time-based simulated world: darts that fly in, land, wobble and settle; hands that pull
them out; lighting that changes. Every camera renders the same world at its own frame times,
so camera timing, temporal logic and multi-camera fusion are exercised exactly as with
real hardware — with exact ground truth for every dart."""

from __future__ import annotations

import itertools
import math
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from vision.config import BoardConfig
from vision.geometry.board import BoardGeometry, DartScore
from vision.geometry.camera_model import CameraModel
from vision.simulation.board_texture import BoardTexture
from vision.simulation.renderer import CameraRenderer, RenderOptions
from vision.simulation.scene import (
    DART_STYLES,
    LIGHTING_PRESETS,
    DartInstance,
    DartStyle,
    Lighting,
    Occluder,
)

FLIGHT_SPEED_MM_S = 14000.0
FLIGHT_VISIBLE_S = 0.08
EXPOSURE_S = 0.008


@dataclass
class GroundTruthDart:
    dart_id: str
    impact: np.ndarray  # (2,) mm
    axis: np.ndarray  # (3,)
    score: DartScore
    landed_at: float
    removed_at: float | None = None
    style_name: str = ""

    def to_dict(self) -> dict:
        return {
            "dart_id": self.dart_id,
            "impact_mm": [float(self.impact[0]), float(self.impact[1])],
            "axis": [float(v) for v in self.axis],
            "score": self.score.to_dict(),
            "landed_at": self.landed_at,
            "removed_at": self.removed_at,
            "style": self.style_name,
        }


@dataclass
class _WorldDart:
    instance: DartInstance
    gt: GroundTruthDart
    wobble_amp_deg: float
    wobble_freq_hz: float
    wobble_tau_s: float
    wobble_dir: np.ndarray


@dataclass
class _HandEvent:
    t0: float
    t1: float
    path: list[np.ndarray]  # waypoints (x, y, z) mm
    scale: float = 1.0

    def position(self, t: float) -> np.ndarray | None:
        if not (self.t0 <= t <= self.t1):
            return None
        u = (t - self.t0) / (self.t1 - self.t0) * (len(self.path) - 1)
        i = min(int(u), len(self.path) - 2)
        f = u - i
        return self.path[i] * (1 - f) + self.path[i + 1] * f


@dataclass
class _LightingEvent:
    t: float
    lighting: Lighting
    transition_s: float = 0.0


@dataclass
class ThrowParams:
    target: tuple[float, float] | None = None  # aim point mm; None → random
    scatter_mm: float = 0.0
    tilt_up_deg: float | None = None
    tilt_right_deg: float | None = None
    style: str | None = None
    roll_deg: float | None = None


class SimulatedWorld:
    def __init__(
        self,
        cameras: dict[str, CameraModel],
        board_config: BoardConfig | None = None,
        lighting: str = "neutral",
        seed: int = 1,
        render_options: RenderOptions | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.board = BoardGeometry(board_config or BoardConfig())
        self.texture = BoardTexture(self.board)
        self.cameras = dict(cameras)
        self.rng = np.random.default_rng(seed)
        self.clock = clock
        self._lock = threading.RLock()
        self._renderers = {
            cid: CameraRenderer(cam, self.board, self.texture, render_options, seed=seed * 101 + i)
            for i, (cid, cam) in enumerate(self.cameras.items())
        }
        self._darts: list[_WorldDart] = []
        self._hands: list[_HandEvent] = []
        self._lighting_events: list[_LightingEvent] = [_LightingEvent(-1e9, LIGHTING_PRESETS[lighting])]
        self._style_cycle = itertools.cycle(DART_STYLES.keys())
        self._persistent_occluders: list[Occluder] = []

    # ------------------------------------------------------------------ queries
    def now(self) -> float:
        return self.clock()

    @property
    def ground_truth(self) -> list[GroundTruthDart]:
        with self._lock:
            return [d.gt for d in self._darts]

    def darts_on_board(self, t: float | None = None) -> list[GroundTruthDart]:
        t = self.now() if t is None else t
        with self._lock:
            return [d.gt for d in self._darts
                    if d.gt.landed_at <= t and (d.gt.removed_at is None or d.gt.removed_at > t)]

    # ------------------------------------------------------------------ actions
    def throw(self, params: ThrowParams | None = None, at: float | None = None) -> GroundTruthDart:
        """Schedule a dart landing at time ``at`` (default: now + flight)."""
        p = params or ThrowParams()
        rng = self.rng
        with self._lock:
            t_land = (self.now() + FLIGHT_VISIBLE_S) if at is None else at
            if p.target is None:
                impact = self.random_board_point()
            else:
                impact = np.asarray(p.target, float) + rng.normal(0, p.scatter_mm, 2) if p.scatter_mm else np.asarray(p.target, float)
            tilt_up = p.tilt_up_deg if p.tilt_up_deg is not None else float(np.clip(rng.normal(10, 7), -10, 30))
            tilt_right = p.tilt_right_deg if p.tilt_right_deg is not None else float(np.clip(rng.normal(0, 7), -22, 22))
            style_name = p.style or next(self._style_cycle)
            style: DartStyle = DART_STYLES[style_name]
            roll = p.roll_deg if p.roll_deg is not None else float(rng.uniform(0, 90))
            inst = DartInstance.from_angles(impact, tilt_up, tilt_right, style=style, roll_deg=roll,
                                            embed_depth=float(rng.uniform(6, 13)))
            dart_id = uuid.uuid4().hex[:12]
            inst.dart_id = dart_id
            gt = GroundTruthDart(dart_id=dart_id, impact=inst.impact.copy(), axis=inst.axis.copy(),
                                 score=self.board.score(*inst.impact), landed_at=t_land,
                                 style_name=style_name)
            wd = rng.normal(0, 1, 3)
            wd -= (wd @ inst.axis) * inst.axis
            wd /= np.linalg.norm(wd)
            self._darts.append(_WorldDart(inst, gt, wobble_amp_deg=float(rng.uniform(1.5, 5.0)),
                                          wobble_freq_hz=float(rng.uniform(9, 16)),
                                          wobble_tau_s=float(rng.uniform(0.05, 0.11)), wobble_dir=wd))
            return gt

    def random_board_point(self, max_radius: float | None = None) -> np.ndarray:
        """Uniform over the board *area* up to the double ring (plus a margin for misses)."""
        r_max = max_radius or (self.board.ring_radii["double_outer"] + 8.0)
        r = r_max * math.sqrt(self.rng.uniform())
        theta = self.rng.uniform(0, 360)
        return np.array(self.board.from_polar(r, theta))

    def remove_darts(self, at: float | None = None, duration: float = 1.8) -> list[str]:
        """A hand reaches in, pulls every dart currently in the board, and leaves."""
        with self._lock:
            t0 = self.now() if at is None else at
            present = [d for d in self._darts if d.gt.landed_at <= t0 and d.gt.removed_at is None]
            if present:
                centroid = np.mean([d.gt.impact for d in present], axis=0)
            else:
                centroid = np.zeros(2)
            start = np.array([centroid[0] + 60, -420.0, 420.0])
            near = np.array([centroid[0], centroid[1] - 30, 110.0])
            path = [start, near]
            for d in present:
                path.append(np.array([d.gt.impact[0], d.gt.impact[1] - 40, 90.0]))
            path += [near, start]
            self._hands.append(_HandEvent(t0, t0 + duration, path))
            n = max(1, len(present))
            for i, d in enumerate(present):
                d.gt.removed_at = t0 + duration * (0.3 + 0.4 * (i + 1) / n)
            return [d.gt.dart_id for d in present]

    def set_lighting(self, preset: str | Lighting, at: float | None = None, transition_s: float = 0.0) -> None:
        lighting = LIGHTING_PRESETS[preset] if isinstance(preset, str) else preset
        with self._lock:
            self._lighting_events.append(_LightingEvent(self.now() if at is None else at, lighting, transition_s))
            self._lighting_events.sort(key=lambda e: e.t)

    def pass_hand(self, at: float | None = None, duration: float = 1.0,
                  position: tuple[float, float] = (0.0, 0.0)) -> None:
        """A hand/arm moves in front of the board without touching any dart."""
        with self._lock:
            t0 = self.now() if at is None else at
            p = np.array([position[0], position[1], 160.0])
            path = [np.array([p[0] - 400, p[1] - 300, 500.0]), p, np.array([p[0] + 400, p[1] - 300, 500.0])]
            self._hands.append(_HandEvent(t0, t0 + duration, path))

    def reset(self) -> None:
        with self._lock:
            self._darts.clear()
            self._hands.clear()

    # ------------------------------------------------------------------ rendering
    def scene_at(self, t: float) -> tuple[list[DartInstance], list[Occluder], Lighting]:
        with self._lock:
            darts: list[DartInstance] = []
            for wd in self._darts:
                inst = self._dart_state(wd, t)
                if inst is not None:
                    darts.append(inst)
            occluders = list(self._persistent_occluders)
            for hand in self._hands:
                pos = hand.position(t)
                if pos is not None:
                    occluders.append(Occluder.hand(pos[:2], z=float(pos[2]), scale=hand.scale))
            lighting = self._lighting_at(t)
        return darts, occluders, lighting

    def _lighting_at(self, t: float) -> Lighting:
        events = [e for e in self._lighting_events if e.t <= t]
        current = events[-1]
        if current.transition_s > 0 and len(events) > 1 and t < current.t + current.transition_s:
            prev = events[-2].lighting
            f = (t - current.t) / current.transition_s
            return _blend_lighting(prev, current.lighting, f)
        return current.lighting

    def _dart_state(self, wd: _WorldDart, t: float) -> DartInstance | None:
        gt = wd.gt
        if gt.removed_at is not None and t >= gt.removed_at:
            return None
        dt = t - gt.landed_at
        base = wd.instance
        if dt < -FLIGHT_VISIBLE_S:
            return None
        if dt < 0:
            # In flight along its own axis, motion-blurred over the exposure time.
            impact3 = np.array([base.impact[0], base.impact[1], 0.0])
            poses = []
            for k in range(5):
                tk = t - EXPOSURE_S * k / 4
                dist = FLIGHT_SPEED_MM_S * max(gt.landed_at - tk, 0.0)
                poses.append((impact3 + base.axis * dist, base.axis))
            return DartInstance(impact=base.impact, axis=base.axis, style=base.style, roll_deg=base.roll_deg,
                                tip_position=poses[0][0], blur_poses=poses[1:], dart_id=base.dart_id)
        amp = wd.wobble_amp_deg * math.exp(-dt / wd.wobble_tau_s) * math.sin(2 * math.pi * wd.wobble_freq_hz * dt)
        axis = base.axis
        if abs(amp) > 1e-3:
            axis = _rotate(base.axis, np.cross(base.axis, wd.wobble_dir), math.radians(amp))
        return DartInstance(impact=base.impact, axis=axis, style=base.style, roll_deg=base.roll_deg,
                            embed_depth=base.embed_depth, dart_id=base.dart_id)

    def render(self, camera_id: str, t: float | None = None) -> np.ndarray:
        t = self.now() if t is None else t
        darts, occluders, lighting = self.scene_at(t)
        return self._renderers[camera_id].render(darts, occluders, lighting)


def _rotate(v: np.ndarray, axis: np.ndarray, angle: float) -> np.ndarray:
    k = axis / (np.linalg.norm(axis) + 1e-12)
    return v * math.cos(angle) + np.cross(k, v) * math.sin(angle) + k * (k @ v) * (1 - math.cos(angle))


def _blend_lighting(a: Lighting, b: Lighting, f: float) -> Lighting:
    f = min(max(f, 0.0), 1.0)
    mix = lambda x, y: x * (1 - f) + y * f  # noqa: E731
    return Lighting(
        gain=mix(a.gain, b.gain), ambient=mix(a.ambient, b.ambient), diffuse=mix(a.diffuse, b.diffuse),
        direction=mix(a.direction, b.direction), shadow_strength=mix(a.shadow_strength, b.shadow_strength),
        shadow_blur_mm=mix(a.shadow_blur_mm, b.shadow_blur_mm),
        gradient=(mix(a.gradient[0], b.gradient[0]), mix(a.gradient[1], b.gradient[1])),
        tint=tuple(mix(x, y) for x, y in zip(a.tint, b.tint)),  # type: ignore[arg-type]
    )
