"""Health, honest runtime status, settings, budget, audit log and action approval."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.ai.router import AIRouter
from app.api.deps import AuthContext, get_auth_context, require_role
from app.config import Settings, get_settings
from app.core.action_engine import action_engine
from app.core.errors import NotFound, ValidationFailed
from app.db.models import ActionRecord, AIUsage, SecurityEvent, Setting
from app.db.session import get_db
from app.memory.engine import memory_engine
from app.skills.registry import skill_registry

router = APIRouter(tags=["system"])

VERSION = "0.2.4"


def _demo_status(settings: Settings, request: Request) -> dict:
    """Public, non-secret: is a demo account actually usable here?"""
    if settings.is_production or not settings.ROMKA_AUTO_DEMO:
        return {"enabled": False, "ready": False}
    state = getattr(request.app.state, "demo_login", None) or {}
    out = {"enabled": True, "ready": bool(state.get("ready")),
           "email": settings.ROMKA_DEMO_EMAIL,
           "note": "DEV-only account; the password is never returned by the API."}
    if state.get("reason"):
        out["reason"] = state["reason"]
    return out


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    """Liveness + DB connectivity. No secrets, no personal data."""
    try:
        db.execute(__import__("sqlalchemy").text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    return {"ok": db_ok, "status": "healthy" if db_ok else "degraded",
            "version": VERSION, "time": datetime.now(timezone.utc).isoformat()}


@router.get("/status")
def status(request: Request, settings: Settings = Depends(get_settings),
           db: Session = Depends(get_db)) -> dict:
    router_ = AIRouter(db, user_id=None, settings=settings)
    from app.ai.runtime_state import verification_state
    from app.channels.bale import BaleAdapter
    from app.channels.telegram import TelegramAdapter
    tg, bale = TelegramAdapter(settings), BaleAdapter(settings)
    return {"ok": True, "version": VERSION, "environment": settings.ENVIRONMENT,
            "database": "sqlite" if settings.DATABASE_URL.startswith("sqlite") else "postgresql",
            "runtime_warnings": settings.runtime_warnings(),
            "providers": router_.configured_status(),
            "provider_verification": verification_state(),
            "demo_login": _demo_status(settings, request),
            "channels": {
                "telegram": {"configured": tg.available,
                             "verified_live": False,
                             "note": "Webhook verification/allowlist implemented and unit-tested; no live token here."},
                "bale": {"configured": bale.available, "verified_live": False,
                         "docs": "https://docs.bale.ai/",
                         "note": "API shape verified from official docs; no live token here."},
            },
            "budget": router_.budget_state(),
            "skills_tracked": len(skill_registry.catalog["candidates"])}


class SettingIn(BaseModel):
    key: str
    value: dict


@router.get("/settings")
def get_settings_api(ctx: AuthContext = Depends(get_auth_context),
                     db: Session = Depends(get_db)) -> dict:
    rows = db.query(Setting).filter(Setting.user_id == ctx.user.id).all()
    return {"ok": True, "items": {r.key: r.value for r in rows}}


@router.put("/settings")
def put_settings(p: SettingIn, ctx: AuthContext = Depends(get_auth_context),
                 db: Session = Depends(get_db)) -> dict:
    if not p.key or len(p.key) > 100:
        raise ValidationFailed("کلید تنظیمات نامعتبر است.")
    row = (db.query(Setting).filter(Setting.user_id == ctx.user.id,
                                    Setting.key == p.key).first())
    if row is None:
        row = Setting(user_id=ctx.user.id, key=p.key, value={})
        db.add(row)
    row.value = p.value
    db.flush()
    return {"ok": True, "key": p.key, "value": row.value}


@router.get("/budget")
def budget(ctx: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db),
           settings: Settings = Depends(get_settings)) -> dict:
    r = AIRouter(db, user_id=ctx.user.id, settings=settings)
    recent = (db.query(AIUsage).filter(AIUsage.user_id == ctx.user.id)
              .order_by(AIUsage.id.desc()).limit(20).all())
    return {"ok": True, "state": r.budget_state(),
            "recent": [{"provider": x.provider, "model": x.model, "status": x.status,
                        "cost_usd": x.cost_usd, "latency_ms": x.latency_ms,
                        "created_at": x.created_at.isoformat()} for x in recent]}


@router.get("/security-events")
def security_events(ctx: AuthContext = Depends(get_auth_context),
                    db: Session = Depends(get_db)) -> dict:
    rows = (db.query(SecurityEvent).filter(SecurityEvent.user_id == ctx.user.id)
            .order_by(SecurityEvent.id.desc()).limit(100).all())
    return {"ok": True, "items": [{"id": r.id, "event_type": r.event_type,
                                    "channel": r.channel, "detail": r.detail,
                                    "created_at": r.created_at.isoformat()} for r in rows]}


@router.get("/actions")
def actions(ctx: AuthContext = Depends(get_auth_context),
            db: Session = Depends(get_db)) -> dict:
    rows = (db.query(ActionRecord).filter(ActionRecord.user_id == ctx.user.id)
            .order_by(ActionRecord.id.desc()).limit(100).all())
    return {"ok": True, "items": [_action(r) for r in rows]}


def _action(r: ActionRecord) -> dict:
    return {"id": r.id, "requester": r.requester, "goal": r.goal, "tool": r.tool,
            "inputs": r.inputs, "risk_level": r.risk_level, "status": r.status,
            "result": r.result, "error": r.error,
            "created_at": r.created_at.isoformat()}


@router.post("/actions/{action_id}/approve")
def approve_action(action_id: int, approve: bool = True,
                   ctx: AuthContext = Depends(require_role("owner")),
                   db: Session = Depends(get_db)) -> dict:
    row = (db.query(ActionRecord).filter(ActionRecord.id == action_id,
                                         ActionRecord.user_id == ctx.user.id).first())
    if row is None:
        raise NotFound("اقدام پیدا نشد.")
    if not approve:
        row.status = "denied"
        db.flush()
        return {"ok": True, "item": _action(row)}
    if row.status not in ("pending_approval", "approved"):
        raise ValidationFailed("این اقدام قبلاً اجرا یا رد شده است.")
    result = action_engine.execute(db, row, approved=True)
    return {"ok": True, "item": _action(result)}


@router.get("/export")
def export_data(ctx: AuthContext = Depends(get_auth_context),
                db: Session = Depends(get_db)) -> dict:
    """User-controlled data export. Sensitive values are included by design here."""
    from app.db.models import Conversation, Goal, Message, Plan, Project, Task
    uid = ctx.user.id
    return {"ok": True, "generated_at": datetime.now(timezone.utc).isoformat(),
            "warning": "این خروجی حاوی اطلاعات شخصی است؛ در جای امن نگهداری کنید.",
            "data": {
                "memory": memory_engine.export_all(db, user_id=uid),
                "tasks": [{"id": t.id, "title": t.title, "status": t.status,
                           "duration_min": t.duration_min} for t in
                          db.query(Task).filter(Task.user_id == uid).all()],
                "goals": [g.title for g in db.query(Goal).filter(Goal.user_id == uid).all()],
                "projects": [p.name for p in db.query(Project).filter(Project.user_id == uid).all()],
                "conversations": [{"id": c.id, "title": c.title} for c in
                                  db.query(Conversation).filter(Conversation.user_id == uid).all()],
                "messages": [{"role": m.role, "content": m.content} for m in
                             db.query(Message).join(Conversation)
                             .filter(Conversation.user_id == uid).all()],
                "plans": [{"date": p.date.isoformat(), "version": p.version} for p in
                          db.query(Plan).filter(Plan.user_id == uid).all()],
            }}
