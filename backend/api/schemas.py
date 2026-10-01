"""Request bodies (validated input)."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

_LABEL = re.compile(r"^(MISS|BULL|DB|SB|25|50|[SDT]?([1-9]|1[0-9]|20)|VOID)$", re.IGNORECASE)
_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def _label(v: str) -> str:
    v = v.strip().upper()
    if not _LABEL.match(v):
        raise ValueError("invalid dart label (examples: T20, D16, S5, 25, BULL, MISS)")
    return v


class PlayerIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    nickname: str | None = Field(None, max_length=64)
    color: str | None = None
    avatar: str | None = Field(None, max_length=16)

    @field_validator("name", "nickname")
    @classmethod
    def _clean(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = " ".join(v.split())
        if any(ord(ch) < 32 for ch in v):
            raise ValueError("control characters are not allowed")
        return v

    @field_validator("color")
    @classmethod
    def _color(cls, v: str | None) -> str | None:
        if v is not None and not _COLOR.match(v):
            raise ValueError("color must be #rrggbb")
        return v


class PlayerPatch(PlayerIn):
    name: str | None = Field(None, min_length=1, max_length=64)  # type: ignore[assignment]
    archived: bool | None = None


class GameIn(BaseModel):
    mode: str = Field(min_length=1, max_length=32)
    settings: dict[str, Any] = Field(default_factory=dict)
    player_ids: list[str] = Field(min_length=1, max_length=16)
    start: bool = True


class DartIn(BaseModel):
    label: str

    _v = field_validator("label")(lambda cls, v: _label(v))


class CorrectionIn(BaseModel):
    dart_id: str = Field(min_length=1, max_length=32)
    label: str
    x_mm: float | None = Field(None, ge=-400, le=400)
    y_mm: float | None = Field(None, ge=-400, le=400)
    note: str | None = Field(None, max_length=500)

    _v = field_validator("label")(lambda cls, v: _label(v))


class ResolveIn(BaseModel):
    choice: Literal["accept", "label", "reject"]
    label: str | None = None
    x_mm: float | None = Field(None, ge=-400, le=400)
    y_mm: float | None = Field(None, ge=-400, le=400)

    @field_validator("label")
    @classmethod
    def _lbl(cls, v: str | None) -> str | None:
        return None if v is None else _label(v)


class BoardCalibrationIn(BaseModel):
    method: Literal["auto", "manual"] = "auto"
    points: dict[str, list[float]] | None = None
    hint: list[float] | None = Field(None, min_length=2, max_length=2)
    azimuth_deg: float | None = Field(None, ge=0, le=360)


class CameraPatch(BaseModel):
    name: str | None = Field(None, max_length=64)
    enabled: bool | None = None
    width: int | None = Field(None, ge=160, le=4096)
    height: int | None = Field(None, ge=120, le=4096)
    fps: int | None = Field(None, ge=1, le=240)
    auto_exposure: bool | None = None
    exposure: float | None = None
    gain: float | None = None
    white_balance: float | None = None
    rotate_180: bool | None = None
    source: dict[str, Any] | None = None
    mount: dict[str, Any] | None = None

    @field_validator("source")
    @classmethod
    def _src(cls, v: dict | None) -> dict | None:
        if v is None:
            return v
        allowed = {"type", "device", "url", "path", "api", "fourcc"}
        bad = set(v) - allowed
        if bad:
            raise ValueError(f"unknown source fields {sorted(bad)}")
        if v.get("type") not in (None, "opencv", "rtsp", "replay"):
            raise ValueError("source.type must be opencv, rtsp or replay")
        url = v.get("url")
        if url is not None and not re.match(r"^(rtsp|rtsps|http|https)://[^\s]+$", str(url)):
            raise ValueError("url must be an rtsp/http(s) URL")
        return v


class ControlsIn(BaseModel):
    auto_exposure: bool | None = None
    exposure: float | None = Field(None, ge=-20, le=100000)
    gain: float | None = Field(None, ge=0, le=1000)
    white_balance: float | None = Field(None, ge=1000, le=12000)


class VisionSettingsPatch(BaseModel):
    """Subset of vision settings editable from the UI."""

    detection: dict[str, Any] | None = None
    fusion: dict[str, Any] | None = None
    scoring: dict[str, Any] | None = None
    motion: dict[str, Any] | None = None
    tracking: dict[str, Any] | None = None
    validation: dict[str, Any] | None = None
    performance: dict[str, Any] | None = None
    board: dict[str, Any] | None = None


class UiSettingsIn(BaseModel):
    value: dict[str, Any]


class RecordingIn(BaseModel):
    name: str | None = Field(None, pattern=r"^[A-Za-z0-9_.-]{1,80}$")
    notes: str = Field("", max_length=1000)


class AnnotationIn(BaseModel):
    entries: list[dict[str, Any]] = Field(min_length=1, max_length=50)


class SimThrowIn(BaseModel):
    target: list[float] | None = Field(None, min_length=2, max_length=2)
    label: str | None = None
    scatter_mm: float = Field(0.0, ge=0, le=100)

    @field_validator("label")
    @classmethod
    def _lbl(cls, v: str | None) -> str | None:
        return None if v is None else _label(v)


class SimLightingIn(BaseModel):
    preset: Literal["neutral", "led_ring", "warm", "dim", "bright", "uneven", "side_light"]
