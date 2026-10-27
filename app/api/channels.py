"""Messaging webhooks. Verification + allowlist happen BEFORE any core call."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agents.orchestrator import log_security_event
from app.api.deps import AuthContext, get_auth_context, require_role
from app.channels.bale import BaleAdapter
from app.channels.telegram import TelegramAdapter
from app.config import Settings, get_settings
from app.core.errors import PermissionDenied
from app.db.models import ChannelIdentity
from app.db.session import get_db

router = APIRouter(prefix="/channels", tags=["channels"])


@router.get("/status")
def channel_status(settings: Settings = Depends(get_settings)) -> dict:
    tg, bale = TelegramAdapter(settings), BaleAdapter(settings)
    return {"ok": True, "telegram": {"configured": tg.available, "verified_live": False},
            "bale": {"configured": bale.available, "verified_live": False,
                     "official_docs": "https://docs.bale.ai/"}}


@router.post("/telegram/webhook")
async def telegram_webhook(request: Request, db: Session = Depends(get_db),
                           settings: Settings = Depends(get_settings)) -> dict:
    tg = TelegramAdapter(settings)
    if not tg.verify(dict(request.headers)):
        log_security_event(db, event_type="invalid_webhook_secret", channel="telegram",
                           detail="missing or bad secret header")
        raise PermissionDenied("امضای وبحوک معتبر نیست.")
    try:
        payload = await request.json()
    except Exception:
        return {"ok": False}
    result = tg.handle_update(db, payload)
    return {"ok": result.ok, "text": result.text, "data": result.data}


@router.post("/bale/webhook")
async def bale_webhook(request: Request, db: Session = Depends(get_db),
                       settings: Settings = Depends(get_settings)) -> dict:
    bale = BaleAdapter(settings)
    if not bale.verify(dict(request.query_params)):
        log_security_event(db, event_type="invalid_webhook_secret", channel="bale",
                           detail="bad secret query parameter")
        raise PermissionDenied("امضای وبحوک معتبر نیست.")
    try:
        payload = await request.json()
    except Exception:
        return {"ok": False}
    result = bale.handle_update(db, payload)
    return {"ok": result.ok, "text": result.text, "data": result.data}


class IdentityIn(BaseModel):
    channel: str
    external_id: str
    user_id: int | None = None
    is_allowed: bool = True


@router.post("/identities")
def add_identity(p: IdentityIn, ctx: AuthContext = Depends(require_role("owner")),
                 db: Session = Depends(get_db)) -> dict:
    if p.channel not in ("telegram", "bale"):
        from app.core.errors import ValidationFailed
        raise ValidationFailed("کانال نامعتبر است.")
    uid = p.user_id or ctx.user.id
    if uid != ctx.user.id and ctx.user.role != "owner":
        raise PermissionDenied("نمیتوانید برای کاربر دیگر هویت تعریف کنید.")
    row = (db.query(ChannelIdentity).filter(ChannelIdentity.channel == p.channel,
                                            ChannelIdentity.external_id == p.external_id).first())
    if row is None:
        row = ChannelIdentity(user_id=uid, channel=p.channel, external_id=p.external_id)
        db.add(row)
    row.user_id = uid
    row.is_allowed = p.is_allowed
    db.flush()
    return {"ok": True, "item": {"id": row.id, "channel": row.channel,
                                  "external_id": row.external_id, "user_id": row.user_id,
                                  "is_allowed": row.is_allowed}}


@router.get("/identities")
def list_identities(ctx: AuthContext = Depends(get_auth_context),
                    db: Session = Depends(get_db)) -> dict:
    rows = (db.query(ChannelIdentity).filter(ChannelIdentity.user_id == ctx.user.id).all())
    return {"ok": True, "items": [{"id": r.id, "channel": r.channel,
                                    "external_id": r.external_id,
                                    "is_allowed": r.is_allowed} for r in rows]}
