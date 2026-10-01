"""Persistent knowledge of the darts currently stuck in the board.

Each known dart keeps its fused impact and, per camera, the pixels it occupies and its
image axis. This is what prevents scoring the same dart twice, lets the engine recognise
a dart that merely sagged or was nudged, tells which darts were pulled out, and provides
the occlusion masks for later throws."""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass, field

import numpy as np

from vision.dart_detection.candidates import DartCandidate


@dataclass
class CameraFootprint:
    bbox: tuple[int, int, int, int]  # full-frame x0, y0, x1, y1
    mask: np.ndarray  # uint8 crop
    tip_px: np.ndarray
    tail_px: np.ndarray

    @staticmethod
    def from_candidate(c: DartCandidate, dilate: int = 2) -> "CameraFootprint":
        import cv2

        x0, y0, x1, y1 = c.mask_bbox
        m = c.mask
        if dilate > 0:
            m = cv2.copyMakeBorder(m, dilate, dilate, dilate, dilate, cv2.BORDER_CONSTANT, value=0)
            m = cv2.dilate(m, np.ones((2 * dilate + 1, 2 * dilate + 1), np.uint8))
            x0, y0, x1, y1 = x0 - dilate, y0 - dilate, x1 + dilate, y1 + dilate
        return CameraFootprint((x0, y0, x1, y1), m, c.tip_px.copy(), c.tail_px.copy())

    def paint(self, target: np.ndarray, value: int = 255) -> None:
        x0, y0, x1, y1 = self.bbox
        H, W = target.shape[:2]
        cx0, cy0, cx1, cy1 = max(0, x0), max(0, y0), min(W, x1), min(H, y1)
        if cx1 <= cx0 or cy1 <= cy0:
            return
        crop = self.mask[cy0 - y0:cy1 - y0, cx0 - x0:cx1 - x0]
        region = target[cy0:cy1, cx0:cx1]
        region[crop > 0] = value

    def pixel_coords(self) -> tuple[np.ndarray, np.ndarray]:
        ys, xs = np.nonzero(self.mask)
        return xs + self.bbox[0], ys + self.bbox[1]


@dataclass
class KnownDart:
    dart_id: str
    impact: np.ndarray
    detected_at: float
    label: str
    footprints: dict[str, CameraFootprint] = field(default_factory=dict)
    axis: np.ndarray | None = None
    manual: bool = False

    def to_dict(self) -> dict:
        return {"dart_id": self.dart_id, "impact_mm": [round(float(v), 2) for v in self.impact],
                "label": self.label, "detected_at": self.detected_at, "cameras": sorted(self.footprints),
                "manual": self.manual}


class BoardState:
    def __init__(self) -> None:
        self._darts: dict[str, KnownDart] = {}
        self._lock = threading.RLock()

    @property
    def darts(self) -> list[KnownDart]:
        with self._lock:
            return sorted(self._darts.values(), key=lambda d: d.detected_at)

    def __len__(self) -> int:
        return len(self._darts)

    def add(self, dart: KnownDart) -> None:
        with self._lock:
            self._darts[dart.dart_id] = dart

    def remove(self, dart_ids: list[str]) -> list[KnownDart]:
        with self._lock:
            return [self._darts.pop(i) for i in dart_ids if i in self._darts]

    def clear(self) -> list[KnownDart]:
        with self._lock:
            out = list(self._darts.values())
            self._darts.clear()
            return out

    def occluder_mask(self, camera_id: str, shape: tuple[int, int]) -> np.ndarray:
        m = np.zeros(shape, dtype=np.uint8)
        for d in self.darts:
            fp = d.footprints.get(camera_id)
            if fp is not None:
                fp.paint(m)
        return m

    def nearest(self, impact: np.ndarray) -> tuple[KnownDart | None, float]:
        best, best_d = None, math.inf
        for d in self.darts:
            dist = float(np.linalg.norm(d.impact - impact))
            if dist < best_d:
                best, best_d = d, dist
        return best, best_d

    def matches_footprint(self, camera_id: str, cand: DartCandidate, max_angle_deg: float = 4.0,
                          max_offset_px: float = 5.0) -> KnownDart | None:
        """A candidate that lies on a known dart's image axis is that dart (it sagged,
        wobbled or was nudged) rather than a new one."""
        cd = cand.tail_px - cand.tip_px
        cl = np.linalg.norm(cd)
        if cl < 1e-6:
            return None
        cu = cd / cl
        for d in self.darts:
            fp = d.footprints.get(camera_id)
            if fp is None:
                continue
            kd = fp.tail_px - fp.tip_px
            kl = np.linalg.norm(kd)
            if kl < 1e-6:
                continue
            ku = kd / kl
            ang = math.degrees(math.acos(min(1.0, abs(float(cu @ ku)))))
            if ang > max_angle_deg:
                continue
            normal = np.array([-ku[1], ku[0]])
            off_tip = abs(float((cand.tip_px - fp.tip_px) @ normal))
            along = float((cand.tip_px - fp.tip_px) @ ku)
            if off_tip <= max_offset_px and abs(along) <= max(25.0, 0.15 * kl):
                return d
        return None
