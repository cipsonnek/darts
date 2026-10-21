"""Application settings: YAML layers + environment overrides, validated by Pydantic."""

from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

from vision.config import VisionConfig, deep_merge, load_yaml_layers

ROOT = Path(__file__).resolve().parents[1]


class ServerSettings(BaseModel):
    host: str = "127.0.0.1"
    port: int = Field(8000, ge=1, le=65535)
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"])
    admin_auth: Literal["localhost", "token", "off"] = "localhost"
    admin_token: str | None = None
    serve_frontend: bool = True


class DatabaseSettings(BaseModel):
    url: str = "sqlite:///data/dartsense.db"


class LoggingSettings(BaseModel):
    level: str = "INFO"
    directory: str = "logs"
    json_format: bool = Field(True, alias="json")
    event_retention_days: int = 30

    model_config = {"populate_by_name": True}


class FleetSettings(BaseModel):
    """Fleet management. On a board: where to report (``url`` + ``board_key``, both empty =
    reporting off). On the central server (``mode: central``): alert thresholds and the
    local time zone and currency used for statistics and settlements."""

    url: str | None = None
    board_key: str | None = None
    interval_s: int = Field(60, ge=10, le=3600)
    offline_after_s: int = Field(300, ge=30)
    timezone: str = "Europe/Warsaw"
    currency: str = "PLN"


class AppSettings(BaseModel):
    # live/simulator: a board with cameras; central: the operator's fleet server (no cameras).
    mode: Literal["live", "simulator", "central"] = "live"
    server: ServerSettings = Field(default_factory=ServerSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    vision: VisionConfig = Field(default_factory=VisionConfig)
    fleet: FleetSettings = Field(default_factory=FleetSettings)
    data_dir: str = "data"

    def path(self, p: str) -> Path:
        q = Path(p)
        return q if q.is_absolute() else ROOT / q

    @property
    def runtime_file(self) -> Path:
        return self.path(self.data_dir) / runtime_file_name(self.mode)


def runtime_file_name(mode: str) -> str:
    """UI overrides are kept per mode: the real cameras saved by a live board must never
    replace the simulator's synthetic cameras (or reach a central server)."""
    return "runtime.yaml" if mode == "live" else f"runtime-{mode}.yaml"


def config_layers() -> list[Path]:
    layers = [ROOT / "configs" / "default.yaml", ROOT / "configs" / "local.yaml"]
    extra = os.environ.get("DARTSENSE_CONFIG")
    if extra:
        p = Path(extra)
        layers.append(p if p.is_absolute() else ROOT / p)
    return layers


def load_settings(extra: dict[str, Any] | None = None) -> AppSettings:
    data = load_yaml_layers(config_layers())
    env = os.environ
    data_dir = (extra or {}).get("data_dir") or data.get("data_dir", "data")
    mode = (extra or {}).get("mode") or env.get("DARTSENSE_MODE") or data.get("mode", "live")
    runtime = Path(data_dir) if Path(data_dir).is_absolute() else ROOT / data_dir
    runtime = runtime / runtime_file_name(mode)
    if runtime.exists():
        data = deep_merge(data, yaml.safe_load(runtime.read_text(encoding="utf-8")) or {})
    if env.get("DARTSENSE_DATABASE_URL"):
        data = deep_merge(data, {"database": {"url": env["DARTSENSE_DATABASE_URL"]}})
    if env.get("DARTSENSE_HOST"):
        data = deep_merge(data, {"server": {"host": env["DARTSENSE_HOST"]}})
    if env.get("DARTSENSE_PORT"):
        data = deep_merge(data, {"server": {"port": int(env["DARTSENSE_PORT"])}})
    if env.get("DARTSENSE_MODE"):
        data = deep_merge(data, {"mode": env["DARTSENSE_MODE"]})
    if env.get("DARTSENSE_ADMIN_TOKEN"):
        data = deep_merge(data, {"server": {"admin_token": env["DARTSENSE_ADMIN_TOKEN"]}})
    if extra:
        data = deep_merge(data, extra)
    return AppSettings.model_validate(data)


def save_runtime_overrides(settings: AppSettings, overrides: dict[str, Any]) -> None:
    """Persist settings changed through the UI (merged with earlier overrides)."""
    path = settings.runtime_file
    path.parent.mkdir(parents=True, exist_ok=True)
    current = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    merged = deep_merge(current or {}, overrides)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(yaml.safe_dump(merged, sort_keys=False), encoding="utf-8")
    tmp.replace(path)


def ensure_admin_token(settings: AppSettings) -> str:
    if settings.server.admin_token:
        return settings.server.admin_token
    path = settings.path(settings.data_dir) / "admin_token.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        token = path.read_text(encoding="utf-8").strip()
        if token:
            settings.server.admin_token = token
            return token
    token = secrets.token_urlsafe(24)
    path.write_text(token, encoding="utf-8")
    settings.server.admin_token = token
    return token
