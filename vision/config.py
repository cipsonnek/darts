"""Typed configuration for the vision engine.

All tunable numbers live here (with their documented defaults) and are loaded from YAML by
:func:`load_vision_config`. Nothing else in ``vision`` should hard-code a threshold.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

STANDARD_SECTOR_ORDER: list[int] = [
    20, 1, 18, 4, 13, 6, 10, 15, 2, 17, 3, 19, 7, 16, 8, 11, 14, 9, 12, 5,
]


class BoardConfig(BaseModel):
    """Board dimensions in millimetres, measured from the centre to the *centre line of the
    wire* that forms each boundary. Defaults are WDF/PDC regulation values."""

    inner_bull_radius_mm: float = Field(6.35, gt=0)
    outer_bull_radius_mm: float = Field(15.9, gt=0)
    triple_inner_radius_mm: float = Field(99.0, gt=0)
    triple_outer_radius_mm: float = Field(107.0, gt=0)
    double_inner_radius_mm: float = Field(162.0, gt=0)
    double_outer_radius_mm: float = Field(170.0, gt=0)
    board_radius_mm: float = Field(225.5, gt=0)
    wire_width_mm: float = Field(1.2, ge=0)
    sector_order: list[int] = Field(default_factory=lambda: list(STANDARD_SECTOR_ORDER))
    # Colours of the double/triple ring on the sector at index 0 (the 20). Standard boards
    # have a red double 20; the colour alternates every sector.
    first_sector_ring_color: Literal["red", "green"] = "red"

    @model_validator(mode="after")
    def _check_ordering(self) -> "BoardConfig":
        radii = [
            self.inner_bull_radius_mm,
            self.outer_bull_radius_mm,
            self.triple_inner_radius_mm,
            self.triple_outer_radius_mm,
            self.double_inner_radius_mm,
            self.double_outer_radius_mm,
            self.board_radius_mm,
        ]
        if any(b <= a for a, b in zip(radii, radii[1:])):
            raise ValueError("board radii must be strictly increasing from bull to board edge")
        if sorted(self.sector_order) != list(range(1, 21)):
            raise ValueError("sector_order must be a permutation of 1..20")
        return self


class CameraSourceConfig(BaseModel):
    type: Literal["opencv", "rtsp", "replay", "synthetic"] = "opencv"
    device: int | str | None = None  # index or device path (opencv)
    url: str | None = None  # rtsp/http stream URL
    path: str | None = None  # replay directory
    api: Literal["auto", "dshow", "msmf", "v4l2", "gstreamer", "ffmpeg"] = "auto"
    fourcc: str | None = "MJPG"


class CameraMountConfig(BaseModel):
    """Rough physical placement. Used only as a prior (e.g. to resolve the 36° rotational
    ambiguity of the red/green ring pattern during automatic board detection)."""

    # Position of the camera around the board, as a clock angle in degrees measured
    # clockwise from 12 o'clock (the 20). 0 = top, 90 = right (6), 180 = bottom (3).
    azimuth_deg: float | None = None
    description: str = ""


class CameraConfig(BaseModel):
    id: str
    name: str = ""
    enabled: bool = True
    source: CameraSourceConfig = Field(default_factory=CameraSourceConfig)
    width: int = Field(1280, gt=0)
    height: int = Field(720, gt=0)
    fps: int = Field(30, gt=0, le=240)
    auto_exposure: bool = False
    exposure: float | None = None
    gain: float | None = None
    white_balance: float | None = None
    rotate_180: bool = False
    mount: CameraMountConfig = Field(default_factory=CameraMountConfig)

    @field_validator("id")
    @classmethod
    def _valid_id(cls, v: str) -> str:
        if not v or not all(c.isalnum() or c in "_-" for c in v):
            raise ValueError("camera id must be non-empty and contain only [A-Za-z0-9_-]")
        return v


class BoardDetectionConfig(BaseModel):
    """Automatic board detection from the red/green rings (board_detection/rings.py).
    Hue is OpenCV's 0..180 scale."""

    red_hue_low_max: int = 12
    red_hue_high_min: int = 160
    green_hue_min: int = 35
    green_hue_max: int = 95
    min_saturation: int = 70
    min_value: int = 30
    min_ring_area_fraction: float = 0.002
    max_pnp_rms_px: float = 4.0


class CalibrationConfig(BaseModel):
    """Intrinsic target and quality grading (calibration/*)."""

    charuco_squares_x: int = 7
    charuco_squares_y: int = 5
    charuco_square_mm: float = 30.0
    charuco_marker_mm: float = 22.0
    charuco_dictionary: str = "DICT_5X5_100"
    min_intrinsic_views: int = 8
    max_intrinsic_rms_px: float = 0.8
    # Board pose grading thresholds
    good_edge_rms_px: float = 0.8
    fair_edge_rms_px: float = 1.6
    good_inlier_fraction: float = 0.8
    fair_inlier_fraction: float = 0.6
    good_pose_sigma_mm: float = 0.3
    fair_pose_sigma_mm: float = 1.0


class MotionConfig(BaseModel):
    """Settle / motion detection on downscaled frames (tracking/motion.py)."""

    analysis_width: int = Field(320, ge=80)
    # Per-pixel absolute grey-level change counted as motion is max(min_pixel_delta,
    # noise_sigma_factor * estimated noise sigma).
    min_pixel_delta: float = 8.0
    noise_sigma_factor: float = 4.0
    # Fraction of the board region that must change between consecutive frames to count
    # as motion.
    motion_area_fraction: float = 0.0004
    # The scene must be motion-free for this long before it counts as settled.
    settle_time_ms: int = 280
    # The settled scene is analysed as the mean of up to this many still frames per camera:
    # averaging N frames divides sensor and compression noise by ~sqrt(N), which matters
    # a lot for webcams running high gain in dim rooms.
    settle_average_frames: int = Field(8, ge=1)
    # Upper bound so a never-settling scene (flicker) is still processed eventually.
    max_wait_ms: int = 4000


class DetectionConfig(BaseModel):
    """Dart change detection and axis extraction (dart_detection/*)."""

    # Change mask
    change_min_delta: float = 10.0
    change_noise_sigma_factor: float = 4.5
    # Hysteresis: weaker changes (factor × threshold) are kept when connected to strong ones.
    change_weak_factor: float = 0.5
    # Threshold increase per unit of local reference gradient (edge-aware threshold).
    change_edge_gain: float = 0.35
    # Changed blobs smaller than this (px) are sensor/compression noise.
    change_min_component_px: int = 6
    shadow_suppression: bool = True
    shadow_min_ratio: float = 0.35
    shadow_max_ratio: float = 0.92
    shadow_max_chroma_shift: float = 0.06
    photometric_normalization: bool = True

    # Candidate geometry (pixels at full resolution; scaled by camera size)
    min_dart_pixels: int = 60
    min_axis_length_px: float = 30.0
    max_component_width_px: float = 120.0
    min_elongation: float = 3.0
    max_candidates_per_camera: int = 4
    line_ransac_threshold_px: float = 2.5
    line_ransac_iterations: int = 300

    # Physical plausibility (mm)
    dart_length_mm: float = 150.0
    dart_length_tolerance: float = 0.6  # accept projected length within [ (1-tol)L, (1+tol)L ]
    max_dart_tilt_deg: float = 65.0  # angle between dart axis and board normal

    # Obstruction: a change larger than this fraction of the board area is a hand/body.
    obstruction_area_fraction: float = 0.08


class FusionConfig(BaseModel):
    """Multi-camera fusion (fusion/*)."""

    min_cameras: int = Field(2, ge=1)
    # Assumed 1-sigma errors used to build per-camera covariances.
    line_sigma_px: float = 1.0
    # Floor of a board line's 1-sigma (mm): calibration residuals, flight asymmetry and
    # mask edges put a lower bound on how well any single camera locates the axis.
    line_sigma_floor_mm: float = 0.3
    tip_sigma_px: float = 2.0
    # Candidates below this plausibility do not take part in fusion (diagnostics only).
    min_candidate_confidence: float = 0.15
    # A camera whose board line misses the fused point by more than this (in sigmas) is
    # rejected as an outlier (occlusion, wrong candidate).
    outlier_sigma: float = 6.0
    max_residual_mm: float = 6.0
    # Angle between two cameras' board lines below which their intersection is unreliable.
    min_line_angle_deg: float = 12.0
    # Unmodelled error (calibration, line bias) added in quadrature to the fused covariance
    # before computing score probabilities. Calibrated with scripts/benchmark.py.
    model_sigma_mm: float = 0.35


class ScoringConfig(BaseModel):
    # Darts whose score probability is below this are reported as uncertain and need a
    # human decision.
    confidence_threshold: float = Field(0.90, ge=0.0, le=1.0)
    monte_carlo_samples: int = Field(4000, ge=100)
    max_alternatives: int = 3
    # Treat an impact outside the double ring but on the board as a scored miss.
    report_misses: bool = True


class TrackingConfig(BaseModel):
    # A new detection closer than this to a known dart is treated as that dart.
    duplicate_radius_mm: float = 4.0
    max_darts_on_board: int = 12
    # A known dart whose per-camera pixels have mostly reverted to the empty board is
    # considered removed.
    removal_pixel_fraction: float = 0.6
    # The board must look empty for this long before it is declared clear.
    clear_confirm_ms: int = 500
    # At start-up the board is assumed empty and the first settled frames become the
    # empty-board reference ("Reset board" in the UI does the same later).
    assume_empty_on_start: bool = True
    # An "obstruction" that stays perfectly still this long is not a person but a changed
    # scene (lights switched on, curtains, board nudged): adopt it as the new reference.
    obstruction_rebaseline_s: float = 8.0


class ValidationConfig(BaseModel):
    """Calibration movement monitoring (calibration/validation.py)."""

    enabled: bool = True
    interval_s: float = 30.0
    edge_tolerance_px: float = 2.0
    min_alignment: float = 0.55  # fraction of model edge samples with nearby image edges
    max_shift_mm: float = 1.5


class PerformanceConfig(BaseModel):
    gpu_enabled: bool = False
    engine_tick_hz: float = Field(60.0, gt=0)
    stream_default_width: int = 640
    stream_default_fps: float = 12.0
    stream_jpeg_quality: int = Field(75, ge=10, le=100)


class RecordingConfig(BaseModel):
    directory: str = "recordings"
    image_format: Literal["png", "jpg"] = "jpg"
    jpeg_quality: int = 95
    record_on_events_only: bool = False


class SimulatorConfig(BaseModel):
    """Synthetic camera rig (vision/simulation). Only used by cameras with
    ``source.type: synthetic`` — never mixed with real cameras."""

    seed: int = 1
    lighting: Literal["neutral", "warm", "dim", "bright", "uneven"] = "neutral"
    noise_sigma: float = 1.8
    ambient_flicker: float = 0.004


class VisionConfig(BaseModel):
    board: BoardConfig = Field(default_factory=BoardConfig)
    cameras: list[CameraConfig] = Field(default_factory=list)
    board_detection: BoardDetectionConfig = Field(default_factory=BoardDetectionConfig)
    calibration: CalibrationConfig = Field(default_factory=CalibrationConfig)
    motion: MotionConfig = Field(default_factory=MotionConfig)
    detection: DetectionConfig = Field(default_factory=DetectionConfig)
    fusion: FusionConfig = Field(default_factory=FusionConfig)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    tracking: TrackingConfig = Field(default_factory=TrackingConfig)
    validation: ValidationConfig = Field(default_factory=ValidationConfig)
    performance: PerformanceConfig = Field(default_factory=PerformanceConfig)
    recording: RecordingConfig = Field(default_factory=RecordingConfig)
    simulator: SimulatorConfig = Field(default_factory=SimulatorConfig)
    calibration_dir: str = "data/calibration"

    @field_validator("cameras")
    @classmethod
    def _unique_ids(cls, cams: list[CameraConfig]) -> list[CameraConfig]:
        ids = [c.id for c in cams]
        if len(ids) != len(set(ids)):
            raise ValueError(f"duplicate camera ids: {ids}")
        return cams

    def camera(self, camera_id: str) -> CameraConfig:
        for cam in self.cameras:
            if cam.id == camera_id:
                return cam
        raise KeyError(camera_id)


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``override`` into a copy of ``base`` (lists are replaced)."""
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_yaml_layers(paths: list[Path]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for path in paths:
        if path.exists():
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if not isinstance(data, dict):
                raise ValueError(f"{path}: top level must be a mapping")
            merged = deep_merge(merged, data)
    return merged


def load_vision_config(paths: list[Path]) -> VisionConfig:
    data = load_yaml_layers(paths)
    return VisionConfig.model_validate(data.get("vision", data))
