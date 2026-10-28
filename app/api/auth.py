from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Request, Response
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

Email = Annotated[str, StringConstraints(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", min_length=5, max_length=320)]
from sqlalchemy.orm import Session

from app.api.deps import (SESSION_COOKIE, AuthContext, get_auth_context,
                          get_signer, session_cookie_kwargs)
from app.config import Settings, get_settings
from app.core.errors import Conflict, PermissionDenied, Unauthorized
from app.core.security import SessionSigner, hash_password, new_csrf_token, verify_password
from app.db.models import User, UserProfile
from app.db.session import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterIn(BaseModel):
    email: Email
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(default="", max_length=120)
    timezone: str = Field(default="Asia/Tehran", max_length=64)
    locale: str = Field(default="fa", max_length=10)


class LoginIn(BaseModel):
    email: Email
    password: str = Field(max_length=128)


def _set_session(request: Request, response: Response, user: User,
                 signer: SessionSigner, settings: Settings) -> tuple[str, str]:
    csrf = new_csrf_token()
    token = signer.create(user.id, csrf)
    response.set_cookie(
        SESSION_COOKIE, token, max_age=settings.SESSION_MAX_AGE_SECONDS,
        httponly=True, path="/", **session_cookie_kwargs(request, settings),
    )
    return csrf, token


def _public_user(u: User) -> dict:
    return {"id": u.id, "email": u.email, "display_name": u.display_name,
            "timezone": u.timezone, "locale": u.locale, "role": u.role}


def _create_user(db: Session, *, email: str, password: str, display_name: str,
                 timezone: str, locale: str) -> User:
    email = email.strip().lower()
    if db.query(User).filter(User.email == email).first():
        raise Conflict("این ایمیل قبلاً ثبت شده است.")
    user = User(email=email, password_hash=hash_password(password),
                display_name=display_name or email.split("@")[0],
                timezone=timezone, locale=locale, role="owner")
    db.add(user)
    db.flush()
    db.add(UserProfile(user_id=user.id))
    db.flush()
    return user


@router.post("/register")
def register(payload: RegisterIn, request: Request, response: Response, db: Session = Depends(get_db),
             signer: SessionSigner = Depends(get_signer),
             settings: Settings = Depends(get_settings)) -> dict:
    user = _create_user(db, email=payload.email, password=payload.password,
                        display_name=payload.display_name, timezone=payload.timezone,
                        locale=payload.locale)
    csrf, token = _set_session(request, response, user, signer, settings)
    return {"ok": True, "user": _public_user(user), "csrf_token": csrf, "session_token": token}


@router.post("/login")
def login(payload: LoginIn, request: Request, response: Response,
          db: Session = Depends(get_db), signer: SessionSigner = Depends(get_signer),
          settings: Settings = Depends(get_settings)) -> dict:
    email = payload.email.strip().lower()
    user = db.query(User).filter(User.email == email, User.is_active.is_(True)).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        from app.agents.orchestrator import log_security_event
        log_security_event(db, event_type="failed_login", channel="web",
                           detail=f"email={email}", ip=request.client.host if request.client else "")
        raise Unauthorized("ایمیل یا رمز عبور نادرست است.")
    csrf, token = _set_session(request, response, user, signer, settings)
    return {"ok": True, "user": _public_user(user), "csrf_token": csrf, "session_token": token}


@router.post("/logout")
def logout(request: Request, response: Response,
           settings: Settings = Depends(get_settings)) -> dict:
    flags = session_cookie_kwargs(request, settings)
    response.delete_cookie(SESSION_COOKIE, path="/", samesite=flags["samesite"],
                           secure=flags["secure"], httponly=True)
    return {"ok": True}


@router.get("/me")
def me(ctx: AuthContext = Depends(get_auth_context)) -> dict:
    return {"ok": True, "user": _public_user(ctx.user), "csrf_token": ctx.session.csrf}


@router.post("/guest")
def guest(request: Request, response: Response, db: Session = Depends(get_db),
          signer: SessionSigner = Depends(get_signer),
          settings: Settings = Depends(get_settings)) -> dict:
    """Dev-only, isolated one-click account. Never available in production."""
    if settings.is_production or not settings.ROMKA_AUTO_DEMO:
        raise PermissionDenied("ورود مهمان فقط در محیط توسعه مجاز است.")
    user = _create_user(db, email=f"guest-{secrets.token_hex(8)}@romka.local",
                        password=secrets.token_urlsafe(32), display_name="مهمان رومکا",
                        timezone="Asia/Tehran", locale="fa")
    csrf, token = _set_session(request, response, user, signer, settings)
    return {"ok": True, "user": _public_user(user), "csrf_token": csrf,
            "session_token": token,
            "note": "حساب موقت توسعه؛ دادهها فقط برای این نشست ایزوله است."}
