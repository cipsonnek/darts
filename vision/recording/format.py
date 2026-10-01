"""On-disk format of a recorded session.

```
recordings/<session>/
    metadata.json          cameras, config snapshot, calibration snapshot, start time
    camera_<id>/
        frames.jsonl       one line per frame: {"index", "timestamp", "file"}
        000001.jpg ...
    events.jsonl           engine events (detections, removals, state changes)
    ground_truth.json      annotated or simulated true impact points
```
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator


@dataclass
class FrameRecord:
    index: int
    timestamp: float
    file: str


def camera_dir(session_dir: Path, camera_id: str) -> Path:
    return session_dir / f"camera_{camera_id}"


def read_metadata(session_dir: Path) -> dict[str, Any]:
    path = session_dir / "metadata.json"
    if not path.exists():
        raise FileNotFoundError(f"{session_dir} is not a recording (no metadata.json)")
    return json.loads(path.read_text(encoding="utf-8"))


def read_frame_index(session_dir: Path, camera_id: str) -> list[FrameRecord]:
    path = camera_dir(session_dir, camera_id) / "frames.jsonl"
    records = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                d = json.loads(line)
                records.append(FrameRecord(int(d["index"]), float(d["timestamp"]), d["file"]))
    return records


def iter_events(session_dir: Path) -> Iterator[dict[str, Any]]:
    path = session_dir / "events.jsonl"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                yield json.loads(line)


def read_ground_truth(session_dir: Path) -> list[dict[str, Any]]:
    path = session_dir / "ground_truth.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8")).get("darts", [])


def write_ground_truth(session_dir: Path, darts: list[dict[str, Any]]) -> None:
    (session_dir / "ground_truth.json").write_text(json.dumps({"darts": darts}, indent=2), encoding="utf-8")


def list_sessions(root: Path) -> list[dict[str, Any]]:
    out = []
    if not root.exists():
        return out
    for d in sorted(root.iterdir(), reverse=True):
        if (d / "metadata.json").exists():
            try:
                meta = read_metadata(d)
            except (OSError, json.JSONDecodeError):
                continue
            out.append({"name": d.name, "path": str(d), **{k: meta.get(k) for k in
                        ("started_at", "cameras", "frame_counts", "duration_s", "synthetic", "notes")}})
    return out
