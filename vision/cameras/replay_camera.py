"""Plays back a recorded session (see vision/recording/format.py) as a live camera."""

from __future__ import annotations

import time
from pathlib import Path

import cv2

from vision.cameras.base import Camera, CameraError, Frame
from vision.config import CameraConfig
from vision.recording.format import camera_dir, read_frame_index


class ReplayCamera(Camera):
    """Paces frames by their recorded timestamps (``realtime``) and reports timestamps on the
    live clock, so the engine behaves exactly as with the original cameras. With
    ``loop=True`` the recording restarts after the last frame."""

    kind = "replay"

    def __init__(self, config: CameraConfig, realtime: bool = True, loop: bool = False,
                 camera_id_in_recording: str | None = None, speed: float = 1.0) -> None:
        super().__init__(config)
        if not config.source.path:
            raise CameraError(f"{config.id}: replay source needs 'path'")
        self.session_dir = Path(config.source.path)
        self.recorded_id = camera_id_in_recording or config.id
        self.realtime = realtime
        self.loop = loop
        self.speed = speed
        self._records = []
        self._pos = 0
        self._open = False
        self._t0_wall = 0.0
        self._t0_rec = 0.0

    def open(self) -> None:
        self._records = read_frame_index(self.session_dir, self.recorded_id)
        if not self._records:
            raise CameraError(f"{self.camera_id}: no frames for {self.recorded_id!r} in {self.session_dir}")
        self._pos = 0
        self._open = True
        self._t0_wall = time.monotonic()
        self._t0_rec = self._records[0].timestamp

    def read(self) -> Frame | None:
        if not self._open:
            raise CameraError(f"{self.camera_id}: not open")
        if self._pos >= len(self._records):
            if not self.loop:
                raise CameraError(f"{self.camera_id}: end of recording")
            self._pos = 0
            self._t0_wall = time.monotonic()
        rec = self._records[self._pos]
        self._pos += 1
        target = self._t0_wall + (rec.timestamp - self._t0_rec) / self.speed
        if self.realtime:
            delay = target - time.monotonic()
            if delay > 0:
                time.sleep(delay)
        image = cv2.imread(str(camera_dir(self.session_dir, self.recorded_id) / rec.file), cv2.IMREAD_COLOR)
        if image is None:
            return None
        ts = time.monotonic() if self.realtime else rec.timestamp
        return Frame(self.camera_id, image, ts, self._next_index(),
                     meta={"replay": True, "recorded_timestamp": rec.timestamp, "recorded_index": rec.index})

    def close(self) -> None:
        self._open = False

    @property
    def is_open(self) -> bool:
        return self._open

    @property
    def progress(self) -> float:
        return self._pos / max(1, len(self._records))
