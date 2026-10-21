"""The vision engine: turns synchronised camera frames into dart events.

Temporal model (docs/VISION.md §6)::

    IDLE ──motion──▶ MOTION ──all cameras still for settle_time──▶ analyse settled scene
      ▲                                                               │
      └──────────── new darts / removals / nothing ◀──────────────────┤
                                       large non-dart change ─────────▶ OBSTRUCTED (wait)

The settled scene is compared with the previous settled scene (``reference``) — existing
darts cancel out — and with the empty board (``empty``) to tell added from removed pixels.

The engine is driven by frame timestamps, never by wall-clock time, so live cameras,
recordings and simulations behave identically and deterministically.
"""

from __future__ import annotations

import logging
import math
import threading
import time
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

import cv2
import numpy as np

from vision.calibration.refine import EdgeAligner
from vision.calibration.validation import ValidationResult, validate_pose
from vision.cameras.base import Frame
from vision.config import VisionConfig
from vision.dart_detection.candidates import DartCandidate, extract_candidates
from vision.dart_detection.change import ChangeResult, compute_change, occupancy
from vision.events import EventType, VisionEvent
from vision.fusion.fusion import FusedDart, fuse
from vision.geometry.board import BoardGeometry
from vision.geometry.camera_model import CameraModel
from vision.scoring.probability import score_distribution
from vision.tracking.board_state import BoardState, CameraFootprint, KnownDart
from vision.tracking.motion import MotionDetector

log = logging.getLogger("vision.engine")

Subscriber = Callable[[VisionEvent], None]


class EngineState(str, Enum):
    STARTING = "starting"
    IDLE = "idle"
    MOTION = "motion"
    PROCESSING = "processing"
    OBSTRUCTED = "obstructed"
    PAUSED = "paused"
    STOPPED = "stopped"


@dataclass
class CameraContext:
    camera_id: str
    model: CameraModel | None
    frame_size: tuple[int, int] | None = None
    roi: np.ndarray | None = None
    motion: MotionDetector | None = None
    reference: np.ndarray | None = None
    empty: np.ndarray | None = None
    last_frame: Frame | None = None
    last_change: ChangeResult | None = None
    last_candidates: list[DartCandidate] = field(default_factory=list)
    last_motion_fraction: float = 0.0
    validation: ValidationResult | None = None
    # Frames since the scene became still (averaged for analysis).
    still_frames: deque = field(default_factory=deque)


@dataclass
class EngineStats:
    framesets: int = 0
    settles: int = 0
    darts: int = 0
    uncertain: int = 0
    obstructions: int = 0
    unrecognized: int = 0
    processing_ms: deque = field(default_factory=lambda: deque(maxlen=200))
    tick_ms: deque = field(default_factory=lambda: deque(maxlen=200))
    sync_spread_ms: deque = field(default_factory=lambda: deque(maxlen=200))
    errors: int = 0

    def to_dict(self) -> dict:
        def summ(d):
            if not d:
                return None
            a = np.asarray(d, dtype=float)
            return {"mean": round(float(a.mean()), 2), "p95": round(float(np.percentile(a, 95)), 2),
                    "max": round(float(a.max()), 2)}
        return {"framesets": self.framesets, "settles": self.settles, "darts": self.darts,
                "uncertain": self.uncertain, "obstructions": self.obstructions,
                "unrecognized": self.unrecognized, "errors": self.errors,
                "processing_ms": summ(self.processing_ms), "tick_ms": summ(self.tick_ms),
                "sync_spread_ms": summ(self.sync_spread_ms)}


def board_roi(model: CameraModel, board: BoardGeometry, height_mm: float = 170.0) -> np.ndarray:
    """Image region where a dart in the board can appear: the board disk extruded to the
    height of a dart, projected into the image."""
    w, h = model.image_size
    r = board.config.board_radius_mm + 5.0
    pts = []
    for z in (0.0, height_mm * 0.5, height_mm):
        c = board.circle_points(r, 96)
        c[:, 2] = z
        ok = model.in_front(c)
        pts.append(model.project(c[ok]))
    allp = np.concatenate(pts)
    mask = np.zeros((h, w), dtype=np.uint8)
    if len(allp) >= 3:
        hull = cv2.convexHull(allp.astype(np.float32)).astype(np.int32)
        cv2.fillConvexPoly(mask, hull, 255)
    return mask


class VisionEngine:
    def __init__(self, config: VisionConfig, camera_models: dict[str, CameraModel | None]) -> None:
        self.config = config
        self.board = BoardGeometry(config.board)
        self.cameras: dict[str, CameraContext] = {cid: CameraContext(cid, m) for cid, m in camera_models.items()}
        self.state = EngineState.STARTING
        self.board_state = BoardState()
        self.stats = EngineStats()
        self._subs: list[Subscriber] = []
        self._lock = threading.RLock()
        self._last_motion_ts: float | None = None
        self._motion_start_ts: float | None = None
        self._still_since: float | None = None
        self._peak_motion = 0.0
        self._obstruction_reported = False
        self._last_ts = 0.0
        self._aligner: EdgeAligner | None = None
        self.last_detection: dict | None = None
        self._paused = False
        # live loop
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._manager = None
        self._last_indices: dict[str, int] = {}
        # Per-camera analysis runs in parallel (OpenCV/NumPy release the GIL).
        self._pool = ThreadPoolExecutor(max_workers=max(1, min(4, len(self.cameras))),
                                        thread_name_prefix="vision-cam")

    # ------------------------------------------------------------------ subscriptions
    def subscribe(self, fn: Subscriber) -> None:
        self._subs.append(fn)

    def unsubscribe(self, fn: Subscriber) -> None:
        if fn in self._subs:
            self._subs.remove(fn)

    def _emit(self, etype: str, ts: float, data: dict) -> VisionEvent:
        ev = VisionEvent(etype, ts, data)
        for fn in list(self._subs):
            try:
                fn(ev)
            except Exception:  # noqa: BLE001 - a subscriber must never break the engine
                log.exception("event subscriber failed")
        return ev

    def _set_state(self, new: EngineState, ts: float, events: list[VisionEvent]) -> None:
        if new != self.state:
            old = self.state
            self.state = new
            events.append(self._emit(EventType.STATE, ts, {"state": new.value, "previous": old.value}))

    # ------------------------------------------------------------------ configuration
    @property
    def calibrated_cameras(self) -> list[str]:
        return [c.camera_id for c in self.cameras.values() if c.model is not None]

    def set_camera_model(self, camera_id: str, model: CameraModel | None) -> None:
        with self._lock:
            ctx = self.cameras.setdefault(camera_id, CameraContext(camera_id, None))
            ctx.model = model
            ctx.roi = None
            ctx.motion = None
            ctx.validation = None

    def pause(self, paused: bool = True) -> None:
        self._paused = paused

    def reset_board(self, mark_empty: bool = True) -> list[KnownDart]:
        """Forget all known darts. With ``mark_empty`` the current view becomes the empty
        board reference (use when the board is actually empty)."""
        with self._lock:
            removed = self.board_state.clear()
            last = self._averaged({cid: c.last_frame for cid, c in self.cameras.items() if c.last_frame is not None})
            for cid, f in last.items():
                ctx = self.cameras[cid]
                ctx.reference = f.image.copy()
                if mark_empty:
                    ctx.empty = f.image.copy()
            self._set_state(EngineState.IDLE, self._last_ts, [])
            return removed

    def relabel_dart(self, dart_id: str, label: str) -> bool:
        """Record a user correction of a known dart's value (display only; the measured
        position is kept)."""
        with self._lock:
            for d in self.board_state.darts:
                if d.dart_id == dart_id:
                    d.label = label
                    return True
            return False

    def remove_dart(self, dart_id: str) -> bool:
        """Forget one known dart (e.g. a false detection deleted by the user)."""
        with self._lock:
            return bool(self.board_state.remove([dart_id]))

    # ------------------------------------------------------------------ core processing
    def _ensure_context(self, ctx: CameraContext, frame: Frame) -> None:
        size = (frame.image.shape[1], frame.image.shape[0])
        if ctx.frame_size != size or ctx.motion is None:
            ctx.frame_size = size
            if ctx.model is not None and ctx.model.image_size != size:
                sx = size[0] / ctx.model.image_size[0]
                sy = size[1] / ctx.model.image_size[1]
                ctx.model = ctx.model.scaled(sx, sy)
            ctx.roi = board_roi(ctx.model, self.board) if ctx.model is not None else None
            ctx.motion = MotionDetector(self.config.motion, ctx.roi, size)
            ctx.reference = None
        elif ctx.roi is None and ctx.model is not None:
            ctx.roi = board_roi(ctx.model, self.board)
            ctx.motion = MotionDetector(self.config.motion, ctx.roi, size)

    def process_frameset(self, frames: dict[str, Frame]) -> list[VisionEvent]:
        """Feed one set of (approximately simultaneous) frames. Returns emitted events."""
        events: list[VisionEvent] = []
        if not frames:
            return events
        t0 = time.perf_counter()
        with self._lock:
            ts = max(f.timestamp for f in frames.values())
            self._last_ts = ts
            self.stats.framesets += 1
            if len(frames) > 1:
                tss = [f.timestamp for f in frames.values()]
                self.stats.sync_spread_ms.append((max(tss) - min(tss)) * 1000.0)
            moving = False
            for cid, frame in frames.items():
                ctx = self.cameras.get(cid)
                if ctx is None:
                    ctx = self.cameras[cid] = CameraContext(cid, None)
                self._ensure_context(ctx, frame)
                ctx.last_frame = frame
                assert ctx.motion is not None
                sample = ctx.motion.update(frame.image)
                ctx.last_motion_fraction = sample.fraction
                moving |= sample.moving
            n_avg = self.config.motion.settle_average_frames
            for cid, frame in frames.items():
                still = self.cameras[cid].still_frames
                if moving:
                    still.clear()
                else:
                    still.append(frame.image)
                    while len(still) > n_avg:
                        still.popleft()
            if moving:
                self._last_motion_ts = ts
                self._still_since = None
                if self._motion_start_ts is None:
                    self._motion_start_ts = ts
                    self._peak_motion = 0.0
                self._peak_motion = max(self._peak_motion, max(c.last_motion_fraction for c in self.cameras.values()))
                if self.state in (EngineState.IDLE, EngineState.STARTING) and self._has_baseline():
                    self._set_state(EngineState.MOTION, ts, events)
            elif self._still_since is None:
                self._still_since = ts
            settled = self._still_since is not None and \
                (ts - self._still_since) * 1000.0 >= self.config.motion.settle_time_ms
            if self._paused:
                pass
            elif not self._has_baseline():
                if settled:
                    self._set_baseline(ts, events)
            elif settled and self.state in (EngineState.MOTION, EngineState.OBSTRUCTED):
                self._set_state(EngineState.PROCESSING, ts, events)
                tp = time.perf_counter()
                try:
                    self._analyse_settled(self._averaged(frames), ts, events)
                except Exception as exc:  # noqa: BLE001 - keep running; report
                    self.stats.errors += 1
                    log.exception("settled-scene analysis failed")
                    events.append(self._emit(EventType.ERROR, ts, {"error": f"{type(exc).__name__}: {exc}"}))
                    self._set_state(EngineState.IDLE, ts, events)
                self.stats.processing_ms.append((time.perf_counter() - tp) * 1000.0)
                self._motion_start_ts = None
            self.stats.tick_ms.append((time.perf_counter() - t0) * 1000.0)
        return events

    def _has_baseline(self) -> bool:
        return any(c.reference is not None for c in self.cameras.values() if c.model is not None) or \
            (not self.calibrated_cameras and any(c.reference is not None for c in self.cameras.values()))

    def _averaged(self, frames: dict[str, Frame]) -> dict[str, Frame]:
        """The settled frames, each replaced by the mean of its camera's still frames."""
        out = {}
        for cid, f in frames.items():
            still = self.cameras[cid].still_frames
            if len(still) < 2 or any(s.shape != f.image.shape for s in still):
                out[cid] = f
                continue
            acc = np.zeros(f.image.shape, np.float32)
            for s in still:
                acc += s
            img = np.clip(acc / len(still) + 0.5, 0, 255).astype(np.uint8)
            out[cid] = Frame(f.camera_id, img, f.timestamp, f.index, {**f.meta, "averaged": len(still)})
        return out

    def _set_baseline(self, ts: float, events: list[VisionEvent]) -> None:
        last = self._averaged({cid: c.last_frame for cid, c in self.cameras.items() if c.last_frame is not None})
        for cid, ctx in self.cameras.items():
            if cid not in last:
                continue
            ctx.reference = last[cid].image.copy()
            if self.config.tracking.assume_empty_on_start and ctx.empty is None:
                ctx.empty = last[cid].image.copy()
        events.append(self._emit(EventType.BASELINE, ts, {"cameras": [c.camera_id for c in self.cameras.values()
                                                                     if c.reference is not None]}))
        self._set_state(EngineState.IDLE, ts, events)

    def _analyse_settled(self, frames: dict[str, Frame], ts: float, events: list[VisionEvent]) -> None:
        self.stats.settles += 1
        cfg = self.config
        cams = {cid: ctx for cid, ctx in self.cameras.items()
                if ctx.model is not None and ctx.reference is not None and cid in frames}
        if not cams:
            self._refresh_references(frames)
            self._set_state(EngineState.IDLE, ts, events)
            return
        futures = {cid: self._pool.submit(compute_change, ctx.reference, frames[cid].image, ctx.roi,
                                          cfg.detection, ctx.empty)
                   for cid, ctx in cams.items()}
        changes: dict[str, ChangeResult] = {}
        for cid, fut in futures.items():
            changes[cid] = fut.result()
            cams[cid].last_change = changes[cid]

        # 1. Obstruction: something large (hand, body) is still in front of the board.
        obstructed = [cid for cid, ch in changes.items() if ch.added_fraction > cfg.detection.obstruction_area_fraction]
        if len(obstructed) >= max(1, math.ceil(len(cams) / 2)):
            if self._still_since is not None and ts - self._still_since >= cfg.tracking.obstruction_rebaseline_s:
                self._rebaseline(frames, cams, ts, events, obstructed)
                return
            self.stats.obstructions += 1
            if not self._obstruction_reported:
                events.append(self._emit(EventType.OBSTRUCTION, ts, {
                    "cameras": obstructed,
                    "added_fraction": {cid: round(changes[cid].added_fraction, 4) for cid in obstructed}}))
                self._obstruction_reported = True
            self._set_state(EngineState.OBSTRUCTED, ts, events)
            return
        self._obstruction_reported = False

        # 2. Removed darts (takeout).
        removed = self._detect_removed(frames, cams)
        if removed:
            gone = self.board_state.remove([d.dart_id for d in removed])
            clear = len(self.board_state) == 0
            events.append(self._emit(EventType.DARTS_REMOVED, ts, {
                "dart_ids": [d.dart_id for d in gone], "board_clear": clear,
                "remaining": [d.dart_id for d in self.board_state.darts]}))

        # 3. New darts. Not when this very scene is the takeout that emptied the board: the
        # hand was just in front of it, and a dart can only look "new" because it was in the
        # board when the empty reference was taken (start-up, reset) and has now been pulled.
        if removed and len(self.board_state) == 0:
            new_events = []
            log.info("takeout emptied the board: new-dart detection skipped for this scene")
        else:
            new_events = self._detect_new(frames, cams, changes, ts)
        events.extend(new_events)

        # 4. Nothing recognised but the scene changed.
        significant = [cid for cid, ch in changes.items()
                       if np.count_nonzero(ch.added) > cfg.detection.min_dart_pixels * 4]
        if not new_events and not removed:
            if significant:
                self.stats.unrecognized += 1
                events.append(self._emit(EventType.UNRECOGNIZED, ts, {
                    "cameras": significant,
                    "added_pixels": {cid: int(np.count_nonzero(changes[cid].added)) for cid in significant},
                    "candidates": {cid: len(self.cameras[cid].last_candidates) for cid in cams}}))
            else:
                events.append(self._emit(EventType.NO_CHANGE, ts, {
                    "peak_motion_fraction": round(self._peak_motion, 5),
                    "possible_bounce_out": self._peak_motion > cfg.motion.motion_area_fraction * 3}))

        self._refresh_references(frames)
        if len(self.board_state) == 0 and removed:
            self._refresh_empty(frames, cams)
            events.append(self._emit(EventType.BOARD_CLEAR, ts, {}))
        self._set_state(EngineState.IDLE, ts, events)

    def _rebaseline(self, frames: dict[str, Frame], cams: dict[str, CameraContext], ts: float,
                    events: list[VisionEvent], obstructed: list[str]) -> None:
        """The scene changed for good (lighting): start again from the current view. The
        empty-board reference is only replaced when no darts are known to be in the board."""
        self._refresh_references(frames)
        if len(self.board_state) == 0:
            for cid in cams:
                self.cameras[cid].empty = frames[cid].image.copy()
        self._obstruction_reported = False
        log.warning("scene changed while still (lighting?) - new reference adopted", extra={"cameras": obstructed})
        events.append(self._emit(EventType.BASELINE, ts, {
            "cameras": list(cams), "reason": "scene_changed", "empty_refreshed": len(self.board_state) == 0}))
        self._set_state(EngineState.IDLE, ts, events)

    def _refresh_references(self, frames: dict[str, Frame]) -> None:
        for cid, f in frames.items():
            ctx = self.cameras.get(cid)
            if ctx is not None:
                ctx.reference = f.image.copy()

    def _refresh_empty(self, frames: dict[str, Frame], cams: dict[str, CameraContext]) -> None:
        """After a confirmed takeout the board is empty: refresh the empty reference unless
        the view still differs from it substantially (then something is left on the board)."""
        for cid, ctx in cams.items():
            if ctx.empty is None:
                ctx.empty = frames[cid].image.copy()
                continue
            occ, _, _ = occupancy(frames[cid].image, ctx.empty, ctx.roi, self.config.detection)
            frac = np.count_nonzero(occ) / max(1, np.count_nonzero(ctx.roi))
            if frac < 0.002:
                ctx.empty = frames[cid].image.copy()

    def _detect_removed(self, frames: dict[str, Frame], cams: dict[str, CameraContext]) -> list[KnownDart]:
        if len(self.board_state) == 0:
            return []
        cfg = self.config
        occ_cache: dict[str, np.ndarray] = {}
        removed = []
        for dart in self.board_state.darts:
            votes, total = 0, 0
            for cid, fp in dart.footprints.items():
                ctx = cams.get(cid)
                if ctx is None or ctx.empty is None:
                    continue
                if cid not in occ_cache:
                    occ, bbox, _ = occupancy(frames[cid].image, ctx.empty, ctx.roi, cfg.detection)
                    full = np.zeros(frames[cid].image.shape[:2], np.uint8)
                    x0, y0, x1, y1 = bbox
                    full[y0:y1, x0:x1] = occ
                    occ_cache[cid] = full
                xs, ys = fp.pixel_coords()
                H, W = occ_cache[cid].shape
                ok = (xs >= 0) & (xs < W) & (ys >= 0) & (ys < H)
                if ok.sum() < 10:
                    continue
                still = occ_cache[cid][ys[ok], xs[ok]] > 0
                total += 1
                if 1.0 - still.mean() >= cfg.tracking.removal_pixel_fraction:
                    votes += 1
            if total > 0 and votes * 2 > total:
                removed.append(dart)
        return removed

    def _detect_new(self, frames: dict[str, Frame], cams: dict[str, CameraContext],
                    changes: dict[str, ChangeResult], ts: float) -> list[VisionEvent]:
        cfg = self.config
        cands: dict[str, list[DartCandidate]] = {}
        support: dict[str, np.ndarray] = {}
        occluders: dict[str, np.ndarray] = {}
        moved: list[tuple[KnownDart, str]] = []
        occ_masks = {cid: self.board_state.occluder_mask(cid, frames[cid].image.shape[:2]) for cid in cams}

        def _extract(cid: str) -> list[DartCandidate]:
            ch = changes[cid]
            x0, y0, x1, y1 = ch.bbox
            return extract_candidates(ch.added, ch.bbox, ch.diff, cams[cid].model, cfg.detection, cid,
                                      occluders=occ_masks[cid][y0:y1, x0:x1], roi=cams[cid].roi,
                                      dart_length_mm=cfg.detection.dart_length_mm)

        raw_by_cam = dict(zip(cams, self._pool.map(_extract, list(cams))))
        for cid, ctx in cams.items():
            ch = changes[cid]
            shape = frames[cid].image.shape[:2]
            occ_full = occ_masks[cid]
            raw = raw_by_cam[cid]
            keep = []
            for c in raw:
                known = self.board_state.matches_footprint(cid, c)
                if known is not None:
                    moved.append((known, cid))
                    continue
                keep.append(c)
            ctx.last_candidates = keep
            cands[cid] = keep
            support[cid] = ch.full_mask("changed", shape)
            occluders[cid] = occ_full
        models = {cid: ctx.model for cid, ctx in cams.items() if ctx.model is not None}
        fused = fuse(models, cands, cfg.fusion, max_tilt_deg=cfg.detection.max_dart_tilt_deg,
                     max_darts=3, support=support, occluders=occluders,
                     board_radius_mm=self.board.config.board_radius_mm)
        events: list[VisionEvent] = []
        for f in fused:
            if len(self.board_state) >= cfg.tracking.max_darts_on_board:
                break
            near, dist = self.board_state.nearest(f.impact)
            if near is not None and dist < cfg.tracking.duplicate_radius_mm and near.axis is not None \
                    and f.axis is not None and float(near.axis @ f.axis) > math.cos(math.radians(6)):
                # Same position and same 3D direction as a known dart: not a new dart.
                continue
            payload = self._dart_payload(f, frames, ts)
            dart = KnownDart(payload["dart_id"], f.impact.copy(), ts, payload["score"]["label"],
                             {o.camera_id: CameraFootprint.from_candidate(o.candidate) for o in f.observations},
                             axis=None if f.axis is None else f.axis.copy())
            self.board_state.add(dart)
            self.stats.darts += 1
            if payload["uncertain"]:
                self.stats.uncertain += 1
            self.last_detection = payload
            events.append(self._emit(EventType.DART, ts, payload))
        if moved and not events:
            ids = sorted({d.dart_id for d, _ in moved})
            events.append(self._emit(EventType.DART_MOVED, ts, {"dart_ids": ids}))
        return events

    def _dart_payload(self, f: FusedDart, frames: dict[str, Frame], ts: float) -> dict:
        cfg = self.config
        # Cameras disagreeing more than their modelled noise inflate the covariance by the
        # reduced chi-square of the line fit (no redundancy with two cameras: fixed factor).
        n_obs = len(f.observations)
        if n_obs >= 3:
            inflation = max(1.0, f.line_chi2 / (n_obs - 2))
        else:
            inflation = 1.7 if n_obs == 2 else 1.0
        cov = f.cov * inflation + np.eye(2) * cfg.fusion.model_sigma_mm ** 2
        dist = score_distribution(self.board, f.impact, cov, cfg.scoring.monte_carlo_samples, model_sigma_mm=0.0)
        top = dist[0]
        exact = self.board.score(*f.impact)
        sigma = float(math.sqrt(max(np.trace(cov), 0.0) / 2.0))
        # Detection confidence: is this a real dart, correctly matched across cameras?
        # Three agreeing cameras are self-checking; two cannot detect a wrong match by
        # line agreement alone (any two lines intersect); one camera is a weak estimate.
        n = len(f.observations)
        cam_factor = {1: 0.5, 2: 0.97}.get(n, 1.0)
        best_two = sorted((o.candidate.confidence for o in f.observations), reverse=True)[:2]
        cand_conf = float(np.mean(best_two))
        detection_conf = float(cam_factor * (0.75 + 0.25 * cand_conf))
        impact_conf = float(1.0 - math.exp(-(2.0 ** 2) / (2.0 * sigma * sigma)))
        score_conf = float(top.probability)
        overall = detection_conf * score_conf
        r, theta = self.board.to_polar(*f.impact)
        dd = self.board.config.double_outer_radius_mm
        per_cam = {}
        for o in f.observations:
            per_cam[o.camera_id] = {
                **o.candidate.to_dict(),
                "line_residual_mm": round(f.residuals_mm[o.camera_id], 3),
                "line_sigma_mm": round(o.line.sigma_mm, 3),
                "tip_weight": round(f.tip_weights.get(o.camera_id, 0.0), 3),
            }
        return {
            "dart_id": uuid.uuid4().hex[:16],
            "timestamp": ts,
            "impact": {"x_mm": round(float(f.impact[0]), 3), "y_mm": round(float(f.impact[1]), 3),
                       "r_mm": round(r, 3), "theta_deg": round(theta, 3),
                       "x_norm": round(float(f.impact[0]) / dd, 5), "y_norm": round(float(f.impact[1]) / dd, 5)},
            "covariance_mm2": [[round(float(v), 5) for v in row] for row in cov],
            "sigma_mm": round(sigma, 3),
            "score": top.score.to_dict() if top.score.label == exact.label else exact.to_dict(),
            "alternatives": [d.to_dict() for d in dist[1:1 + cfg.scoring.max_alternatives]],
            "score_probability": round(score_conf, 4),
            "confidence": {"detection": round(detection_conf, 4), "impact": round(impact_conf, 4),
                           "score": round(score_conf, 4), "overall": round(overall, 4)},
            "uncertain": bool(overall < cfg.scoring.confidence_threshold),
            "cameras_used": f.cameras,
            "cameras_rejected": f.rejected,
            "per_camera": per_cam,
            "axis": None if f.axis is None else [round(float(v), 4) for v in f.axis],
            "tilt_deg": None if f.tilt_deg is None else round(f.tilt_deg, 2),
            "consistency": round(f.line_consistency, 4),
            "covariance_inflation": round(inflation, 3),
            "frame_timestamps": {cid: fr.timestamp for cid, fr in frames.items()},
        }

    # ------------------------------------------------------------------ manual darts
    def add_manual_dart(self, dart_id: str, impact: np.ndarray | None, label: str, ts: float | None = None) -> None:
        """Register a dart entered by the user, so that its later removal is understood."""
        with self._lock:
            self.board_state.add(KnownDart(dart_id, np.zeros(2) if impact is None else np.asarray(impact, float),
                                           self._last_ts if ts is None else ts, label, {}, manual=True))

    # ------------------------------------------------------------------ calibration validation
    def validate_calibration(self) -> dict[str, ValidationResult]:
        """Check every calibrated camera's pose against its latest frame (known darts are
        masked out). Intended for idle moments."""
        out = {}
        if self._aligner is None:
            self._aligner = EdgeAligner(self.board)
        with self._lock:
            items = [(cid, ctx, ctx.last_frame) for cid, ctx in self.cameras.items()]
        for cid, ctx, frame in items:
            if ctx.model is None or frame is None:
                continue
            ignore = self.board_state.occluder_mask(cid, frame.image.shape[:2])
            if np.any(ignore):
                ignore = cv2.dilate(ignore, np.ones((9, 9), np.uint8))
            res = validate_pose(frame.image, ctx.model, self._aligner, self.config.validation, ignore)
            ctx.validation = res
            out[cid] = res
        if out:
            self._emit(EventType.CALIBRATION, self._last_ts, {cid: r.to_dict() for cid, r in out.items()})
        return out

    # ------------------------------------------------------------------ status
    def status(self) -> dict:
        with self._lock:
            return {
                "state": self.state.value,
                "paused": self._paused,
                "darts_on_board": [d.to_dict() for d in self.board_state.darts],
                "cameras": {
                    cid: {
                        "calibrated": ctx.model is not None,
                        "has_reference": ctx.reference is not None,
                        "has_empty_reference": ctx.empty is not None,
                        "motion_fraction": round(ctx.last_motion_fraction, 5),
                        "last_frame_ts": None if ctx.last_frame is None else ctx.last_frame.timestamp,
                        "candidates": len(ctx.last_candidates),
                        "validation": None if ctx.validation is None else ctx.validation.to_dict(),
                    }
                    for cid, ctx in self.cameras.items()
                },
                "stats": self.stats.to_dict(),
                "last_detection": self.last_detection,
            }

    # ------------------------------------------------------------------ live operation
    def attach(self, manager) -> None:
        self._manager = manager

    def start(self) -> None:
        if self._manager is None:
            raise RuntimeError("attach a CameraManager before start()")
        self._stop.clear()
        self._thread = threading.Thread(target=self._supervise, name="vision-engine", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self.state = EngineState.STOPPED

    def _supervise(self) -> None:
        backoff = 0.5
        while not self._stop.is_set():
            try:
                self._loop()
                return
            except Exception as exc:  # noqa: BLE001 - supervisor boundary: restart the loop
                self.stats.errors += 1
                log.exception("engine loop crashed; restarting")
                self._emit(EventType.ERROR, self._last_ts, {"error": f"engine crashed: {exc}", "restarting": True})
                self._stop.wait(backoff)
                backoff = min(backoff * 2, 10.0)

    def _loop(self) -> None:
        period = 1.0 / self.config.performance.engine_tick_hz
        while not self._stop.is_set():
            start = time.perf_counter()
            fs = self._manager.frameset()
            fresh = {cid: f for cid, f in fs.frames.items() if f.index != self._last_indices.get(cid)}
            if fresh:
                for cid, f in fresh.items():
                    self._last_indices[cid] = f.index
                self.process_frameset(fs.frames)
            delay = period - (time.perf_counter() - start)
            if delay > 0:
                self._stop.wait(delay)
