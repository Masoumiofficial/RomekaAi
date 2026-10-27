from __future__ import annotations


from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth_context
from app.db.models import FitnessProfile, Goal, UserProfile
from app.db.session import get_db

router = APIRouter(prefix="/profile", tags=["profile"])


class ProfileIn(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)
    timezone: str | None = Field(default=None, max_length=64)
    locale: str | None = Field(default=None, max_length=10)
    wake_time: int | None = Field(default=None, ge=0, le=1439)
    sleep_time: int | None = Field(default=None, ge=1, le=1440)
    work_start: int | None = Field(default=None, ge=0, le=1440)
    work_end: int | None = Field(default=None, ge=0, le=1440)
    commute_minutes: int | None = Field(default=None, ge=0, le=300)
    meal_windows: list[dict] | None = None
    focus_peak_start: int | None = Field(default=None, ge=0, le=1440)
    focus_peak_end: int | None = Field(default=None, ge=0, le=1440)
    daily_focus_capacity_min: int | None = Field(default=None, ge=30, le=900)
    buffer_pct: int | None = Field(default=None, ge=0, le=50)
    energy_drains: list[str] | None = None
    energy_boosters: list[str] | None = None
    health_consent: bool | None = None
    goals: list[str] | None = None


def _serialize_profile(p: UserProfile) -> dict:
    return {
        "wake_time": p.wake_time, "sleep_time": p.sleep_time,
        "work_start": p.work_start, "work_end": p.work_end,
        "commute_minutes": p.commute_minutes, "meal_windows": p.meal_windows,
        "focus_peak_start": p.focus_peak_start, "focus_peak_end": p.focus_peak_end,
        "daily_focus_capacity_min": p.daily_focus_capacity_min,
        "buffer_pct": p.buffer_pct, "energy_drains": p.energy_drains,
        "energy_boosters": p.energy_boosters, "health_consent": p.health_consent,
        "onboarding_completed": p.onboarding_completed,
    }


@router.get("")
def get_profile(ctx: AuthContext = Depends(get_auth_context),
                db: Session = Depends(get_db)) -> dict:
    p = db.query(UserProfile).filter(UserProfile.user_id == ctx.user.id).first()
    return {"ok": True, "user": {"id": ctx.user.id, "email": ctx.user.email,
                                 "display_name": ctx.user.display_name,
                                 "timezone": ctx.user.timezone, "locale": ctx.user.locale},
            "profile": _serialize_profile(p) if p else None, "csrf_token": ctx.session.csrf}


@router.put("")
def update_profile(payload: ProfileIn, ctx: AuthContext = Depends(get_auth_context),
                   db: Session = Depends(get_db)) -> dict:
    p = db.query(UserProfile).filter(UserProfile.user_id == ctx.user.id).first()
    if p is None:
        p = UserProfile(user_id=ctx.user.id)
        db.add(p)
        db.flush()
    data = payload.model_dump(exclude_none=True)
    user_fields = {k: data.pop(k) for k in ("display_name", "timezone", "locale") if k in data}
    for k, v in user_fields.items():
        setattr(ctx.user, k, v)
    goals = data.pop("goals", None)
    for k, v in data.items():
        setattr(p, k, v)
    if goals:
        for g in goals[:10]:
            db.add(Goal(user_id=ctx.user.id, title=str(g)[:300],
                        horizon="long_term", priority=2))
    p.onboarding_completed = True
    db.flush()
    return {"ok": True, "profile": _serialize_profile(p)}


class FitnessIn(BaseModel):
    age: int | None = Field(default=None, ge=10, le=100)
    height_cm: float | None = Field(default=None, ge=80, le=250)
    weight_kg: float | None = Field(default=None, ge=20, le=400)
    goal: str | None = Field(default=None, max_length=30)
    experience: str | None = Field(default=None, max_length=30)
    days_per_week: int | None = Field(default=None, ge=1, le=7)
    session_minutes: int | None = Field(default=None, ge=15, le=240)
    equipment: list[str] | None = None
    injuries: list[str] | None = None
    food_preferences: list[str] | None = None
    allergies: list[str] | None = None
    food_budget: float | None = None


@router.get("/fitness")
def get_fitness(ctx: AuthContext = Depends(get_auth_context),
                db: Session = Depends(get_db)) -> dict:
    f = db.query(FitnessProfile).filter(FitnessProfile.user_id == ctx.user.id).first()
    if f is None:
        return {"ok": True, "fitness": None}
    return {"ok": True, "fitness": {c.name: getattr(f, c.name) for c in FitnessProfile.__table__.columns}}


@router.put("/fitness")
def update_fitness(payload: FitnessIn, ctx: AuthContext = Depends(get_auth_context),
                   db: Session = Depends(get_db)) -> dict:
    f = db.query(FitnessProfile).filter(FitnessProfile.user_id == ctx.user.id).first()
    if f is None:
        f = FitnessProfile(user_id=ctx.user.id)
        db.add(f)
        db.flush()
    for k, v in payload.model_dump(exclude_none=True).items():
        setattr(f, k, v)
    db.flush()
    return {"ok": True, "fitness": {c.name: getattr(f, c.name) for c in FitnessProfile.__table__.columns}}
