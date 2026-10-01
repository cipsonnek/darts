"""Camera abstraction. The rest of the engine only ever sees :class:`Frame` objects and
does not care how they were obtained."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from vision.config import CameraConfig


class CameraError(RuntimeError):
    pass


@dataclass
class Frame:
    camera_id: str
    image: np.ndarray  # BGR uint8, HxWx3
    timestamp: float  # seconds; monotonic clock (live) or source clock (replay/simulation)
    index: int = 0
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def size(self) -> tuple[int, int]:
        return self.image.shape[1], self.image.shape[0]


class Camera(ABC):
    """A frame source. Implementations must be safe to ``open``/``close`` repeatedly
    (the capture worker reconnects by closing and reopening)."""

    kind: str = "abstract"
    supports_trigger: bool = False

    def __init__(self, config: CameraConfig) -> None:
        self.config = config
        self._index = 0

    @property
    def camera_id(self) -> str:
        return self.config.id

    @abstractmethod
    def open(self) -> None: ...

    @abstractmethod
    def read(self) -> Frame | None:
        """Block until the next frame is available. Returns None on a (recoverable)
        read failure; raises CameraError when the device is gone."""

    @abstractmethod
    def close(self) -> None: ...

    @property
    @abstractmethod
    def is_open(self) -> bool: ...

    def set_controls(self, **controls: Any) -> dict[str, Any]:
        """Apply exposure/gain/white balance etc. Returns the values actually in effect."""
        return {}

    def get_controls(self) -> dict[str, Any]:
        return {}

    def trigger(self) -> None:
        """Software/hardware trigger hook for synchronised capture (not supported by
        free-running UVC cameras)."""
        raise NotImplementedError

    def info(self) -> dict[str, Any]:
        return {"id": self.camera_id, "kind": self.kind, "source": self.config.source.model_dump()}

    def _next_index(self) -> int:
        self._index += 1
        return self._index


def validate_frame(image: np.ndarray | None, expected: tuple[int, int] | None = None) -> str | None:
    """Return a reason string if the frame is unusable (corrupted), else None."""
    if image is None:
        return "empty"
    if image.ndim != 3 or image.shape[2] != 3 or image.dtype != np.uint8:
        return f"bad format {image.shape} {image.dtype}"
    if expected is not None and (image.shape[1], image.shape[0]) != expected:
        return f"unexpected size {image.shape[1]}x{image.shape[0]}"
    # Fully black/flat frames are a common symptom of a stalled USB stream.
    sub = image[::16, ::16]
    if int(sub.max()) - int(sub.min()) < 2:
        return "flat frame"
    return None
