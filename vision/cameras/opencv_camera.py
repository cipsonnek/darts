"""USB/UVC and network (RTSP/HTTP) cameras through OpenCV's VideoCapture."""

from __future__ import annotations

import logging
import platform
import threading
import time
from typing import Any

import cv2

from vision.cameras.base import Camera, CameraError, Frame
from vision.config import CameraConfig

log = logging.getLogger("vision.cameras")

_APIS = {
    "auto": cv2.CAP_ANY,
    "dshow": cv2.CAP_DSHOW,
    "msmf": cv2.CAP_MSMF,
    "v4l2": cv2.CAP_V4L2,
    "gstreamer": cv2.CAP_GSTREAMER,
    "ffmpeg": cv2.CAP_FFMPEG,
}


def default_api() -> int:
    system = platform.system()
    if system == "Windows":
        return cv2.CAP_DSHOW
    if system == "Linux":
        return cv2.CAP_V4L2
    return cv2.CAP_ANY


class OpenCVCamera(Camera):
    kind = "opencv"

    def __init__(self, config: CameraConfig) -> None:
        super().__init__(config)
        self._cap: cv2.VideoCapture | None = None
        self._lock = threading.Lock()

    def _target(self) -> tuple[int | str, int]:
        src = self.config.source
        api = _APIS[src.api] if src.api != "auto" else default_api()
        if src.type == "rtsp":
            if not src.url:
                raise CameraError(f"{self.camera_id}: rtsp source needs 'url'")
            return src.url, (cv2.CAP_FFMPEG if src.api == "auto" else api)
        dev = src.device
        if dev is None:
            raise CameraError(f"{self.camera_id}: opencv source needs 'device'")
        if isinstance(dev, str) and dev.isdigit():
            dev = int(dev)
        return dev, api

    def open(self) -> None:
        target, api = self._target()
        cap = cv2.VideoCapture(target, api)
        if not cap.isOpened():
            cap.release()
            raise CameraError(f"{self.camera_id}: cannot open {target!r}")
        cfg = self.config
        if cfg.source.fourcc and cfg.source.type == "opencv":
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*cfg.source.fourcc))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg.height)
        cap.set(cv2.CAP_PROP_FPS, cfg.fps)
        # Keep the driver queue short so we always process a recent frame.
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        with self._lock:
            self._cap = cap
        self.set_controls(auto_exposure=cfg.auto_exposure, exposure=cfg.exposure,
                          gain=cfg.gain, white_balance=cfg.white_balance)
        log.info("camera opened", extra={"camera": self.camera_id, "target": str(target),
                                         "actual": self.get_controls()})

    def read(self) -> Frame | None:
        cap = self._cap
        if cap is None:
            raise CameraError(f"{self.camera_id}: not open")
        ok, image = cap.read()
        ts = time.monotonic()
        if not ok or image is None:
            return None
        if self.config.rotate_180:
            image = cv2.rotate(image, cv2.ROTATE_180)
        return Frame(self.camera_id, image, ts, self._next_index())

    def close(self) -> None:
        with self._lock:
            if self._cap is not None:
                self._cap.release()
                self._cap = None

    @property
    def is_open(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    def set_controls(self, **controls: Any) -> dict[str, Any]:
        cap = self._cap
        if cap is None:
            return {}
        windows = platform.system() == "Windows"
        if "auto_exposure" in controls and controls["auto_exposure"] is not None:
            auto = bool(controls["auto_exposure"])
            # DirectShow: 0.75 = auto, 0.25 = manual. V4L2: 3 = aperture priority, 1 = manual.
            cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, (0.75 if auto else 0.25) if windows else (3 if auto else 1))
        if controls.get("exposure") is not None:
            cap.set(cv2.CAP_PROP_EXPOSURE, float(controls["exposure"]))
        if controls.get("gain") is not None:
            cap.set(cv2.CAP_PROP_GAIN, float(controls["gain"]))
        if controls.get("white_balance") is not None:
            cap.set(cv2.CAP_PROP_AUTO_WB, 0)
            cap.set(cv2.CAP_PROP_WB_TEMPERATURE, float(controls["white_balance"]))
        return self.get_controls()

    def get_controls(self) -> dict[str, Any]:
        cap = self._cap
        if cap is None:
            return {}
        return {
            "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            "fps": float(cap.get(cv2.CAP_PROP_FPS)),
            "exposure": float(cap.get(cv2.CAP_PROP_EXPOSURE)),
            "gain": float(cap.get(cv2.CAP_PROP_GAIN)),
            "auto_exposure": float(cap.get(cv2.CAP_PROP_AUTO_EXPOSURE)),
            "backend": cap.getBackendName(),
        }


def probe_devices(max_index: int = 8, api: str = "auto") -> list[dict[str, Any]]:
    """Enumerate capture devices by index and report whether they deliver frames, plus a
    simple "looks real" heuristic (virtual cameras often deliver flat/static images)."""
    results = []
    cv_api = _APIS[api] if api != "auto" else default_api()
    for idx in range(max_index):
        cap = cv2.VideoCapture(idx, cv_api)
        if not cap.isOpened():
            cap.release()
            continue
        frames = []
        for _ in range(6):
            ok, img = cap.read()
            if ok and img is not None:
                frames.append(img)
        entry: dict[str, Any] = {"index": idx, "opened": True, "frames": len(frames)}
        if frames:
            img = frames[-1]
            entry["width"], entry["height"] = img.shape[1], img.shape[0]
            entry["mean"] = float(img.mean())
            entry["std"] = float(img.std())
            entry["temporal_change"] = float(cv2.absdiff(frames[0], frames[-1]).mean()) if len(frames) > 1 else 0.0
            entry["likely_virtual_or_blank"] = entry["std"] < 3.0
        entry["backend"] = cap.getBackendName()
        cap.release()
        results.append(entry)
    return results
