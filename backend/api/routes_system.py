"""Health, system information, diagnostics, logs and settings."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from backend import __version__
from backend.api import deps
from backend.api.schemas import UiSettingsIn, VisionSettingsPatch
from backend.database.models import Setting
from backend.logging_setup import RING
from backend.settings import AppSettings, save_runtime_overrides
from vision.config import VisionConfig

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health(request_settings: AppSettings = Depends(deps.settings), vision=Depends(deps.vision),
           games=Depends(deps.games)) -> dict[str, Any]:
    cams = vision.manager.health() if vision.manager else []
    connected = sum(1 for c in cams if c["connected"])
    calibrated = len(vision.engine.calibrated_cameras) if vision.engine else 0
    db_ok = games.db.healthy()
    status = "ok"
    if not db_ok or connected == 0:
        status = "down" if connected == 0 and not db_ok else "degraded"
    elif connected < len(cams) or calibrated < min(2, len(cams)):
        status = "degraded"
    return {"status": status, "version": __version__, "mode": request_settings.mode,
            "cameras_connected": connected, "cameras_total": len(cams), "cameras_calibrated": calibrated,
            "database": "ok" if db_ok else "unavailable",
            "engine_state": vision.engine.state.value if vision.engine else None}


@router.get("/system")
def system(vision=Depends(deps.vision)) -> dict[str, Any]:
    return vision.diagnostics()


@router.get("/diagnostics")
def diagnostics(vision=Depends(deps.vision)) -> dict[str, Any]:
    d = vision.diagnostics()
    d["detection_debug"] = vision.debug_snapshot()
    d["calibration"] = vision.calibration_overall()
    return d


@router.get("/logs")
def logs(level: str | None = Query(None, pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$"),
         logger: str | None = Query(None, max_length=64), text: str | None = Query(None, max_length=100),
         after: int = 0, limit: int = Query(200, ge=1, le=2000)) -> list[dict]:
    return RING.query(level, logger, limit, after, text)


@router.get("/events")
def events(limit: int = Query(200, ge=1, le=2000), type: str | None = Query(None, max_length=32),
           games=Depends(deps.games)) -> list[dict]:
    return games.event_log(limit, type)


@router.get("/settings")
def get_settings(cfg: AppSettings = Depends(deps.settings), games=Depends(deps.games)) -> dict[str, Any]:
    with games.db.session() as s:
        ui = {row.key: row.value for row in s.scalars(select(Setting))}
    v = cfg.vision.model_dump()
    return {"mode": cfg.mode, "server": {"admin_auth": cfg.server.admin_auth, "port": cfg.server.port},
            "vision": {k: v[k] for k in ("board", "motion", "detection", "fusion", "scoring", "tracking",
                                         "validation", "performance", "recording")},
            "database": {"url": games.db.safe_url}, "ui": ui}


@router.put("/settings/vision", dependencies=[Depends(deps.require_admin)])
def put_vision_settings(body: VisionSettingsPatch, cfg: AppSettings = Depends(deps.settings),
                        vision=Depends(deps.vision)) -> dict[str, Any]:
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    merged = cfg.vision.model_dump()
    for k, v in patch.items():
        merged[k] = {**merged[k], **v}
    try:
        new = VisionConfig.model_validate(merged)
    except Exception as exc:  # noqa: BLE001 - surface validation errors to the client
        raise HTTPException(422, f"invalid settings: {exc}") from exc
    # Apply in place (the engine reads its config live).
    for k in patch:
        setattr(cfg.vision, k, getattr(new, k))
    if vision.engine is not None:
        vision.engine.config = cfg.vision
    save_runtime_overrides(cfg, {"vision": patch})
    restart = "board" in patch
    return {"saved": True, "restart_required": restart, "vision": {k: getattr(cfg.vision, k).model_dump() for k in patch}}


@router.put("/settings/ui/{key}")
def put_ui_setting(key: str, body: UiSettingsIn, games=Depends(deps.games)) -> dict[str, Any]:
    if not key.replace("_", "").replace("-", "").isalnum() or len(key) > 64:
        raise HTTPException(422, "invalid key")
    import json

    if len(json.dumps(body.value)) > 64_000:
        raise HTTPException(413, "value too large")
    with games.db.session() as s:
        row = s.get(Setting, key)
        if row is None:
            s.add(Setting(key=key, value=body.value))
        else:
            row.value = body.value
    return {"key": key, "value": body.value}


@router.get("/admin/check", dependencies=[Depends(deps.require_admin)])
def admin_check() -> dict[str, bool]:
    return {"admin": True}
