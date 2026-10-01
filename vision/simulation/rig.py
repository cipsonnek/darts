"""Synthetic camera rigs that mimic a ring-mounted 3-camera setup.

Cameras sit on a ring around the board, slightly in front of the board surface, and look
across the board at a shallow angle. Placement is deliberately imperfect (radius, height,
aim point and roll jitter) so that nothing in the pipeline can rely on an ideal geometry.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from vision.geometry.camera_model import CameraModel, default_intrinsics


@dataclass(frozen=True)
class RigCameraSpec:
    camera_id: str
    azimuth_deg: float  # clock angle around the board (0 = top / 20, 90 = right / 6)
    radius_mm: float = 340.0
    height_mm: float = 105.0  # distance in front of the board surface
    aim_offset_mm: tuple[float, float] = (0.0, 0.0)
    roll_deg: float = 0.0
    hfov_deg: float = 72.0
    width: int = 1280
    height: int = 720
    distortion: tuple[float, ...] = (-0.12, 0.05, 0.0005, -0.0004, 0.0)


def default_rig_specs(width: int = 1280, height: int = 720, jitter_seed: int | None = 3
                      ) -> list[RigCameraSpec]:
    rng = np.random.default_rng(jitter_seed) if jitter_seed is not None else None
    specs = []
    for i, az in enumerate((0.0, 120.0, 240.0)):
        j = (lambda s: float(rng.normal(0, s))) if rng is not None else (lambda s: 0.0)
        specs.append(RigCameraSpec(
            camera_id=f"cam{i + 1}",
            azimuth_deg=az + j(4.0),
            radius_mm=340.0 + j(12.0),
            height_mm=105.0 + j(8.0),
            aim_offset_mm=(j(10.0), j(10.0)),
            roll_deg=j(2.0),
            hfov_deg=72.0 + j(1.5),
            width=width,
            height=height,
        ))
    return specs


def build_camera(spec: RigCameraSpec) -> CameraModel:
    t = math.radians(spec.azimuth_deg)
    position = np.array([spec.radius_mm * math.sin(t), spec.radius_mm * math.cos(t), spec.height_mm])
    target = np.array([spec.aim_offset_mm[0], spec.aim_offset_mm[1], 0.0])
    K = default_intrinsics(spec.width, spec.height, spec.hfov_deg)
    # Principal point is never exactly centred on real sensors.
    K[0, 2] += 6.0
    K[1, 2] -= 4.0
    return CameraModel.look_at(position, target, K, (spec.width, spec.height),
                               dist=np.array(spec.distortion, dtype=np.float64),
                               roll_deg=spec.roll_deg, camera_id=spec.camera_id)


def default_rig(width: int = 1280, height: int = 720, jitter_seed: int | None = 3
                ) -> dict[str, CameraModel]:
    return {s.camera_id: build_camera(s) for s in default_rig_specs(width, height, jitter_seed)}
