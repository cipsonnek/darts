"""Events emitted by the vision engine. Plain, JSON-serialisable payloads: the engine does
not know who consumes them (backend, recorder, tests)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


class EventType:
    STATE = "engine_state"
    BASELINE = "baseline_set"
    DART = "dart_detected"
    DARTS_REMOVED = "darts_removed"
    BOARD_CLEAR = "board_clear"
    OBSTRUCTION = "obstruction"
    UNRECOGNIZED = "unrecognized_change"
    NO_CHANGE = "motion_without_change"
    DART_MOVED = "dart_moved"
    CALIBRATION = "calibration_status"
    ERROR = "engine_error"


@dataclass
class VisionEvent:
    type: str
    timestamp: float  # source clock (frame timestamps)
    data: dict[str, Any] = field(default_factory=dict)
    wall_time: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "timestamp": self.timestamp, "wall_time": self.wall_time, "data": self.data}
