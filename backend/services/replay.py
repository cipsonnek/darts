"""Offline replay of a recorded session through a fresh engine, and evaluation against the
session's ground truth (simulator truth, or impacts annotated in the web UI)."""

from __future__ import annotations

import heapq
import math
from pathlib import Path
from typing import Any, Iterator

import cv2
import numpy as np

from vision.cameras.base import Frame
from vision.config import VisionConfig
from vision.engine import VisionEngine
from vision.events import EventType, VisionEvent
from vision.geometry.board import BoardGeometry
from vision.geometry.camera_model import CameraModel
from vision.recording.format import camera_dir, read_frame_index, read_ground_truth, read_metadata


def iter_framesets(session: Path, cameras: list[str]) -> Iterator[dict[str, Frame]]:
    """Merge the cameras' frame streams by timestamp. A frameset is yielded each time every
    camera has delivered a new frame (the latest of each), like a complete live frameset."""
    streams = {cid: read_frame_index(session, cid) for cid in cameras}
    heap: list[tuple[float, str, int]] = []
    for cid, recs in streams.items():
        if recs:
            heapq.heappush(heap, (recs[0].timestamp, cid, 0))
    latest: dict[str, Frame] = {}
    fresh: set[str] = set()
    while heap:
        ts, cid, i = heapq.heappop(heap)
        rec = streams[cid][i]
        img = cv2.imread(str(camera_dir(session, cid) / rec.file), cv2.IMREAD_COLOR)
        if img is not None:
            latest[cid] = Frame(cid, img, rec.timestamp, rec.index)
            fresh.add(cid)
            if len(fresh) == len(cameras):
                yield dict(latest)
                fresh.clear()
        if i + 1 < len(streams[cid]):
            heapq.heappush(heap, (streams[cid][i + 1].timestamp, cid, i + 1))


def replay_session(session: Path, cfg: VisionConfig | None = None) -> tuple[list[VisionEvent], dict]:
    meta = read_metadata(session)
    if cfg is None:
        cfg = VisionConfig.model_validate(meta["vision_config"]) if meta.get("vision_config") else VisionConfig()
    cameras = list(meta.get("cameras", []))
    models: dict[str, CameraModel | None] = {}
    for cid in cameras:
        pose = (meta.get("calibration", {}).get(cid) or {}).get("pose")
        models[cid] = CameraModel.from_dict(pose) if pose and not pose.get("stale") else None
    engine = VisionEngine(cfg, models)
    events: list[VisionEvent] = []
    engine.subscribe(events.append)
    n = 0
    for fs in iter_framesets(session, cameras):
        engine.process_frameset(fs)
        n += 1
    return events, {"framesets": n, "engine": engine.stats.to_dict(), "cameras": cameras}


def evaluate_session(session: Path, cfg: VisionConfig | None = None, match_radius_mm: float = 25.0) -> dict[str, Any]:
    events, info = replay_session(session, cfg)
    gt = read_ground_truth(session)
    board = BoardGeometry()
    darts = [e for e in events if e.type == EventType.DART]
    out: dict[str, Any] = {"replay": info, "detections": [
        {"timestamp": e.timestamp, "label": e.data["score"]["label"], "x_mm": e.data["impact"]["x_mm"],
         "y_mm": e.data["impact"]["y_mm"], "uncertain": e.data["uncertain"],
         "confidence": e.data["confidence"]["overall"]} for e in darts]}
    if not gt:
        out["metrics"] = None
        out["note"] = "no ground truth in this recording (annotate impacts in the developer UI)"
        return out
    used: set[int] = set()
    rows = []
    for g in gt:
        p = np.asarray(g["impact_mm"], float)
        t = g.get("frame_timestamp") or g.get("landed_at")
        best, best_d = None, math.inf
        for i, e in enumerate(darts):
            if i in used:
                continue
            if t is not None and not (t - 15.0 <= e.timestamp <= t + 15.0):
                continue
            d = math.hypot(e.data["impact"]["x_mm"] - p[0], e.data["impact"]["y_mm"] - p[1])
            if d < best_d:
                best, best_d = i, d
        true_label = board.score(*p).label
        if best is None or best_d > match_radius_mm:
            rows.append({"gt": true_label, "detected": False})
            continue
        used.add(best)
        e = darts[best]
        rows.append({"gt": true_label, "detected": True, "pred": e.data["score"]["label"], "error_mm": best_d,
                     "uncertain": e.data["uncertain"]})
    det = [r for r in rows if r["detected"]]
    errs = np.array([r["error_mm"] for r in det]) if det else np.array([])
    out["metrics"] = {
        "darts": len(rows), "detected": len(det), "missed": len(rows) - len(det),
        "false_positives": len(darts) - len(used),
        "score_accuracy": round(sum(r.get("pred") == r["gt"] for r in rows) / len(rows), 4) if rows else None,
        "impact_error_mm": None if errs.size == 0 else {
            "mean": round(float(errs.mean()), 3), "median": round(float(np.median(errs)), 3),
            "p95": round(float(np.percentile(errs, 95)), 3), "max": round(float(errs.max()), 3)},
    }
    out["rows"] = rows
    return out
