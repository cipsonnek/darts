"""Per-camera motion detection on downscaled frames.

Only answers "is anything moving inside the board region right now?". The engine waits
until every camera has been still for the settle time before it analyses the scene, so a
dart in flight, a wobbling dart or a moving hand is never analysed mid-motion.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from vision.config import MotionConfig


@dataclass
class MotionSample:
    moving: bool
    fraction: float  # fraction of the region that changed since the previous frame
    threshold: float
    noise_sigma: float


class MotionDetector:
    def __init__(self, cfg: MotionConfig, roi: np.ndarray | None, frame_size: tuple[int, int]) -> None:
        self.cfg = cfg
        w, h = frame_size
        self.scale = cfg.analysis_width / float(w)
        self.size = (cfg.analysis_width, max(1, int(round(h * self.scale))))
        if roi is not None:
            small = cv2.resize(roi, self.size, interpolation=cv2.INTER_NEAREST)
            self.roi = small > 0
        else:
            self.roi = np.ones((self.size[1], self.size[0]), dtype=bool)
        self.roi_count = max(1, int(self.roi.sum()))
        self._prev: np.ndarray | None = None
        self._sigma = 1.0
        self._initialised = False

    def reset(self) -> None:
        self._prev = None

    def update(self, image: np.ndarray) -> MotionSample:
        g = cv2.cvtColor(cv2.resize(image, self.size, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
        g = cv2.GaussianBlur(g, (3, 3), 0).astype(np.int16)
        if self._prev is None:
            self._prev = g
            return MotionSample(False, 0.0, self.cfg.min_pixel_delta, self._sigma)
        d = np.abs(g - self._prev).astype(np.float32)
        self._prev = g
        vals = d[self.roi]
        thr = max(self.cfg.min_pixel_delta, self.cfg.noise_sigma_factor * self._sigma)
        frac = float(np.count_nonzero(vals > thr)) / self.roi_count
        moving = frac > self.cfg.motion_area_fraction
        if not moving:
            # Track sensor noise from still frames (median abs diff of two noisy frames).
            est = float(np.median(vals)) / 0.95 if vals.size else self._sigma
            if not self._initialised:
                self._sigma, self._initialised = max(est, 0.3), True
            else:
                self._sigma = 0.95 * self._sigma + 0.05 * max(est, 0.3)
        return MotionSample(moving, frac, thr, self._sigma)
