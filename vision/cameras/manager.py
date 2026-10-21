"""Creates cameras from configuration, runs their capture workers and assembles
time-aligned frame sets."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

from vision.cameras.base import Camera, CameraError, Frame
from vision.cameras.capture import CaptureWorker, FrameListener
from vision.cameras.opencv_camera import OpenCVCamera
from vision.cameras.replay_camera import ReplayCamera
from vision.cameras.synthetic_camera import SyntheticCamera
from vision.config import CameraConfig

log = logging.getLogger("vision.cameras")


@dataclass
class FrameSet:
    frames: dict[str, Frame]

    @property
    def timestamp(self) -> float:
        return max(f.timestamp for f in self.frames.values())

    @property
    def sync_spread_ms(self) -> float:
        """Max − min capture timestamp across cameras: how far apart the views are in time."""
        if len(self.frames) < 2:
            return 0.0
        ts = [f.timestamp for f in self.frames.values()]
        return (max(ts) - min(ts)) * 1000.0


def create_camera(config: CameraConfig, world=None) -> Camera:
    t = config.source.type
    if t in ("opencv", "rtsp"):
        return OpenCVCamera(config)
    if t == "replay":
        return ReplayCamera(config, realtime=True, loop=True)
    if t == "synthetic":
        if world is None:
            raise CameraError(f"{config.id}: synthetic camera needs a simulated world")
        return SyntheticCamera(config, world)
    raise CameraError(f"unknown camera source type {t!r}")


class CameraManager:
    def __init__(self, configs: list[CameraConfig], world=None) -> None:
        self._lock = threading.RLock()
        self._configs = {c.id: c for c in configs}
        self._world = world
        self._workers: dict[str, CaptureWorker] = {}
        self._listeners: list[FrameListener] = []
        for cfg in configs:
            if cfg.enabled:
                self._workers[cfg.id] = CaptureWorker(create_camera(cfg, world))

    @property
    def camera_ids(self) -> list[str]:
        return list(self._workers.keys())

    @property
    def configs(self) -> dict[str, CameraConfig]:
        return dict(self._configs)

    @property
    def world(self):
        return self._world

    def start(self) -> None:
        for w in self._workers.values():
            w.start()

    def stop(self) -> None:
        for w in self._workers.values():
            w.stop()

    def worker(self, camera_id: str) -> CaptureWorker:
        try:
            return self._workers[camera_id]
        except KeyError as exc:
            raise KeyError(f"unknown or disabled camera {camera_id!r}") from exc

    def latest(self, camera_id: str) -> Frame | None:
        return self.worker(camera_id).latest()

    def frameset(self) -> FrameSet:
        frames = {cid: f for cid, w in self._workers.items() if (f := w.latest()) is not None}
        return FrameSet(frames)

    def health(self) -> list[dict]:
        return [w.health.to_dict() for w in self._workers.values()]

    def add_listener(self, fn: FrameListener) -> None:
        for w in self._workers.values():
            w.add_listener(fn)
        self._listeners.append(fn)

    def remove_listener(self, fn: FrameListener) -> None:
        for w in self._workers.values():
            w.remove_listener(fn)
        if fn in self._listeners:
            self._listeners.remove(fn)

    def reconfigure(self, config: CameraConfig) -> None:
        """Replace a camera's configuration and restart its worker."""
        self.reconfigure_many([config])

    def reconfigure_many(self, configs: list[CameraConfig]) -> None:
        """Restart several cameras: all are stopped before any is started, so cameras that
        swap devices never try to open a device the other one still holds."""
        with self._lock:
            for config in configs:
                old = self._workers.pop(config.id, None)
                if old is not None:
                    old.stop()
            for config in configs:
                self._configs[config.id] = config
                if config.enabled:
                    worker = CaptureWorker(create_camera(config, self._world))
                    for fn in self._listeners:
                        worker.add_listener(fn)
                    self._workers[config.id] = worker
                    worker.start()

    def apply_controls(self, camera_id: str, **controls) -> dict:
        worker = self.worker(camera_id)
        applied = worker.camera.set_controls(**controls)
        worker.health.controls = applied or worker.camera.get_controls()
        return worker.health.controls
