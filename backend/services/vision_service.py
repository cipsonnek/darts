"""Owns the camera manager, the vision engine, calibration workflows, recording/replay and
(in simulator mode) the simulated world. Everything the API needs from the vision side
goes through here; the engine itself stays independent of the web stack."""

from __future__ import annotations

import asyncio
import json
import logging
import math
import platform
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np

from backend.settings import AppSettings, save_runtime_overrides
from backend.ws.hub import EventHub
from vision.calibration.board_pose import BoardCalibration, calibrate_board, landmarks, STANDARD_MANUAL_POINTS
from vision.calibration.intrinsics import IntrinsicsCalibrator, IntrinsicsResult, render_charuco
from vision.calibration.store import CalibrationStore
from vision.cameras.base import Frame
from vision.cameras.manager import CameraManager
from vision.cameras.opencv_camera import probe_devices
from vision.config import CameraConfig
from vision.diagnostics.overlays import LAYERS, draw_board, draw_debug, topdown_view, undistort_image
from vision.engine import EngineState, VisionEngine
from vision.events import EventType, VisionEvent
from vision.geometry.board import BoardGeometry
from vision.geometry.camera_model import CameraModel
from vision.recording.format import camera_dir, list_sessions, read_frame_index, read_ground_truth, read_metadata
from vision.recording.recorder import SessionRecorder

log = logging.getLogger("backend.vision")

EventCallback = Callable[[VisionEvent], None]


class VisionService:
    def __init__(self, settings: AppSettings, hub: EventHub) -> None:
        self.settings = settings
        self.cfg = settings.vision
        self.hub = hub
        self.board = BoardGeometry(self.cfg.board)
        self.store = CalibrationStore(settings.path(self.cfg.calibration_dir))
        self.world = None
        self.manager: CameraManager | None = None
        self.engine: VisionEngine | None = None
        self.recorder: SessionRecorder | None = None
        self._recording_lock = threading.Lock()
        self._event_callbacks: list[EventCallback] = []
        self._intrinsics: dict[str, IntrinsicsCalibrator] = {}
        self._intrinsics_results: dict[str, IntrinsicsResult] = {}
        self._pending_pose: dict[str, BoardCalibration] = {}
        self._validation_thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.started_at = time.time()
        # Persists calibration history (set by the application: database profiles).
        self.profile_sink: Callable[[str, str, dict], None] | None = None
        self.simulator = settings.mode == "simulator"

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        if self.simulator:
            self.world = self._build_world()
        self.manager = CameraManager(self.cfg.cameras, world=self.world)
        models = {c.id: self.store.camera_model(c.id) for c in self.cfg.cameras if c.enabled}
        self.engine = VisionEngine(self.cfg, models)
        self.engine.attach(self.manager)
        self.engine.subscribe(self._on_engine_event)
        self.manager.start()
        self.engine.start()
        if self.cfg.validation.enabled:
            self._validation_thread = threading.Thread(target=self._validation_loop, name="calib-validation",
                                                       daemon=True)
            self._validation_thread.start()
        log.info("vision service started", extra={"mode": self.settings.mode, "cameras": self.manager.camera_ids,
                                                   "calibrated": [k for k, v in models.items() if v is not None]})

    def stop(self) -> None:
        self._stop.set()
        self.stop_recording()
        if self.engine is not None:
            self.engine.stop()
        if self.manager is not None:
            self.manager.stop()

    def _build_world(self):
        from vision.simulation.renderer import RenderOptions
        from vision.simulation.rig import build_camera, default_rig_specs
        from vision.simulation.world import SimulatedWorld

        specs = default_rig_specs(jitter_seed=self.cfg.simulator.seed + 2)
        cams = {}
        for cfg_cam, spec in zip([c for c in self.cfg.cameras if c.source.type == "synthetic"], specs):
            spec = type(spec)(**{**spec.__dict__, "camera_id": cfg_cam.id, "width": cfg_cam.width,
                                 "height": cfg_cam.height})
            cams[cfg_cam.id] = build_camera(spec)
        return SimulatedWorld(cams, self.cfg.board, lighting=self.cfg.simulator.lighting, seed=self.cfg.simulator.seed,
                              render_options=RenderOptions(noise_sigma=self.cfg.simulator.noise_sigma,
                                                           flicker=self.cfg.simulator.ambient_flicker))

    def add_event_callback(self, fn: EventCallback) -> None:
        self._event_callbacks.append(fn)

    def _on_engine_event(self, ev: VisionEvent) -> None:
        """Runs in the engine thread."""
        if self.recorder is not None:
            self.recorder.add_event(ev.to_dict())
        channel = "detection" if ev.type in (EventType.STATE,) else "events"
        self.hub.publish(channel, ev.type, {**ev.data, "timestamp": ev.timestamp})
        if ev.type == EventType.STATE:
            self.hub.publish("events", ev.type, ev.data)
        for fn in list(self._event_callbacks):
            try:
                fn(ev)
            except Exception:  # noqa: BLE001
                log.exception("vision event callback failed")

    # ------------------------------------------------------------------ cameras
    def camera_list(self) -> list[dict]:
        assert self.manager is not None
        health = {h["camera_id"]: h for h in self.manager.health()}
        out = []
        for c in self.cfg.cameras:
            data = self.store.load(c.id)
            pose = data.get("pose")
            out.append({
                "id": c.id, "name": c.name or c.id, "enabled": c.enabled, "config": c.model_dump(),
                "synthetic": c.source.type == "synthetic",
                "health": health.get(c.id),
                "calibration": {
                    "intrinsics": data.get("intrinsics") is not None,
                    "intrinsics_rms_px": (data.get("intrinsics") or {}).get("rms_px"),
                    "pose": pose is not None and not pose.get("stale"),
                    "grade": pose.get("grade") if pose else None,
                    "calibrated_at": pose.get("calibrated_at") if pose else None,
                    "method": pose.get("method") if pose else None,
                    "intrinsics_source": pose.get("intrinsics_source") if pose else None,
                },
            })
        return out

    def camera(self, camera_id: str) -> CameraConfig:
        for c in self.cfg.cameras:
            if c.id == camera_id:
                return c
        raise KeyError(camera_id)

    def latest_frame(self, camera_id: str) -> Frame | None:
        assert self.manager is not None
        try:
            return self.manager.latest(camera_id)
        except KeyError:
            return None

    def averaged_frame(self, camera_id: str, n: int = 5) -> np.ndarray | None:
        """Mean of the last frames (less sensor noise for calibration)."""
        assert self.manager is not None
        hist = self.manager.worker(camera_id).history()[-n:]
        if not hist:
            return None
        acc = np.zeros_like(hist[0].image, dtype=np.float32)
        for f in hist:
            acc += f.image
        return (acc / len(hist)).round().astype(np.uint8)

    def update_camera(self, camera_id: str, patch: dict[str, Any]) -> dict:
        cur = self.camera(camera_id)
        data = cur.model_dump()
        for k, v in patch.items():
            if isinstance(v, dict) and isinstance(data.get(k), dict):
                data[k].update(v)
            else:
                data[k] = v
        new = CameraConfig.model_validate(data)
        idx = [c.id for c in self.cfg.cameras].index(camera_id)
        self.cfg.cameras[idx] = new
        assert self.manager is not None
        self.manager.reconfigure(new)
        save_runtime_overrides(self.settings, {"vision": {"cameras": [c.model_dump() for c in self.cfg.cameras]}})
        log.info("camera reconfigured", extra={"camera": camera_id, "patch": patch})
        return new.model_dump()

    def apply_controls(self, camera_id: str, controls: dict[str, Any]) -> dict:
        assert self.manager is not None
        applied = self.manager.apply_controls(camera_id, **controls)
        cur = self.camera(camera_id)
        patch = {k: v for k, v in controls.items() if k in ("exposure", "gain", "auto_exposure", "white_balance")}
        if patch:
            self.update_camera_config_only(camera_id, patch)
        return applied

    def update_camera_config_only(self, camera_id: str, patch: dict[str, Any]) -> None:
        cur = self.camera(camera_id)
        new = CameraConfig.model_validate({**cur.model_dump(), **patch})
        idx = [c.id for c in self.cfg.cameras].index(camera_id)
        self.cfg.cameras[idx] = new
        save_runtime_overrides(self.settings, {"vision": {"cameras": [c.model_dump() for c in self.cfg.cameras]}})

    def probe(self) -> list[dict]:
        if self.simulator:
            return []
        return probe_devices(8)

    # ------------------------------------------------------------------ images
    def render_view(self, camera_id: str, width: int | None = None, layers: set[str] | None = None,
                    view: str = "raw", quality: int | None = None, model_override: CameraModel | None = None
                    ) -> bytes | None:
        frame = self.latest_frame(camera_id)
        if frame is None:
            return None
        return self.encode(frame, camera_id, width, layers or set(), view, quality, model_override)

    def encode(self, frame: Frame, camera_id: str, width: int | None, layers: set[str], view: str,
               quality: int | None, model_override: CameraModel | None = None) -> bytes:
        img = frame.image
        engine = self.engine
        ctx = engine.cameras.get(camera_id) if engine else None
        cam = model_override or (ctx.model if ctx else None)
        if view == "undistorted" and cam is not None:
            img = undistort_image(img, cam)
        elif view == "topdown" and cam is not None:
            img = topdown_view(img, cam, self.board)
            cam = None
        h, w = img.shape[:2]
        target_w = min(w, width or self.cfg.performance.stream_default_width)
        scale = target_w / w
        small = cv2.resize(img, (target_w, int(round(h * scale))), interpolation=cv2.INTER_AREA) if scale < 1 else img
        if layers and view != "topdown":
            darts = []
            if "darts" in layers and engine is not None:
                for d in engine.board_state.darts:
                    darts.append({"x_mm": float(d.impact[0]), "y_mm": float(d.impact[1]), "label": d.label,
                                  "axis": None if d.axis is None else d.axis.tolist()})
            info = None
            if "info" in layers and ctx is not None:
                info = [f"{camera_id}  state={engine.state.value}", f"motion={ctx.last_motion_fraction:.4f}",
                        f"candidates={len(ctx.last_candidates)}"]
            small = draw_debug(small, cam if view == "raw" else None, self.board, layers,
                               roi=ctx.roi if ctx else None, change=ctx.last_change if ctx else None,
                               candidates=ctx.last_candidates if ctx else None, darts=darts, info=info, scale=scale)
        q = quality or self.cfg.performance.stream_jpeg_quality
        ok, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, int(q)])
        return buf.tobytes() if ok else b""

    async def mjpeg(self, camera_id: str, width: int | None, fps: float | None, layers: set[str], view: str,
                    quality: int | None):
        """Multipart MJPEG generator: encodes only while a client is connected, at most at
        the requested rate, always the most recent frame (no queueing)."""
        boundary = b"--frame\r\n"
        period = 1.0 / max(0.5, min(fps or self.cfg.performance.stream_default_fps, 30.0))
        last_index = -1
        while True:
            t0 = time.monotonic()
            frame = self.latest_frame(camera_id)
            if frame is not None and frame.index != last_index:
                last_index = frame.index
                data = await asyncio.to_thread(self.encode, frame, camera_id, width, layers, view, quality)
                yield boundary + b"Content-Type: image/jpeg\r\nContent-Length: " + str(len(data)).encode() + \
                    b"\r\n\r\n" + data + b"\r\n"
            await asyncio.sleep(max(0.005, period - (time.monotonic() - t0)))

    # ------------------------------------------------------------------ calibration
    def calibration_status(self) -> dict:
        out = {}
        for c in self.cfg.cameras:
            data = self.store.load(c.id)
            pose = data.get("pose")
            ctx = self.engine.cameras.get(c.id) if self.engine else None
            health = None
            if self.manager is not None and c.id in self.manager.camera_ids:
                health = self.manager.worker(c.id).health.to_dict()
            out[c.id] = {
                "camera_id": c.id,
                "name": c.name or c.id,
                "connected": bool(health and health["connected"]),
                "intrinsics": data.get("intrinsics"),
                "pose": pose,
                "pending": self._pending_pose[c.id].to_dict() if c.id in self._pending_pose else None,
                "intrinsics_session": self._intrinsics[c.id].status() if c.id in self._intrinsics else None,
                "validation": None if ctx is None or ctx.validation is None else ctx.validation.to_dict(),
                "mount": c.mount.model_dump(),
            }
        return out

    def landmarks(self) -> dict:
        lm = landmarks(self.board)
        return {"standard": STANDARD_MANUAL_POINTS,
                "points": {k: {"x_mm": v[0], "y_mm": v[1]} for k, v in lm.items()}}

    def detect_board(self, camera_id: str, method: str = "auto", points: dict[str, list[float]] | None = None,
                     hint: list[float] | None = None, azimuth: float | None = None) -> dict:
        img = self.averaged_frame(camera_id)
        if img is None:
            raise RuntimeError("no frames from this camera")
        intr = self.store.intrinsics(camera_id)
        cam_cfg = self.camera(camera_id)
        prior = azimuth if azimuth is not None else cam_cfg.mount.azimuth_deg
        pts = {k: (float(v[0]), float(v[1])) for k, v in (points or {}).items()} if method == "manual" else None
        res = calibrate_board(img, self.cfg, camera_id, intrinsics=intr, azimuth_prior_deg=prior,
                              hint_px=tuple(hint) if hint else None, manual_points=pts)
        if res.ok:
            self._pending_pose[camera_id] = res
        self.hub.publish("calibration", "board_detection", {"camera_id": camera_id, **res.to_dict()})
        return res.to_dict()

    def accept_pose(self, camera_id: str) -> dict:
        res = self._pending_pose.pop(camera_id, None)
        if res is None or res.camera is None:
            raise KeyError("no pending calibration for this camera")
        data = self.store.save_pose(camera_id, res.camera, res.method, {**res.metrics, **res.derived}, res.grade,
                                    res.intrinsics_source)
        if self.profile_sink is not None:
            self.profile_sink(camera_id, "pose", data.get("pose") or {})
        assert self.engine is not None
        self.engine.set_camera_model(camera_id, res.camera)
        self.hub.publish("calibration", "pose_saved", {"camera_id": camera_id, "grade": res.grade})
        log.info("calibration saved", extra={"camera": camera_id, "grade": res.grade, "method": res.method})
        return data

    def discard_pose(self, camera_id: str) -> None:
        self._pending_pose.pop(camera_id, None)

    def clear_pose(self, camera_id: str) -> None:
        self.store.clear(camera_id)
        if self.engine is not None:
            self.engine.set_camera_model(camera_id, None)

    def preview_pose(self, camera_id: str, width: int | None = None) -> bytes | None:
        res = self._pending_pose.get(camera_id)
        model = res.camera if res is not None else None
        return self.render_view(camera_id, width, {"board", "sectors", "labels"}, "raw", 85, model_override=model)

    def intrinsics_start(self, camera_id: str) -> dict:
        frame = self.latest_frame(camera_id)
        if frame is None:
            raise RuntimeError("no frames from this camera")
        self._intrinsics[camera_id] = IntrinsicsCalibrator(self.cfg.calibration, frame.size)
        return self._intrinsics[camera_id].status()

    def intrinsics_capture(self, camera_id: str) -> dict:
        cal = self._intrinsics.get(camera_id)
        if cal is None:
            raise KeyError("start an intrinsics session first")
        frame = self.latest_frame(camera_id)
        if frame is None:
            raise RuntimeError("no frames from this camera")
        det = cal.add_view(frame.image)
        return {"accepted": det.accepted, "corners": det.n_corners, "reason": det.reason, **cal.status()}

    def intrinsics_solve(self, camera_id: str) -> dict:
        cal = self._intrinsics.get(camera_id)
        if cal is None:
            raise KeyError("start an intrinsics session first")
        res = cal.calibrate()
        self._intrinsics_results[camera_id] = res
        good = res.rms_px <= self.cfg.calibration.max_intrinsic_rms_px and res.coverage >= 0.5
        return {**res.to_dict(), "grade": "good" if good else "poor"}

    def intrinsics_accept(self, camera_id: str) -> dict:
        res = self._intrinsics_results.pop(camera_id, None)
        if res is None:
            raise KeyError("solve the intrinsics first")
        self._intrinsics.pop(camera_id, None)
        data = self.store.save_intrinsics(camera_id, res)
        if self.profile_sink is not None:
            self.profile_sink(camera_id, "intrinsics", data.get("intrinsics") or {})
        if self.engine is not None:
            self.engine.set_camera_model(camera_id, None)  # pose must be re-done with new intrinsics
        return self.store.load(camera_id)

    def intrinsics_cancel(self, camera_id: str) -> None:
        self._intrinsics.pop(camera_id, None)
        self._intrinsics_results.pop(camera_id, None)

    def charuco_png(self) -> bytes:
        img = render_charuco(self.cfg.calibration, pixels_per_mm=11.81)  # 300 DPI
        ok, buf = cv2.imencode(".png", img)
        return buf.tobytes()

    def validate_now(self) -> dict:
        assert self.engine is not None
        res = self.engine.validate_calibration()
        return {cid: r.to_dict() for cid, r in res.items()}

    def _validation_loop(self) -> None:
        interval = max(5.0, self.cfg.validation.interval_s)
        while not self._stop.wait(interval):
            eng = self.engine
            if eng is None or eng.state != EngineState.IDLE or not eng.calibrated_cameras:
                continue
            try:
                eng.validate_calibration()
            except Exception:  # noqa: BLE001
                log.exception("calibration validation failed")

    def calibration_overall(self) -> dict:
        """One summary for the dashboard: all cameras, alignment and recommendation."""
        st = self.calibration_status()
        cams = []
        worst = "ok"
        for cid, s in st.items():
            pose = s.get("pose")
            val = s.get("validation")
            status = "uncalibrated"
            if pose and not pose.get("stale"):
                status = (val or {}).get("status", "ok") if val else "ok"
            if status in ("moved",):
                worst = "moved"
            elif status in ("warning", "uncalibrated") and worst == "ok":
                worst = "warning"
            cams.append({"camera_id": cid, "status": status, "grade": pose.get("grade") if pose else None,
                         "alignment": (val or {}).get("alignment"), "shift_mm": (val or {}).get("shift_mm"),
                         "message": (val or {}).get("message")})
        aligned = [c["alignment"] for c in cams if c["alignment"] is not None]
        return {"status": worst, "cameras": cams,
                "board_alignment": None if not aligned else round(float(np.mean(aligned)), 4),
                "recommendation": [f"Recalibrate {c['camera_id']}" for c in cams if c["status"] in ("moved", "warning", "uncalibrated")]}

    # ------------------------------------------------------------------ recording
    def start_recording(self, name: str | None = None, notes: str = "") -> dict:
        with self._recording_lock:
            if self.recorder is not None and self.recorder.active:
                raise RuntimeError("already recording")
            root = self.settings.path(self.cfg.recording.directory)
            self.recorder = SessionRecorder(root, name, self.cfg.recording.image_format, self.cfg.recording.jpeg_quality)
            self.recorder.set_metadata(
                cameras=[c.id for c in self.cfg.cameras if c.enabled],
                camera_configs=[c.model_dump() for c in self.cfg.cameras],
                calibration={c.id: self.store.load(c.id) for c in self.cfg.cameras},
                vision_config=self.cfg.model_dump(), synthetic=self.simulator, notes=notes,
                clock_origin=time.monotonic())
            assert self.manager is not None
            self.manager.add_listener(self.recorder.add_frame)
            log.info("recording started", extra={"recording": self.recorder.name})
            return self.recorder.summary()

    def stop_recording(self) -> dict | None:
        with self._recording_lock:
            rec = self.recorder
            if rec is None or not rec.active:
                return None
            if self.manager is not None:
                self.manager.remove_listener(rec.add_frame)
            if self.world is not None:
                from vision.recording.format import write_ground_truth

                write_ground_truth(rec.dir, [g.to_dict() for g in self.world.ground_truth])
            summary = rec.stop()
            self.recorder = None
            return summary

    def recording_status(self) -> dict | None:
        return None if self.recorder is None else self.recorder.summary()

    def recordings(self) -> list[dict]:
        return list_sessions(self.settings.path(self.cfg.recording.directory))

    def recording_path(self, name: str) -> Path:
        if not name or "/" in name or "\\" in name or ".." in name:
            raise ValueError("invalid recording name")
        p = self.settings.path(self.cfg.recording.directory) / name
        if not (p / "metadata.json").exists():
            raise FileNotFoundError(name)
        return p

    def recording_detail(self, name: str) -> dict:
        p = self.recording_path(name)
        meta = read_metadata(p)
        frames = {cid: [{"index": r.index, "timestamp": r.timestamp} for r in read_frame_index(p, cid)]
                  for cid in meta.get("cameras", [])}
        events = []
        ev_path = p / "events.jsonl"
        if ev_path.exists():
            events = [json.loads(line) for line in ev_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        result = None
        if (p / "evaluation.json").exists():
            result = json.loads((p / "evaluation.json").read_text(encoding="utf-8"))
        return {"name": name, "metadata": {k: v for k, v in meta.items() if k not in ("vision_config", "calibration")},
                "frames": frames, "events": [e for e in events if e.get("type") != EventType.STATE],
                "ground_truth": read_ground_truth(p), "evaluation": result}

    def recording_frame(self, name: str, camera_id: str, index: int, layers: set[str] | None = None,
                        width: int | None = None) -> bytes | None:
        p = self.recording_path(name)
        recs = read_frame_index(p, camera_id)
        rec = next((r for r in recs if r.index == index), None)
        if rec is None:
            return None
        img = cv2.imread(str(camera_dir(p, camera_id) / rec.file))
        if img is None:
            return None
        if layers:
            meta = read_metadata(p)
            pose = (meta.get("calibration", {}).get(camera_id) or {}).get("pose")
            cam = CameraModel.from_dict(pose) if pose else None
            if cam is not None:
                draw_board(img, cam, self.board, 1.0, "sectors" in layers, "labels" in layers)
        if width and width < img.shape[1]:
            img = cv2.resize(img, (width, int(img.shape[0] * width / img.shape[1])), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
        return buf.tobytes() if ok else None

    def recording_pixel_to_board(self, name: str, camera_id: str, x: float, y: float) -> list[float] | None:
        meta = read_metadata(self.recording_path(name))
        pose = (meta.get("calibration", {}).get(camera_id) or {}).get("pose")
        if not pose:
            return None
        p = CameraModel.from_dict(pose).pixel_to_board((x, y))
        return None if p is None else [float(p[0]), float(p[1])]

    def annotate(self, name: str, entries: list[dict]) -> list[dict]:
        from vision.recording.format import write_ground_truth

        p = self.recording_path(name)
        gt = read_ground_truth(p)
        for e in entries:
            imp = [float(e["x_mm"]), float(e["y_mm"])]
            gt.append({"dart_id": e.get("dart_id") or f"ann-{len(gt) + 1}", "impact_mm": imp,
                       "score": self.board.score(*imp).to_dict(), "landed_at": e.get("timestamp"),
                       "removed_at": None, "annotated": True, "frame_timestamp": e.get("timestamp")})
        write_ground_truth(p, gt)
        return gt

    def evaluate_recording(self, name: str) -> dict:
        from backend.services.replay import evaluate_session

        p = self.recording_path(name)
        res = evaluate_session(p, self.cfg)
        (p / "evaluation.json").write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
        return res

    # ------------------------------------------------------------------ simulator
    def require_simulator(self):
        if self.world is None:
            raise RuntimeError("simulator controls are only available in simulator mode")
        return self.world

    def sim_throw(self, target: list[float] | None, scatter_mm: float = 0.0, label: str | None = None) -> dict:
        from vision.geometry.board import DartScore
        from vision.simulation.world import ThrowParams

        w = self.require_simulator()
        if label and not target:
            s = DartScore.from_label(label)
            target = list(self._aim_point(s))
        gt = w.throw(ThrowParams(target=tuple(target) if target else None, scatter_mm=scatter_mm))
        return gt.to_dict()

    def _aim_point(self, s) -> tuple[float, float]:
        rr = self.board.ring_radii
        if s.sector == 25:
            return (0.0, 3.0 if s.multiplier == 2 else 11.0)
        r = {1: (rr["triple_outer"] + rr["double_inner"]) / 2, 2: (rr["double_inner"] + rr["double_outer"]) / 2,
             3: (rr["triple_inner"] + rr["triple_outer"]) / 2}.get(s.multiplier, 130.0)
        if s.sector == 0:
            r = 195.0
            return self.board.from_polar(r, 0.0)
        return self.board.from_polar(r, self.board.sector_center_angle(s.sector))

    def sim_takeout(self) -> dict:
        return {"removed": self.require_simulator().remove_darts()}

    def sim_lighting(self, preset: str) -> dict:
        self.require_simulator().set_lighting(preset, transition_s=0.5)
        return {"lighting": preset}

    def sim_hand(self) -> dict:
        self.require_simulator().pass_hand(duration=0.8)
        return {"ok": True}

    def sim_ground_truth(self) -> list[dict]:
        return [g.to_dict() for g in self.require_simulator().ground_truth]

    def sim_auto_calibrate(self) -> dict:
        """Run automatic board calibration on every camera and accept good results."""
        out = {}
        for c in self.cfg.cameras:
            try:
                res = self.detect_board(c.id, "auto")
                if res["ok"] and res["grade"] in ("good", "fair"):
                    self.accept_pose(c.id)
                out[c.id] = {"ok": res["ok"], "grade": res.get("grade"), "reason": res.get("reason")}
            except Exception as exc:  # noqa: BLE001
                out[c.id] = {"ok": False, "reason": str(exc)}
        return out

    # ------------------------------------------------------------------ diagnostics
    def diagnostics(self) -> dict:
        import psutil

        eng = self.engine
        assert self.manager is not None
        fs = self.manager.frameset()
        proc = psutil.Process()
        gpu = _gpu_info()
        return {
            "mode": self.settings.mode,
            "uptime_s": round(time.time() - self.started_at, 1),
            "engine": eng.status() if eng else None,
            "cameras": self.manager.health(),
            "sync": {"spread_ms": round(fs.sync_spread_ms, 2), "cameras": len(fs.frames)},
            "recording": self.recording_status(),
            "system": {
                "platform": platform.platform(), "python": platform.python_version(),
                "opencv": cv2.__version__, "numpy": np.__version__,
                "cpu_count": psutil.cpu_count(), "cpu_percent": psutil.cpu_percent(interval=None),
                "process_rss_mb": round(proc.memory_info().rss / 1e6, 1),
                "gpu": gpu,
            },
            "websocket_clients": self.hub.client_count,
        }

    def debug_snapshot(self) -> dict:
        eng = self.engine
        if eng is None:
            return {}
        out = {}
        for cid, ctx in eng.cameras.items():
            ch = ctx.last_change
            out[cid] = {
                "change": None if ch is None else {
                    "threshold": round(ch.threshold, 2), "noise_sigma": round(ch.noise_sigma, 3),
                    "added_fraction": round(ch.added_fraction, 5), "removed_fraction": round(ch.removed_fraction, 5),
                    "shadow_pixels": ch.shadow_pixels},
                "candidates": [c.to_dict() for c in ctx.last_candidates],
                "motion_fraction": ctx.last_motion_fraction,
            }
        return out


def _gpu_info() -> dict | None:
    import shutil
    import subprocess

    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "--query-gpu=name,memory.total,utilization.gpu", "--format=csv,noheader"],
                             capture_output=True, text=True, timeout=3, check=True).stdout.strip()
        return {"nvidia": out}
    except Exception:  # noqa: BLE001
        return None
