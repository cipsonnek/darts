"""Operator accounts on the central server: password hashing, sessions, login throttling.

Passwords are hashed with scrypt (standard library, no extra dependency). A session is a
random token handed to the browser in an HttpOnly cookie; only its sha256 is stored, so a
leaked database does not let anyone sign in.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, select

from backend.database import Database
from backend.database.models import OperatorSession, OperatorUser

SESSION_COOKIE = "ds_session"
SESSION_DAYS = 14
MIN_PASSWORD = 8

# scrypt cost: ~50 ms per hash on a small VPS core, 16 MB of memory.
_N, _R, _P = 2**14, 8, 1


class AuthError(ValueError):
    pass


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    b64 = lambda b: base64.b64encode(b).decode()  # noqa: E731
    return f"scrypt${_N}${_R}${_P}${b64(salt)}${b64(dk)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, dk = stored.split("$")
        if algo != "scrypt":
            return False
        want = base64.b64decode(dk)
        got = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p),
                             dklen=len(want))
        return hmac.compare_digest(got, want)
    except (ValueError, TypeError):
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class LoginThrottle:
    """At most ``limit`` failed logins per IP (and per username) within ``window_s``."""

    def __init__(self, limit: int = 8, window_s: float = 300.0) -> None:
        self.limit = limit
        self.window_s = window_s
        self._fails: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str, now: float) -> list[float]:
        xs = [t for t in self._fails.get(key, []) if now - t < self.window_s]
        self._fails[key] = xs
        return xs

    def retry_after(self, *keys: str) -> int:
        now = time.monotonic()
        with self._lock:
            waits = [int(self.window_s - (now - xs[0])) + 1 for k in keys if len(xs := self._recent(k, now)) >= self.limit]
        return max(waits, default=0)

    def fail(self, *keys: str) -> None:
        now = time.monotonic()
        with self._lock:
            for k in keys:
                self._recent(k, now).append(now)

    def reset(self, *keys: str) -> None:
        with self._lock:
            for k in keys:
                self._fails.pop(k, None)


class AuthService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.throttle = LoginThrottle()

    @staticmethod
    def _user_dict(u: OperatorUser) -> dict[str, Any]:
        return {"id": u.id, "username": u.username, "display_name": u.display_name or u.username,
                "active": u.active, "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None}

    # ------------------------------------------------------------------ accounts
    def has_users(self) -> bool:
        with self.db.session() as s:
            return s.scalar(select(OperatorUser.id).limit(1)) is not None

    def list_users(self) -> list[dict[str, Any]]:
        with self.db.session() as s:
            return [self._user_dict(u) for u in s.scalars(select(OperatorUser).order_by(OperatorUser.username))]

    def create_user(self, username: str, password: str, display_name: str = "") -> dict[str, Any]:
        username = username.strip().lower()
        if not username or len(username) > 64:
            raise AuthError("nieprawidłowa nazwa użytkownika")
        self._check_password(password)
        with self.db.session() as s:
            if s.scalar(select(OperatorUser).where(OperatorUser.username == username)):
                raise AuthError(f"użytkownik {username} już istnieje")
            u = OperatorUser(username=username, display_name=display_name.strip(), password_hash=hash_password(password))
            s.add(u)
            s.flush()
            return self._user_dict(u)

    def set_password(self, username: str, password: str) -> None:
        self._check_password(password)
        with self.db.session() as s:
            u = s.scalar(select(OperatorUser).where(OperatorUser.username == username.strip().lower()))
            if not u:
                raise AuthError(f"nie ma użytkownika {username}")
            u.password_hash = hash_password(password)
            # A new password signs out every other session of that user.
            s.execute(delete(OperatorSession).where(OperatorSession.user_id == u.id))

    def set_active(self, username: str, active: bool) -> None:
        with self.db.session() as s:
            u = s.scalar(select(OperatorUser).where(OperatorUser.username == username.strip().lower()))
            if not u:
                raise AuthError(f"nie ma użytkownika {username}")
            u.active = active
            if not active:
                s.execute(delete(OperatorSession).where(OperatorSession.user_id == u.id))

    @staticmethod
    def _check_password(password: str) -> None:
        if len(password) < MIN_PASSWORD:
            raise AuthError(f"hasło musi mieć co najmniej {MIN_PASSWORD} znaków")

    # ------------------------------------------------------------------ sessions
    def login(self, username: str, password: str, ip: str = "") -> tuple[str, dict[str, Any]]:
        username = username.strip().lower()
        keys = (f"ip:{ip}", f"user:{username}")
        wait = self.throttle.retry_after(*keys)
        if wait:
            raise PermissionError(f"Za dużo nieudanych prób. Spróbuj ponownie za {wait} s.")
        with self.db.session() as s:
            u = s.scalar(select(OperatorUser).where(OperatorUser.username == username))
            # Hash even for unknown users so response time does not reveal which names exist.
            ok = verify_password(password, u.password_hash if u else hash_password("x" * MIN_PASSWORD))
            if not u or not ok or not u.active:
                self.throttle.fail(*keys)
                raise AuthError("Nieprawidłowy login lub hasło.")
            self.throttle.reset(*keys)
            now = datetime.now(timezone.utc)
            token = secrets.token_urlsafe(32)
            s.add(OperatorSession(token_hash=_token_hash(token), user_id=u.id, created_at=now,
                                  expires_at=now + timedelta(days=SESSION_DAYS), ip=ip[:64]))
            u.last_login_at = now
            s.execute(delete(OperatorSession).where(OperatorSession.expires_at < now))
            return token, self._user_dict(u)

    def user_for_token(self, token: str | None) -> dict[str, Any] | None:
        if not token:
            return None
        with self.db.session() as s:
            sess = s.get(OperatorSession, _token_hash(token))
            if not sess or _utc(sess.expires_at) < datetime.now(timezone.utc):
                return None
            u = s.get(OperatorUser, sess.user_id)
            return self._user_dict(u) if u and u.active else None

    def logout(self, token: str | None) -> None:
        if not token:
            return
        with self.db.session() as s:
            s.execute(delete(OperatorSession).where(OperatorSession.token_hash == _token_hash(token)))

    def change_password(self, user_id: int, old: str, new: str) -> None:
        with self.db.session() as s:
            u = s.get(OperatorUser, user_id)
            if not u or not verify_password(old, u.password_hash):
                raise AuthError("Obecne hasło jest nieprawidłowe.")
        username = u.username
        self.set_password(username, new)
