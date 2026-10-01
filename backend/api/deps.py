"""Shared API dependencies: service access and protection of administrative endpoints."""

from __future__ import annotations

import hmac
import ipaddress

from fastapi import Depends, HTTPException, Request

from backend.services.game_service import GameService
from backend.services.stats_service import StatsService
from backend.services.vision_service import VisionService
from backend.settings import AppSettings


def settings(request: Request) -> AppSettings:
    return request.app.state.settings


def vision(request: Request) -> VisionService:
    return request.app.state.vision


def games(request: Request) -> GameService:
    return request.app.state.games


def stats(request: Request) -> StatsService:
    return request.app.state.stats


def _is_local(request: Request) -> bool:
    host = request.client.host if request.client else ""
    if host in ("testclient", "localhost"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def require_admin(request: Request, cfg: AppSettings = Depends(settings)) -> None:
    """Administrative endpoints: calibration writes, camera/config changes, deletions,
    device probing. Policy from ``server.admin_auth``."""
    mode = cfg.server.admin_auth
    if mode == "off":
        return
    if mode == "localhost" and _is_local(request):
        return
    token = request.headers.get("x-admin-token") or ""
    expected = cfg.server.admin_token or ""
    if not expected or not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="admin token required (header X-Admin-Token)")
