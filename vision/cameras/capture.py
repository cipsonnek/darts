"""One capture thread per camera.

Each worker keeps only the most recent frame (plus a short history ring) — never an
unbounded queue — so a slow consumer can never build up latency. It measures FPS, frame
intervals, corrupted frames and reconnects, and reopens the camera with exponential
back-off after failures."""

from __future__ import annotations

import collections
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from vision.cameras.base import Camera, CameraError, Frame, validate_frame

log = logging.getLogger("vision.cameras")

_BACKOFF = (0.5, 1.0, 2.0, 5.0, 10.0)
_READ_TIMEOUT_S = 3.0


@dataclass
class CameraHealth:
    camera_id: str
    kind: str
    state: str = "stopped"  # stopped | connecting | streaming | error
    connected: bool = False
    fps: float = 0.0
    target_fps: float = 0.0
    frames_total: int = 0
    frames_corrupted: int = 0
    reconnects: int = 0
    last_error: str | None = None
    last_frame_ts: float | None = None
    frame_interval_jitter_ms: float = 0.0
    width: int = 0
    height: int = 0
    brightness: float = 0.0
    contrast: float = 0.0
    saturated_fraction: float = 0.0
    dark_fraction: float = 0.0
    sharpness: float = 0.0
    controls: dict = field(default_factory=dict)

    def to_dict(self, now: float | None = None) -> dict:
        now = time.monotonic() if now is None else now
        d = self.__dict__.copy()
        d["last_frame_age_ms"] = None if self.last_frame_ts is None else max(0.0, (now - self.last_frame_ts) * 1000)
        d["low_fps"] = self.connected and self.target_fps > 0 and self.fps < 0.6 * self.target_fps
        return d


FrameListener = Callable[[Frame], None]


class CaptureWorker:
    def __init__(self, camera: Camera, history: int = 8) -> None:
        self.camera = camera
        self.health = CameraHealth(camera.camera_id, camera.kind, target_fps=camera.config.fps)
        self._latest: Frame | None = None
        self._history: collections.deque[Frame] = collections.deque(maxlen=history)
        self._lock = threading.Lock()
        self._new_frame = threading.Condition(self._lock)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._listeners: list[FrameListener] = []
        self._intervals: collections.deque[float] = collections.deque(maxlen=60)
        self._quality_every = 15

    # ------------------------------------------------------------------ control
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name=f"capture-{self.camera.camera_id}", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        with self._new_frame:
            self._new_frame.notify_all()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        try:
            self.camera.close()
        except Exception:  # noqa: BLE001
            pass
        self.health.state = "stopped"
        self.health.connected = False

    def add_listener(self, fn: FrameListener) -> None:
        self._listeners.append(fn)

    def remove_listener(self, fn: FrameListener) -> None:
        if fn in self._listeners:
            self._listeners.remove(fn)

    # ------------------------------------------------------------------ access
    def latest(self) -> Frame | None:
        with self._lock:
            return self._latest

    def history(self) -> list[Frame]:
        with self._lock:
            return list(self._history)

    def wait_for_frame(self, after_index: int, timeout: float = 1.0) -> Frame | None:
        with self._new_frame:
            self._new_frame.wait_for(lambda: (self._latest is not None and self._latest.index > after_index)
                                     or self._stop.is_set(), timeout=timeout)
            return self._latest

    # ------------------------------------------------------------------ loop
    def _run(self) -> None:
        attempt = 0
        while not self._stop.is_set():
            self.health.state = "connecting"
            try:
                self.camera.open()
                self.health.connected = True
                self.health.state = "streaming"
                self.health.last_error = None
                self.health.controls = self.camera.get_controls()
                attempt = 0
                self._read_loop()
            except CameraError as exc:
                self._fail(str(exc))
            except Exception as exc:  # noqa: BLE001 - reconnect boundary
                log.exception("capture crashed", extra={"camera": self.camera.camera_id})
                self._fail(f"{type(exc).__name__}: {exc}")
            finally:
                try:
                    self.camera.close()
                except Exception:  # noqa: BLE001
                    pass
            if self._stop.is_set():
                break
            delay = _BACKOFF[min(attempt, len(_BACKOFF) - 1)]
            attempt += 1
            self.health.reconnects += 1
            self._stop.wait(delay)

    def _fail(self, message: str) -> None:
        self.health.connected = False
        self.health.state = "error"
        self.health.last_error = message
        log.warning("camera failure", extra={"camera": self.camera.camera_id, "error": message})

    def _read_loop(self) -> None:
        last_ok = time.monotonic()
        fps_window: collections.deque[float] = collections.deque(maxlen=30)
        expected = (self.camera.config.width, self.camera.config.height) if self.camera.kind == "synthetic" else None
        while not self._stop.is_set():
            frame = self.camera.read()
            now = time.monotonic()
            if frame is None:
                if now - last_ok > _READ_TIMEOUT_S:
                    raise CameraError("no frames received (timeout)")
                time.sleep(0.005)
                continue
            reason = validate_frame(frame.image, expected)
            if reason is not None:
                self.health.frames_corrupted += 1
                if now - last_ok > _READ_TIMEOUT_S:
                    raise CameraError(f"only corrupted frames ({reason})")
                continue
            last_ok = now
            with self._new_frame:
                prev = self._latest
                self._latest = frame
                self._history.append(frame)
                self._new_frame.notify_all()
            h = self.health
            h.frames_total += 1
            h.last_frame_ts = now
            h.height, h.width = frame.image.shape[:2]
            fps_window.append(now)
            if len(fps_window) >= 2:
                h.fps = (len(fps_window) - 1) / max(1e-6, fps_window[-1] - fps_window[0])
            if prev is not None:
                self._intervals.append(frame.timestamp - prev.timestamp)
                if len(self._intervals) > 5:
                    h.frame_interval_jitter_ms = float(np.std(self._intervals) * 1000)
            if h.frames_total % self._quality_every == 1:
                _update_quality(h, frame.image)
            for listener in list(self._listeners):
                try:
                    listener(frame)
                except Exception:  # noqa: BLE001 - listeners must not break capture
                    log.exception("frame listener failed", extra={"camera": self.camera.camera_id})


def _update_quality(h: CameraHealth, image: np.ndarray) -> None:
    import cv2

    small = cv2.resize(image, (160, 90), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    h.brightness = float(gray.mean())
    h.contrast = float(gray.std())
    h.saturated_fraction = float((gray >= 250).mean())
    h.dark_fraction = float((gray <= 8).mean())
    full_gray = cv2.cvtColor(image[::2, ::2], cv2.COLOR_BGR2GRAY)
    h.sharpness = float(cv2.Laplacian(full_gray, cv2.CV_32F).var())
