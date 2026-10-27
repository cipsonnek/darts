"""Shared API dependencies: service access and protection of administrative endpoints."""

from __future__ import annotations

import hmac
import ipaddress

from fastapi import Depends, HTTPException, Request

from backend.services.auth_service import SESSION_COOKIE, AuthService
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


def auth(request: Request) -> AuthService:
    return request.app.state.auth


def require_operator(request: Request, svc: AuthService = Depends(auth)) -> dict:
    """Operator panel (central server): a signed-in operator account (session cookie)."""
    user = svc.user_for_token(request.cookies.get(SESSION_COOKIE))
    if not user:
        raise HTTPException(status_code=401, detail="Zaloguj się do panelu operatora.")
    return user


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
    # A central server sits behind a reverse proxy on a public host: "from localhost" says
    # nothing about who is calling, so it always wants the token.
    if cfg.mode == "central" and mode == "localhost":
        mode = "token"
    if mode == "off":
        return
    if mode == "localhost" and _is_local(request):
        return
    token = request.headers.get("x-admin-token") or ""
    expected = cfg.server.admin_token or ""
    if not expected or not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="admin token required (header X-Admin-Token)")
