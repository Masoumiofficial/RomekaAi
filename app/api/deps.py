"""Shared API dependencies. Every personal-data query is scoped by user_id."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from functools import lru_cache

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.core.errors import PermissionDenied, Unauthorized
from app.core.security import SessionData, SessionSigner
from app.db.models import User
from app.db.session import get_db

SESSION_COOKIE = "romka_session"


@dataclass(frozen=True)
class AuthContext:
    user: User
    session: SessionData


@lru_cache
def _signer(secret_key: str, max_age: int) -> SessionSigner:
    return SessionSigner(secret_key, max_age)


def get_signer(settings: Settings = Depends(get_settings)) -> SessionSigner:
    return _signer(settings.secret_key, settings.SESSION_MAX_AGE_SECONDS)


def get_auth_context(
    request: Request,
    db: Session = Depends(get_db),
    signer: SessionSigner = Depends(get_signer),
) -> AuthContext:
    token = request.cookies.get(SESSION_COOKIE, "")
    data = signer.read(token)
    if data is None:
        raise Unauthorized("نشست معتبر نیست. لطفاً دوباره وارد شوید.")
    user = db.query(User).filter(User.id == data.user_id, User.is_active.is_(True)).first()
    if user is None:
        raise Unauthorized("کاربر یافت نشد.")
    return AuthContext(user=user, session=data)


def optional_auth_context(
    request: Request,
    db: Session = Depends(get_db),
    signer: SessionSigner = Depends(get_signer),
) -> AuthContext | None:
    token = request.cookies.get(SESSION_COOKIE, "")
    if not token:
        return None
    data = signer.read(token)
    if data is None:
        return None
    user = db.query(User).filter(User.id == data.user_id, User.is_active.is_(True)).first()
    return AuthContext(user=user, session=data) if user else None


def require_role(*roles: str):
    def checker(ctx: AuthContext = Depends(get_auth_context)) -> AuthContext:
        if ctx.user.role not in roles:
            raise PermissionDenied("نقش کاربر برای این عملیات کافی نیست.")
        return ctx
    return checker


class SlidingWindowRateLimiter:
    """In-process limiter. On a multi-worker VPS, replace with Redis (documented)."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, window: float = 60.0) -> bool:
        now = time.monotonic()
        with self._lock:
            bucket = self._hits[key]
            while bucket and bucket[0] <= now - window:
                bucket.popleft()
            if len(bucket) >= limit:
                return False
            bucket.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


rate_limiter = SlidingWindowRateLimiter()
