"""Life Planner API — the deterministic engine is the single source of truth."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth_context
from app.core.errors import NotFound, ValidationFailed
from app.core.timeutil import local_minute_to_utc, today_in
from app.db.models import FixedEvent, Plan, Task, UserProfile
from app.db.session import get_db
from app.planning.engine import expand_recurrence, light_day_plan
from app.planning.review import calibration, daily_review, weekly_load
from app.planning.service import (
    complete_task, generate, load_fixed, load_tasks, constraints_from_profile,
    parse_natural_request,
)

router = APIRouter(prefix="/planner", tags=["planner"])


def _day(value: str | None, tz_name: str = "UTC") -> date:
    if not value:
        return today_in(tz_name)
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationFailed("تاریخ باید بهصورت YYYY-MM-DD باشد.") from exc


class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=400)
    duration_min: int = Field(default=60, ge=5, le=720)
    priority: int = Field(default=3, ge=1, le=5)
    energy: str = Field(default="medium", pattern="^(low|medium|high)$")
    kind: str = Field(default="focus", pattern="^(focus|admin|personal)$")
    project_id: int | None = None
    deadline_min: int | None = Field(default=None, ge=0, le=1440)
    earliest_start_min: int | None = Field(default=None, ge=0, le=1440)
    latest_end_min: int | None = Field(default=None, ge=0, le=1440)
    depends_on: list[int] = Field(default_factory=list)
    must_do: bool = False
    deferrable: bool = True
    recurrence_rule: str | None = Field(default=None, max_length=200)


class EventIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    start_min: int = Field(ge=0, le=1439)
    end_min: int = Field(ge=1, le=1440)
    category: str = Field(default="meeting", pattern="^(meeting|workout|meal|commute|personal)$")


class GenerateIn(BaseModel):
    date: str | None = None
    energy_mode: str = Field(default="normal", pattern="^(normal|low)$")
    # Set false to see the raw estimates without the measured correction.
    apply_calibration: bool = True


class ReplanIn(BaseModel):
    date: str | None = None
    energy_mode: str = Field(default="normal", pattern="^(normal|low)$")
    extended_events: dict[str, int] = Field(default_factory=dict)
    completed_task_ids: list[int] = Field(default_factory=list)
    replan_from_min: int | None = Field(default=None, ge=0, le=1440)


class IntakeIn(BaseModel):
    text: str = Field(min_length=3, max_length=4000)
    date: str | None = None
    save: bool = True
    energy_mode: str = Field(default="normal", pattern="^(normal|low)$")


def _task(row: Task) -> dict:
    return {"id": row.id, "title": row.title, "duration_min": row.duration_min,
            "actual_min": row.actual_min,
            "priority": row.priority, "energy": row.energy, "kind": row.kind,
            "project_id": row.project_id, "status": row.status,
            "depends_on": row.depends_on, "must_do": row.must_do,
            "deferrable": row.deferrable, "recurrence_rule": row.recurrence_rule,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None}


@router.get("/tasks")
def tasks(ctx: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)) -> dict:
    rows = (db.query(Task).filter(Task.user_id == ctx.user.id)
            .order_by(Task.priority, Task.id).all())
    return {"ok": True, "items": [_task(r) for r in rows], "count": len(rows)}


@router.post("/tasks")
def create_task(p: TaskIn, ctx: AuthContext = Depends(get_auth_context),
                db: Session = Depends(get_db)) -> dict:
    if p.recurrence_rule:
        try:
            expand_recurrence(p.recurrence_rule, date.today(), 1)
        except ValueError as exc:
            raise ValidationFailed(str(exc)) from exc
    data = p.model_dump()
    deadline_min = data.pop("deadline_min", None)
    row = Task(user_id=ctx.user.id, **data)
    if deadline_min is not None:
        row.deadline = local_minute_to_utc(today_in(ctx.user.timezone), deadline_min,
                                           ctx.user.timezone)
    db.add(row)
    db.flush()
    return {"ok": True, "item": _task(row)}


@router.delete("/tasks/{task_id}")
def delete_task(task_id: int, ctx: AuthContext = Depends(get_auth_context),
                db: Session = Depends(get_db)) -> dict:
    row = db.query(Task).filter(Task.id == task_id, Task.user_id == ctx.user.id).first()
    if row is None:
        raise NotFound("وظیفه پیدا نشد.")
    db.delete(row)
    db.flush()
    return {"ok": True}


class CompleteIn(BaseModel):
    actual_minutes: int | None = Field(default=None, ge=1, le=1440,
                                       description="مدت واقعی انجام کار، برای کالیبراسیون")
    note: str = Field(default="", max_length=400)


@router.post("/tasks/{task_id}/complete")
def finish_task(task_id: int, payload: CompleteIn | None = None,
                ctx: AuthContext = Depends(get_auth_context),
                db: Session = Depends(get_db)) -> dict:
    """Complete a task and optionally record the REAL duration.

    The estimate is preserved, so the response shows both numbers and the
    calibration state — no silent rewriting of history.
    """
    payload = payload or CompleteIn()
    row = complete_task(db, user_id=ctx.user.id, task_id=task_id,
                        actual_minutes=payload.actual_minutes, note=payload.note,
                        day=today_in(ctx.user.timezone))
    return {"ok": True, "item": _task(row), "calibration": calibration(db, ctx.user.id)}


@router.get("/review")
def review(day: str | None = Query(default=None),
           mode: str = Query(default="night", pattern="^(morning|night)$"),
           ctx: AuthContext = Depends(get_auth_context),
           db: Session = Depends(get_db)) -> dict:
    """Morning preview / evening review built only from stored rows."""
    return daily_review(db, user_id=ctx.user.id, day=_day(day, ctx.user.timezone), mode=mode)


@router.get("/week")
def week(day: str | None = Query(default=None), days: int = Query(default=7, ge=3, le=31),
         ctx: AuthContext = Depends(get_auth_context),
         db: Session = Depends(get_db)) -> dict:
    """Real loads for the last N days (empty days mean 'nothing recorded')."""
    return weekly_load(db, user_id=ctx.user.id, end_day=_day(day, ctx.user.timezone), days=days)


@router.get("/calibration")
def calibration_state(ctx: AuthContext = Depends(get_auth_context),
                      db: Session = Depends(get_db)) -> dict:
    """Is the estimate correction active, and on how much evidence?"""
    return {"ok": True, "calibration": calibration(db, ctx.user.id)}


@router.get("/events")
def events(day: str | None = Query(default=None),
           ctx: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)) -> dict:
    d = _day(day, ctx.user.timezone)
    rows = (db.query(FixedEvent).filter(FixedEvent.user_id == ctx.user.id, FixedEvent.date == d)
            .order_by(FixedEvent.start_min).all())
    return {"ok": True, "items": [{"id": r.id, "title": r.title, "start_min": r.start_min,
                                    "end_min": r.end_min, "category": r.category,
                                    "source": r.source} for r in rows]}


@router.post("/events")
def create_event(p: EventIn, day: str | None = Query(default=None),
                 ctx: AuthContext = Depends(get_auth_context),
                 db: Session = Depends(get_db)) -> dict:
    if p.end_min <= p.start_min:
        raise ValidationFailed("زمان پایان باید بعد از شروع باشد.")
    row = FixedEvent(user_id=ctx.user.id, date=_day(day, ctx.user.timezone), **p.model_dump())
    db.add(row)
    db.flush()
    return {"ok": True, "item": {"id": row.id, "title": row.title}}


@router.get("/today")
def today(day: str | None = Query(default=None),
          ctx: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)) -> dict:
    d = _day(day, ctx.user.timezone)
    plan = (db.query(Plan).filter(Plan.user_id == ctx.user.id, Plan.date == d,
                                  Plan.is_active.is_(True))
            .order_by(Plan.version.desc()).first())
    return {"ok": True, "date": d.isoformat(), "plan": plan.payload if plan else None,
            "plan_db_id": plan.id if plan else None}


@router.post("/generate")
def generate_plan(p: GenerateIn, ctx: AuthContext = Depends(get_auth_context),
                  db: Session = Depends(get_db)) -> dict:
    d = _day(p.date, ctx.user.timezone)
    profile = db.query(UserProfile).filter(UserProfile.user_id == ctx.user.id).first()
    result = generate(db, user_id=ctx.user.id, day=d, profile=profile,
                      energy_mode=p.energy_mode, tz_name=ctx.user.timezone,
                      apply_calibration=p.apply_calibration)
    return {"ok": True, "plan": result}


@router.post("/replan")
def replan_day(p: ReplanIn, ctx: AuthContext = Depends(get_auth_context),
               db: Session = Depends(get_db)) -> dict:
    d = _day(p.date, ctx.user.timezone)
    for k, v in p.extended_events.items():
        if not 0 <= v <= 1440:
            raise ValidationFailed("زمان پایان رویداد نامعتبر است.")
    profile = db.query(UserProfile).filter(UserProfile.user_id == ctx.user.id).first()
    result = generate(
        db, user_id=ctx.user.id, day=d, profile=profile, energy_mode=p.energy_mode,
        replan_from_min=p.replan_from_min,
        extended_events=p.extended_events or None,
        completed_task_ids=[str(x) for x in p.completed_task_ids],
        tz_name=ctx.user.timezone,
    )
    return {"ok": True, "plan": result}


@router.post("/intake")
def intake(p: IntakeIn, ctx: AuthContext = Depends(get_auth_context),
           db: Session = Depends(get_db)) -> dict:
    """Acceptance scenario A: natural language in, real tasks + validated plan out."""
    d = _day(p.date, ctx.user.timezone)
    parsed = parse_natural_request(p.text)
    created_tasks: list[int] = []
    created_events: list[int] = []
    if p.save:
        for t in parsed["tasks"]:
            row = Task(user_id=ctx.user.id, title=t["title"][:400],
                       duration_min=t["duration_min"], priority=t["priority"],
                       energy=t["energy"], kind=t["kind"], planned_for=d)
            db.add(row)
            db.flush()
            created_tasks.append(row.id)
        for e in parsed["fixed"]:
            row = FixedEvent(user_id=ctx.user.id, date=d, title=e["title"][:300],
                             start_min=e["start_min"], end_min=e["end_min"],
                             category=e["category"], source="chat")
            db.add(row)
            db.flush()
            created_events.append(row.id)
        db.flush()
    profile = db.query(UserProfile).filter(UserProfile.user_id == ctx.user.id).first()
    result = generate(db, user_id=ctx.user.id, day=d, profile=profile,
                      energy_mode=p.energy_mode, tz_name=ctx.user.timezone)
    return {"ok": True, "parsed": parsed, "created_task_ids": created_tasks,
            "created_event_ids": created_events, "plan": result}


@router.post("/light-day")
def light_day(p: GenerateIn, ctx: AuthContext = Depends(get_auth_context),
              db: Session = Depends(get_db)) -> dict:
    d = _day(p.date, ctx.user.timezone)
    profile = db.query(UserProfile).filter(UserProfile.user_id == ctx.user.id).first()
    c = constraints_from_profile(profile, d)
    result = light_day_plan(load_tasks(db, ctx.user.id, d, ctx.user.timezone),
                              load_fixed(db, ctx.user.id, d), c)
    return {"ok": True, "alternative": result, "note": "نسخه جایگزین ذخیره نشد؛ فقط پیشنهاد است."}


@router.get("/recurrence")
def recurrence(rule: str = Query(..., max_length=200), count: int = Query(default=8, ge=1, le=365),
               start: str | None = None,
               ctx: AuthContext = Depends(get_auth_context)) -> dict:
    try:
        dates = expand_recurrence(rule, _day(start, ctx.user.timezone), count)
    except ValueError as exc:
        raise ValidationFailed(str(exc)) from exc
    return {"ok": True, "rule": rule, "dates": [x.isoformat() for x in dates],
            "source": "python-dateutil rrule (Apache-2.0 OR BSD-3-Clause)"}
