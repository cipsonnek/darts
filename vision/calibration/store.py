"""Persistent per-camera calibration profiles (JSON, one file per camera, with history)."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vision.calibration.intrinsics import IntrinsicsResult
from vision.geometry.camera_model import CameraModel

_HISTORY = 20


class CalibrationStore:
    def __init__(self, directory: Path) -> None:
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _path(self, camera_id: str) -> Path:
        if not camera_id or not all(c.isalnum() or c in "_-" for c in camera_id):
            raise ValueError("invalid camera id")
        return self.dir / f"{camera_id}.json"

    def load(self, camera_id: str) -> dict[str, Any]:
        path = self._path(camera_id)
        if not path.exists():
            return {"camera_id": camera_id, "intrinsics": None, "pose": None, "history": []}
        return json.loads(path.read_text(encoding="utf-8"))

    def _save(self, data: dict[str, Any]) -> None:
        path = self._path(data["camera_id"])
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(path)

    def save_intrinsics(self, camera_id: str, result: IntrinsicsResult) -> dict[str, Any]:
        with self._lock:
            data = self.load(camera_id)
            self._push_history(data, "intrinsics")
            data["intrinsics"] = result.to_dict()
            # A pose solved with different intrinsics is no longer valid.
            if data.get("pose") is not None:
                data["pose"]["stale"] = True
            self._save(data)
            return data

    def save_pose(self, camera_id: str, camera: CameraModel, method: str, metrics: dict, grade: str,
                  intrinsics_source: str) -> dict[str, Any]:
        with self._lock:
            data = self.load(camera_id)
            self._push_history(data, "pose")
            data["pose"] = {
                **camera.to_dict(),
                "method": method,
                "metrics": metrics,
                "grade": grade,
                "intrinsics_source": intrinsics_source,
                "calibrated_at": datetime.now(timezone.utc).isoformat(),
                "stale": False,
            }
            self._save(data)
            return data

    def clear(self, camera_id: str) -> None:
        with self._lock:
            data = self.load(camera_id)
            self._push_history(data, "pose")
            data["pose"] = None
            self._save(data)

    def camera_model(self, camera_id: str) -> CameraModel | None:
        data = self.load(camera_id)
        pose = data.get("pose")
        if not pose or pose.get("stale"):
            return None
        return CameraModel.from_dict(pose)

    def intrinsics(self, camera_id: str) -> IntrinsicsResult | None:
        d = self.load(camera_id).get("intrinsics")
        return IntrinsicsResult.from_dict(d) if d else None

    @staticmethod
    def _push_history(data: dict[str, Any], key: str) -> None:
        if data.get(key) is not None:
            data.setdefault("history", []).append({"kind": key, "archived_at": datetime.now(timezone.utc).isoformat(),
                                                   "value": data[key]})
            data["history"] = data["history"][-_HISTORY:]
