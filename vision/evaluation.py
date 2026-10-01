"""Accuracy evaluation: run scenarios through the *real* engine and compare its events with
ground truth.

* :class:`SimulationRunner` drives a :class:`SimulatedWorld` on a virtual clock: every
  camera renders frames at its own FPS and phase (unsynchronised cameras), the engine
  receives framesets exactly as in live operation.
* :func:`compute_metrics` matches detections to true darts and reports detection rate,
  impact error (mean / median / p95), score / sector / ring accuracy, false positives,
  misses, duplicates, uncertainty behaviour, confidence calibration and latency.

All numbers produced here are from *synthetic* footage and are labelled as such.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from vision.calibration.board_pose import calibrate_board
from vision.calibration.intrinsics import IntrinsicsResult
from vision.cameras.base import Frame
from vision.config import VisionConfig
from vision.engine import VisionEngine
from vision.events import EventType, VisionEvent
from vision.geometry.board import BoardGeometry, DartScore, Ring
from vision.geometry.camera_model import CameraModel
from vision.simulation.renderer import RenderOptions
from vision.simulation.rig import default_rig, default_rig_specs
from vision.simulation.world import GroundTruthDart, SimulatedWorld, ThrowParams


class _VirtualClock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


@dataclass
class ScenarioStep:
    at: float
    action: str  # throw | takeout | hand | lighting
    params: dict = field(default_factory=dict)


@dataclass
class Scenario:
    name: str
    steps: list[ScenarioStep]
    duration: float
    lighting: str = "neutral"


def turns_scenario(n_turns: int, rng: np.random.Generator, mode: str = "uniform", throw_gap: float = 1.2,
                   lighting: str = "neutral", hand_pass_prob: float = 0.0,
                   lighting_changes: list[str] | None = None) -> Scenario:
    """Turns of three darts followed by a takeout. ``mode``: ``uniform`` (anywhere on the
    board), ``cluster`` (grouped around a target: heavy overlap/occlusion), ``boundary``
    (aimed at wires: hard scoring cases) or ``mixed``."""
    steps: list[ScenarioStep] = []
    t = 1.5
    targets = [(0.0, 103.0), (0.0, 166.0), (0.0, 0.0), (-50.0, -90.0), (90.0, 40.0)]
    for turn in range(n_turns):
        m = mode if mode != "mixed" else ("uniform", "cluster", "boundary")[turn % 3]
        aim = targets[int(rng.integers(len(targets)))]
        for k in range(3):
            if m == "cluster":
                p = {"target": aim, "scatter_mm": 9.0}
            elif m == "boundary":
                p = {"target": _boundary_point(rng)}
            else:
                p = {}
            steps.append(ScenarioStep(t, "throw", p))
            if hand_pass_prob and rng.uniform() < hand_pass_prob:
                steps.append(ScenarioStep(t + throw_gap * 0.55, "hand", {}))
            t += throw_gap
        if lighting_changes and turn % 2 == 1:
            steps.append(ScenarioStep(t - 0.3, "lighting", {"preset": lighting_changes[turn % len(lighting_changes)]}))
        steps.append(ScenarioStep(t, "takeout", {}))
        t += 3.0
    return Scenario(f"{mode}_{n_turns}turns", steps, t + 1.0, lighting)


def _boundary_point(rng: np.random.Generator) -> tuple[float, float]:
    board = BoardGeometry()
    if rng.uniform() < 0.5:  # near a ring wire
        r = float(rng.choice(list(board.ring_radii.values()))) + float(rng.normal(0, 1.2))
        theta = float(rng.uniform(0, 360))
    else:  # near a sector wire
        r = float(rng.uniform(20, 165))
        theta = float(rng.choice(board.sector_boundary_angles())) + math.degrees(float(rng.normal(0, 1.2)) / max(r, 1))
    return board.from_polar(max(r, 0.5), theta)


@dataclass
class RunResult:
    scenario: str
    ground_truth: list[GroundTruthDart]
    events: list[VisionEvent]
    wall_seconds: float
    framesets: int
    engine_stats: dict
    calibration: dict


class SimulationRunner:
    def __init__(self, config: VisionConfig | None = None, seed: int = 1, fps: float = 30.0,
                 width: int = 1280, height: int = 720, calibration: str = "auto",
                 render_options: RenderOptions | None = None, lighting: str = "neutral",
                 rig_jitter_seed: int | None = 3) -> None:
        self.config = config or VisionConfig()
        self.clock = _VirtualClock()
        self.rig = default_rig(width, height, jitter_seed=rig_jitter_seed)
        self.specs = {s.camera_id: s for s in default_rig_specs(width, height, jitter_seed=rig_jitter_seed)}
        self.world = SimulatedWorld(self.rig, self.config.board, lighting=lighting, seed=seed,
                                    render_options=render_options, clock=self.clock)
        self.fps = fps
        rng = np.random.default_rng(seed + 1000)
        self.phase = {cid: float(rng.uniform(0, 1.0 / fps)) for cid in self.rig}
        self.calibration_mode = calibration
        self.calibration_report: dict[str, Any] = {}
        self.models = self._calibrate(calibration)
        self.engine = VisionEngine(self.config, self.models)
        self.events: list[VisionEvent] = []
        self.engine.subscribe(self.events.append)
        self._frame_idx = {cid: 0 for cid in self.rig}

    def _calibrate(self, mode: str) -> dict[str, CameraModel]:
        """``truth``: exact rig models. ``auto``: automatic board calibration on a rendered
        empty board with known intrinsics (as after a ChArUco calibration). ``board_only``:
        automatic calibration estimating the intrinsics from the board itself."""
        if mode == "truth":
            return dict(self.rig)
        out = {}
        for cid, cam in self.rig.items():
            img = self.world.render(cid, 0.0)
            intr = None
            if mode == "auto":
                intr = IntrinsicsResult(K=cam.K.copy(), dist=cam.dist.copy(), image_size=cam.image_size,
                                        rms_px=0.3, n_views=20, per_view_rms_px=[], coverage=0.9)
            prior = round(self.specs[cid].azimuth_deg / 30.0) * 30.0
            res = calibrate_board(img, self.config, cid, intrinsics=intr, azimuth_prior_deg=prior)
            if not res.ok or res.camera is None:
                raise RuntimeError(f"automatic calibration failed for {cid}: {res.reason}")
            out[cid] = res.camera
            self.calibration_report[cid] = {"grade": res.grade, **res.metrics,
                                            "true_shift_mm": _model_shift(cam, res.camera)}
        return out

    def run(self, scenario: Scenario, progress: Callable[[float], None] | None = None) -> RunResult:
        if scenario.lighting:
            self.world.set_lighting(scenario.lighting, at=-1.0)
        steps = sorted(scenario.steps, key=lambda s: s.at)
        si = 0
        period = 1.0 / self.fps
        t = 0.0
        start = time.perf_counter()
        n = 0
        while t < scenario.duration:
            while si < len(steps) and steps[si].at <= t + period:
                self._apply(steps[si])
                si += 1
            frames = {}
            for cid in self.rig:
                ft = t + self.phase[cid]
                self.clock.t = ft
                img = self.world.render(cid, ft)
                self._frame_idx[cid] += 1
                frames[cid] = Frame(cid, img, ft, self._frame_idx[cid])
            self.engine.process_frameset(frames)
            n += 1
            t += period
            if progress and n % 30 == 0:
                progress(t / scenario.duration)
        return RunResult(scenario.name, self.world.ground_truth, list(self.events),
                         time.perf_counter() - start, n, self.engine.stats.to_dict(), self.calibration_report)

    def _apply(self, step: ScenarioStep) -> None:
        if step.action == "throw":
            p = step.params
            self.world.throw(ThrowParams(target=p.get("target"), scatter_mm=p.get("scatter_mm", 0.0)), at=step.at)
        elif step.action == "takeout":
            self.world.remove_darts(at=step.at)
        elif step.action == "hand":
            self.world.pass_hand(at=step.at, duration=0.5)
        elif step.action == "lighting":
            self.world.set_lighting(step.params["preset"], at=step.at, transition_s=0.4)


def _model_shift(true_cam: CameraModel, est: CameraModel) -> float:
    from vision.calibration.validation import board_shift_mm

    return round(board_shift_mm(true_cam, est), 4)


# ---------------------------------------------------------------------------- metrics
@dataclass
class Match:
    gt: GroundTruthDart
    event: dict | None
    error_mm: float | None = None
    mahalanobis2: float | None = None


def compute_metrics(results: list[RunResult], board: BoardGeometry | None = None, match_radius_mm: float = 25.0
                    ) -> dict[str, Any]:
    board = board or BoardGeometry()
    matches: list[Match] = []
    false_pos: list[dict] = []
    duplicates: list[dict] = []
    latencies: list[float] = []
    processing: list[float] = []
    unrecognized = 0
    for res in results:
        gts = sorted(res.ground_truth, key=lambda g: g.landed_at)
        darts = [e for e in res.events if e.type == EventType.DART]
        unrecognized += sum(1 for e in res.events if e.type == EventType.UNRECOGNIZED)
        matched: dict[str, dict] = {}
        for e in darts:
            p = np.array([e.data["impact"]["x_mm"], e.data["impact"]["y_mm"]])
            live = [g for g in gts if g.landed_at <= e.timestamp and (g.removed_at is None or g.removed_at > e.timestamp - 2.0)]
            best, best_d = None, math.inf
            for g in live:
                d = float(np.linalg.norm(g.impact - p))
                if d < best_d:
                    best, best_d = g, d
            if best is None or best_d > match_radius_mm:
                false_pos.append(e.data)
            elif best.dart_id in matched:
                duplicates.append(e.data)
            else:
                matched[best.dart_id] = e.data
                latencies.append(e.timestamp - best.landed_at)
        for g in gts:
            ev = matched.get(g.dart_id)
            if ev is None:
                matches.append(Match(g, None))
                continue
            p = np.array([ev["impact"]["x_mm"], ev["impact"]["y_mm"]])
            err = float(np.linalg.norm(p - g.impact))
            cov = np.asarray(ev["covariance_mm2"], float)
            r = p - g.impact
            try:
                m2 = float(r @ np.linalg.inv(cov) @ r)
            except np.linalg.LinAlgError:
                m2 = None
            matches.append(Match(g, ev, err, m2))
        processing += [float(x) for x in []]
    n = len(matches)
    det = [m for m in matches if m.event is not None]
    errs = np.array([m.error_mm for m in det]) if det else np.array([])

    def score_ok(m: Match) -> bool:
        return m.event is not None and m.event["score"]["label"] == m.gt.score.label

    auto = [m for m in det if not m.event["uncertain"]]
    flagged = [m for m in det if m.event["uncertain"]]
    wrong = [m for m in det if not score_ok(m)]
    sub = {
        "bull": [m for m in matches if m.gt.score.ring in (Ring.INNER_BULL, Ring.OUTER_BULL)],
        "double": [m for m in matches if m.gt.score.ring == Ring.DOUBLE],
        "triple": [m for m in matches if m.gt.score.ring == Ring.TRIPLE],
        "single": [m for m in matches if m.gt.score.ring in (Ring.INNER_SINGLE, Ring.OUTER_SINGLE)],
        "miss": [m for m in matches if m.gt.score.ring == Ring.MISS],
    }

    def acc(ms: list[Match]) -> float | None:
        return None if not ms else round(sum(score_ok(m) for m in ms) / len(ms), 4)

    within95 = [m.mahalanobis2 for m in det if m.mahalanobis2 is not None]
    out = {
        "synthetic": True,
        "darts_thrown": n,
        "detected": len(det),
        "detection_rate": round(len(det) / n, 4) if n else None,
        "missed": n - len(det),
        "miss_rate": round((n - len(det)) / n, 4) if n else None,
        "false_positives": len(false_pos),
        "false_positive_rate": round(len(false_pos) / max(1, n), 4),
        "duplicates": len(duplicates),
        "duplicate_rate": round(len(duplicates) / max(1, n), 4),
        "unrecognized_change_events": unrecognized,
        "impact_error_mm": None if errs.size == 0 else {
            "mean": round(float(errs.mean()), 3), "median": round(float(np.median(errs)), 3),
            "p95": round(float(np.percentile(errs, 95)), 3), "max": round(float(errs.max()), 3)},
        "score_accuracy_all_thrown": acc(matches),
        "score_accuracy_detected": acc(det),
        "sector_accuracy_detected": None if not det else round(sum(m.event["score"]["sector"] == m.gt.score.sector for m in det) / len(det), 4),
        "ring_accuracy_detected": None if not det else round(sum(m.event["score"]["ring"] == m.gt.score.ring.value for m in det) / len(det), 4),
        "accuracy_by_region": {k: acc(v) for k, v in sub.items()},
        "count_by_region": {k: len(v) for k, v in sub.items()},
        "uncertain_rate": round(len(flagged) / max(1, len(det)), 4),
        "auto_accepted_accuracy": acc(auto),
        "wrong_scores_flagged_uncertain": None if not wrong else round(sum(m.event["uncertain"] for m in wrong) / len(wrong), 4),
        "wrong_auto_accepted": sum(1 for m in auto if not score_ok(m)),
        "confidence_calibration": None if not within95 else {
            "fraction_within_95pct_ellipse": round(float(np.mean(np.array(within95) <= 5.991)), 4),
            "fraction_within_68pct_ellipse": round(float(np.mean(np.array(within95) <= 2.279)), 4)},
        "latency_s": None if not latencies else {"mean": round(float(np.mean(latencies)), 3),
                                                 "p95": round(float(np.percentile(latencies, 95)), 3)},
        "processing_ms": _merge_stat([r.engine_stats.get("processing_ms") for r in results]),
        "camera_count_used": _count_cams(det),
        "worst_cases": [
            {"gt": m.gt.score.label, "pred": m.event["score"]["label"], "error_mm": round(m.error_mm, 2),
             "uncertain": m.event["uncertain"], "cameras": m.event["cameras_used"],
             "gt_impact": [round(float(v), 1) for v in m.gt.impact]}
            for m in sorted(det, key=lambda m: -m.error_mm)[:8]
        ],
        "missed_darts": [{"gt": m.gt.score.label, "impact": [round(float(v), 1) for v in m.gt.impact]}
                         for m in matches if m.event is None][:10],
    }
    return out


def _merge_stat(stats: list[dict | None]) -> dict | None:
    vals = [s for s in stats if s]
    if not vals:
        return None
    return {"mean": round(float(np.mean([s["mean"] for s in vals])), 2),
            "p95": round(float(np.max([s["p95"] for s in vals])), 2),
            "max": round(float(np.max([s["max"] for s in vals])), 2)}


def _count_cams(det: list[Match]) -> dict[str, int]:
    out: dict[str, int] = {}
    for m in det:
        k = str(len(m.event["cameras_used"]))
        out[k] = out.get(k, 0) + 1
    return out
