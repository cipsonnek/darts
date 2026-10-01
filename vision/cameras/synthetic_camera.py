"""Camera backed by :class:`vision.simulation.world.SimulatedWorld` (developer simulator).

Frames are rendered on demand at the configured FPS from the shared world, so the real
detection pipeline runs unchanged. Reported with ``kind = "synthetic"`` everywhere.
"""

from __future__ import annotations

import time

from vision.cameras.base import Camera, CameraError, Frame
from vision.config import CameraConfig
from vision.simulation.world import SimulatedWorld


class SyntheticCamera(Camera):
    kind = "synthetic"

    def __init__(self, config: CameraConfig, world: SimulatedWorld) -> None:
        super().__init__(config)
        if config.id not in world.cameras:
            raise CameraError(f"simulated world has no camera {config.id!r}")
        self.world = world
        self._open = False
        self._next_t = 0.0

    def open(self) -> None:
        self._open = True
        self._next_t = self.world.now()

    def read(self) -> Frame | None:
        if not self._open:
            raise CameraError(f"{self.camera_id}: not open")
        period = 1.0 / self.config.fps
        now = self.world.now()
        if now < self._next_t:
            time.sleep(self._next_t - now)
        t = self.world.now()
        self._next_t = max(self._next_t + period, t)
        image = self.world.render(self.camera_id, t)
        return Frame(self.camera_id, image, t, self._next_index(), meta={"synthetic": True})

    def close(self) -> None:
        self._open = False

    @property
    def is_open(self) -> bool:
        return self._open

    def info(self) -> dict:
        info = super().info()
        info["synthetic"] = True
        return info
