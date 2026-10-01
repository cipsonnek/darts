"""Session recorder: saves every captured frame (asynchronously, bounded queue), engine
events and ground truth so that sessions can be replayed through the same pipeline."""

from __future__ import annotations

import json
import logging
import queue
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2

from vision.cameras.base import Frame
from vision.recording.format import camera_dir

log = logging.getLogger("vision.recording")

_SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")


class SessionRecorder:
    def __init__(self, root: Path, name: str | None = None, image_format: str = "jpg",
                 jpeg_quality: int = 95, max_queue: int = 256) -> None:
        name = name or datetime.now().strftime("session_%Y%m%d_%H%M%S")
        if not _SAFE_NAME.match(name):
            raise ValueError("recording name may only contain letters, digits, '_', '-', '.'")
        self.dir = Path(root) / name
        if self.dir.exists():
            raise FileExistsError(f"recording {name!r} already exists")
        self.dir.mkdir(parents=True)
        self.name = name
        self.image_format = image_format
        self.jpeg_quality = jpeg_quality
        self._queue: queue.Queue[Frame | None] = queue.Queue(maxsize=max_queue)
        self._index_files: dict[str, Any] = {}
        self._counts: dict[str, int] = {}
        self._dropped = 0
        self._events = open(self.dir / "events.jsonl", "a", encoding="utf-8")
        self._events_lock = threading.Lock()
        self._started = time.monotonic()
        self._first_ts: float | None = None
        self._last_ts: float | None = None
        self._metadata: dict[str, Any] = {"started_at": datetime.now(timezone.utc).isoformat(),
                                          "name": name}
        self._thread = threading.Thread(target=self._writer, name=f"recorder-{name}", daemon=True)
        self._thread.start()
        self.active = True

    def set_metadata(self, **meta: Any) -> None:
        self._metadata.update(meta)
        self._flush_metadata()

    def add_frame(self, frame: Frame) -> None:
        """Called from capture threads. Never blocks; drops (and counts) on overload."""
        if not self.active:
            return
        try:
            self._queue.put_nowait(frame)
        except queue.Full:
            self._dropped += 1

    def add_event(self, event: dict[str, Any]) -> None:
        if not self.active:
            return
        with self._events_lock:
            self._events.write(json.dumps(event, default=_json_default) + "\n")
            self._events.flush()

    def stop(self) -> dict[str, Any]:
        if not self.active:
            return self.summary()
        self.active = False
        self._queue.put(None)
        self._thread.join(timeout=30)
        for f in self._index_files.values():
            f.close()
        self._events.close()
        self._flush_metadata()
        log.info("recording stopped", extra={"recording": self.summary()})
        return self.summary()

    def summary(self) -> dict[str, Any]:
        return {"name": self.name, "path": str(self.dir), "frame_counts": dict(self._counts),
                "dropped_frames": self._dropped, "active": self.active,
                "duration_s": (self._last_ts - self._first_ts) if self._first_ts is not None and self._last_ts is not None else 0.0}

    def _flush_metadata(self) -> None:
        meta = dict(self._metadata)
        meta.update(frame_counts=dict(self._counts), dropped_frames=self._dropped,
                    duration_s=self.summary()["duration_s"], cameras=sorted(self._counts.keys()) or meta.get("cameras", []))
        (self.dir / "metadata.json").write_text(json.dumps(meta, indent=2, default=_json_default), encoding="utf-8")

    def _writer(self) -> None:
        while True:
            frame = self._queue.get()
            if frame is None:
                break
            try:
                self._write(frame)
            except Exception:  # noqa: BLE001 - a bad frame must not kill the recorder
                log.exception("failed to write frame", extra={"camera": frame.camera_id})

    def _write(self, frame: Frame) -> None:
        cdir = camera_dir(self.dir, frame.camera_id)
        if frame.camera_id not in self._index_files:
            cdir.mkdir(parents=True, exist_ok=True)
            self._index_files[frame.camera_id] = open(cdir / "frames.jsonl", "a", encoding="utf-8")
            self._counts[frame.camera_id] = 0
        n = self._counts[frame.camera_id] + 1
        fname = f"{n:06d}.{self.image_format}"
        params = [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality] if self.image_format == "jpg" else []
        cv2.imwrite(str(cdir / fname), frame.image, params)
        self._index_files[frame.camera_id].write(json.dumps(
            {"index": n, "timestamp": frame.timestamp, "file": fname, "source_index": frame.index}) + "\n")
        self._counts[frame.camera_id] = n
        if self._first_ts is None:
            self._first_ts = frame.timestamp
        self._last_ts = frame.timestamp


def _json_default(o: Any) -> Any:
    try:
        import numpy as np

        if isinstance(o, np.ndarray):
            return o.tolist()
        if isinstance(o, (np.floating, np.integer)):
            return o.item()
    except ImportError:  # pragma: no cover
        pass
    if hasattr(o, "to_dict"):
        return o.to_dict()
    return str(o)
