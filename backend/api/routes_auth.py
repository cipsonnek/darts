"""Sign-in for the operator panel (central server) and the service PIN of a board.

``/api/auth/*`` exists only on the central server: operators sign in with a username and
password and get an HttpOnly session cookie. Accounts are created on the server with
``python -m backend.users``.

``/api/service/unlock`` exists only on a board: venue staff type the service PIN to open
calibration; the response carries the admin token the UI then sends with admin actions.
"""

from __future__ import annotations

import hmac
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from backend.api import deps
from backend.services.auth_service import SESSION_COOKIE, SESSION_DAYS, AuthError, AuthService, LoginThrottle
from backend.settings import AppSettings


class LoginIn(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=256)


class PasswordIn(BaseModel):
    old_password: str = Field(..., max_length=256)
    new_password: str = Field(..., max_length=256)


class PinIn(BaseModel):
    pin: str = Field(..., min_length=1, max_length=32)


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


def _set_cookie(request: Request, response: Response, token: str) -> None:
    response.set_cookie(SESSION_COOKIE, token, max_age=SESSION_DAYS * 86400, httponly=True, samesite="strict",
                        secure=request.url.scheme == "https", path="/")


# --------------------------------------------------------------------------- operator panel
auth = APIRouter(prefix="/api/auth", tags=["auth"])


@auth.post("/login")
def login(body: LoginIn, request: Request, response: Response, svc: AuthService = Depends(deps.auth)) -> dict[str, Any]:
    try:
        token, user = svc.login(body.username, body.password, _ip(request))
    except PermissionError as e:
        raise HTTPException(429, str(e)) from e
    except AuthError as e:
        raise HTTPException(401, str(e)) from e
    _set_cookie(request, response, token)
    return {"user": user}


@auth.post("/logout", status_code=204)
def logout(request: Request, response: Response, svc: AuthService = Depends(deps.auth)) -> None:
    svc.logout(request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(SESSION_COOKIE, path="/")


@auth.get("/me")
def me(user: dict = Depends(deps.require_operator)) -> dict[str, Any]:
    return {"user": user}


@auth.post("/password")
def change_password(body: PasswordIn, request: Request, response: Response, user: dict = Depends(deps.require_operator),
                    svc: AuthService = Depends(deps.auth)) -> dict[str, Any]:
    try:
        svc.change_password(user["id"], body.old_password, body.new_password)
        token, user = svc.login(user["username"], body.new_password, _ip(request))
    except AuthError as e:
        raise HTTPException(400, str(e)) from e
    _set_cookie(request, response, token)
    return {"user": user}


# --------------------------------------------------------------------------- board service PIN
service = APIRouter(prefix="/api/service", tags=["service"])
_pin_throttle = LoginThrottle(limit=5, window_s=120)


@service.post("/unlock")
def unlock(body: PinIn, request: Request, cfg: AppSettings = Depends(deps.settings)) -> dict[str, str]:
    key = f"ip:{_ip(request)}"
    wait = _pin_throttle.retry_after(key)
    if wait:
        raise HTTPException(429, f"Za dużo błędnych prób. Spróbuj za {wait} s.")
    expected = cfg.server.service_pin or ""
    if not expected or not hmac.compare_digest(body.pin.strip(), expected):
        _pin_throttle.fail(key)
        raise HTTPException(401, "Nieprawidłowy PIN.")
    _pin_throttle.reset(key)
    return {"admin_token": cfg.server.admin_token or ""}
