"""Bridge between the database/API layer and the pure planning engine.

Also contains a deliberately simple Persian natural-language intake parser. It is
a heuristic: it extracts candidate tasks/events, and the engine (not the parser)
has the final word on feasibility.
"""
from __future__ import annotations

import re
from datetime import date

from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.core.timeutil import utc_to_local_minute
from app.db.base import utcnow
from app.db.models import FixedEvent, Plan, PlanBlock, Task, UserProfile
from app.planning.engine import (
    DayConstraints, FixedBlock, TaskSpec, build_plan, replan,
)

_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_WORD_NUM = {
    "یک": 1, "دو": 2, "سه": 3, "چهار": 4, "پنج": 5, "شش": 6, "هفت": 7, "هشت": 8,
    "نه": 9, "ده": 10, "یازده": 11, "دوازده": 12, "سی": 30, "چهل": 40, "پنجاه": 50,
    "پانزده": 15, "بیست": 20, "بیست و پنج": 25, "چهل و پنج": 45, "نیم": 0.5,
}
_WORKOUT = ("باشگاه", "تمرین", "ورزش", "دویدن", "پیادهروی")
_MEETING = ("جلسه", " meeting", "قرار", "کلاس", "وبینار")
_TIME_RE = re.compile(r"ساعت\s*([0-9۰-۹]{1,2}|[\u0600-\u06FF ]{2,12})(?:\s*[:：]\s*([0-9۰-۹]{2}))?")
_DUR_RE = re.compile(r"([0-9۰-۹]{1,3}|[\u0600-\u06FF ]{2,14})\s*(ساعت|دقیقه)")


def _norm(text: str) -> str:
    return text.translate(_PERSIAN_DIGITS).replace("ي", "ی").replace("ك", "ک")


def _number(token: str) -> int | None:
    token = token.strip()
    try:
        return int(token)
    except ValueError:
        pass
    total = 0
    parts = [p.strip() for p in token.split(" و ")]
    for p in parts:
        if p == "نیم":
            total += 30
        elif p in _WORD_NUM:
            total += int(_WORD_NUM[p])
        else:
            return None
    return total or None


def _extract_time(chunk: str) -> int | None:
    m = _TIME_RE.search(chunk)
    if not m:
        return None
    raw = _norm(m.group(1)).strip()
    hour = _number(raw)
    if hour is None or not 0 <= hour <= 23:
        return None
    minute = int(_norm(m.group(2) or "0"))
    if minute > 59:
        return None
    evening = any(w in chunk for w in ("عصر", "شب", "باشگاه", "بعدازظهر")) or 1 <= hour <= 7
    if evening and hour < 12:
        hour += 12
    return hour * 60 + minute


def _extract_duration(chunk: str) -> int | None:
    m = _DUR_RE.search(chunk)
    if not m:
        return None
    n = _number(_norm(m.group(1)).strip())
    if n is None:
        return None
    return n * 60 if "ساعت" in m.group(2) else n


def parse_natural_request(text: str) -> dict:
    """Split a Persian daily-brain-dump into candidate tasks and fixed events."""
    clean = _norm(text).strip()
    chunks = [c.strip() for c in re.split(r"[،,\n;؛]| و ", clean) if c.strip()]
    tasks: list[dict] = []
    fixed: list[dict] = []
    detected: list[str] = []
    for idx, chunk in enumerate(chunks):
        at = _extract_time(chunk)
        duration = _extract_duration(chunk)
        if any(w in chunk for w in _WORKOUT):
            start = at if at is not None else 18 * 60
            end = min(start + (duration or 90), 1440)
            fixed.append({"id": f"in-w-{idx}", "title": chunk, "start_min": start,
                          "end_min": end, "category": "workout"})
            detected.append("workout")
        elif any(w in chunk for w in _MEETING):
            start = at if at is not None else 10 * 60
            end = min(start + (duration or 60), 1440)
            fixed.append({"id": f"in-m-{idx}", "title": chunk, "start_min": start,
                          "end_min": end, "category": "meeting"})
            detected.append("meeting")
        else:
            tasks.append({"id": f"in-t-{idx}", "title": chunk,
                          "duration_min": duration or 60, "priority": min(idx + 1, 5),
                          "energy": "high" if duration and duration >= 120 else "medium",
                          "kind": "focus"})
            detected.append("task")
    return {"tasks": tasks, "fixed": fixed, "detected": detected, "chunks": chunks}


def constraints_from_profile(profile: UserProfile | None, day: date, *,
                             energy_mode: str = "normal",
                             replan_from_min: int | None = None,
                             completed_task_ids: list[str] | None = None) -> DayConstraints:
    if profile is None:
        return DayConstraints(day.isoformat(), energy_mode=energy_mode,
                              replan_from_min=replan_from_min,
                              completed_task_ids=completed_task_ids or [],
                              meal_windows=[(780, 810, "ناهار")])
    meals = [(int(w.get("start", 780)), int(w.get("end", 810)), str(w.get("title", "ناهار")))
             for w in (profile.meal_windows or [])]
    if not meals:
        meals = [(780, 810, "ناهار")]
    commute = []
    if profile.commute_minutes:
        commute = [(profile.work_start - profile.commute_minutes, profile.work_start, "رفتآمد")]
    return DayConstraints(
        date=day.isoformat(), wake_min=profile.wake_time, sleep_min=profile.sleep_time,
        buffer_pct=profile.buffer_pct, focus_capacity_min=profile.daily_focus_capacity_min,
        focus_peak_start=profile.focus_peak_start, focus_peak_end=profile.focus_peak_end,
        energy_mode=energy_mode, replan_from_min=replan_from_min,
        completed_task_ids=completed_task_ids or [], meal_windows=meals,
        commute_blocks=commute,
    )


def load_tasks(db: Session, user_id: int, day: date, tz_name: str = "UTC") -> list[TaskSpec]:
    rows = (db.query(Task).filter(Task.user_id == user_id, Task.status != "done")
            .order_by(Task.priority, Task.created_at).all())
    out = []
    for r in rows:
        deadline_min = utc_to_local_minute(r.deadline, day, tz_name)
        out.append(TaskSpec(
            id=str(r.id), title=r.title, duration_min=r.duration_min, priority=r.priority,
            energy=r.energy, depends_on=[str(x) for x in (r.depends_on or [])],
            deadline_min=deadline_min, earliest_start_min=r.earliest_start_min,
            latest_end_min=r.latest_end_min, must_do=r.must_do, deferrable=r.deferrable,
            kind=r.kind, project=str(r.project_id) if r.project_id else None,
        ))
    return out


def load_fixed(db: Session, user_id: int, day: date) -> list[FixedBlock]:
    rows = (db.query(FixedEvent).filter(FixedEvent.user_id == user_id, FixedEvent.date == day)
            .order_by(FixedEvent.start_min).all())
    return [FixedBlock(str(r.id), r.title, r.start_min, r.end_min, r.category, r.is_locked) for r in rows]


def persist_plan(db: Session, *, user_id: int, day: date, result: dict,
                 energy_mode: str) -> Plan:
    db.query(Plan).filter(Plan.user_id == user_id, Plan.date == day).update(
        {Plan.is_active: False}, synchronize_session=False)
    plan = Plan(user_id=user_id, date=day, version=result.get("version", 1),
                energy_mode=energy_mode, payload=result, is_active=True)
    db.add(plan)
    db.flush()
    for b in result["blocks"]:
        tid = b.get("task_id")
        db.add(PlanBlock(plan_id=plan.id, task_id=int(tid) if tid and str(tid).isdigit() else None,
                         title=b["title"], start_min=b["start_min"], end_min=b["end_min"],
                         block_type=b["type"], status="planned"))
    scheduled_ids = [int(b["task_id"]) for b in result["scheduled"]
                     if b.get("task_id") and str(b["task_id"]).isdigit()]
    if scheduled_ids:
        db.query(Task).filter(Task.user_id == user_id, Task.id.in_(scheduled_ids)).update(
            {Task.status: "scheduled", Task.planned_for: day}, synchronize_session=False)
    db.flush()
    return plan


def generate(db: Session, *, user_id: int, day: date, profile: UserProfile | None,
             energy_mode: str = "normal", replan_from_min: int | None = None,
             extended_events: dict[str, int] | None = None,
             completed_task_ids: list[str] | None = None,
             extra_tasks: list[dict] | None = None,
             extra_fixed: list[dict] | None = None,
             persist: bool = True, tz_name: str = "UTC") -> dict:
    tasks = load_tasks(db, user_id, day, tz_name)
    for i, t in enumerate(extra_tasks or []):
        tasks.append(TaskSpec(id=t.get("id", f"tmp-{i}"), title=t["title"],
                              duration_min=int(t.get("duration_min", 60)),
                              priority=int(t.get("priority", 3)),
                              energy=t.get("energy", "medium"),
                              depends_on=[str(x) for x in t.get("depends_on", [])],
                              deadline_min=t.get("deadline_min"),
                              must_do=bool(t.get("must_do", False)),
                              kind=t.get("kind", "focus")))
    fixed = load_fixed(db, user_id, day)
    for b in extra_fixed or []:
        fixed.append(FixedBlock(b["id"], b["title"], int(b["start_min"]),
                                int(b["end_min"]), b.get("category", "meeting")))
    c = constraints_from_profile(profile, day, energy_mode=energy_mode,
                                 replan_from_min=replan_from_min,
                                 completed_task_ids=completed_task_ids)
    previous = (db.query(Plan).filter(Plan.user_id == user_id, Plan.date == day,
                                      Plan.is_active.is_(True)).first())
    if extended_events or replan_from_min is not None:
        result = replan(tasks, fixed, c, extended_events=extended_events,
                        previous=previous.payload if previous else None)
    else:
        result = build_plan(tasks, fixed, c)
    result["plan_id"] = None
    if persist:
        plan = persist_plan(db, user_id=user_id, day=day, result=result, energy_mode=energy_mode)
        result["plan_id"] = plan.id
    return result


def complete_task(db: Session, *, user_id: int, task_id: int,
                  actual_minutes: int | None = None, note: str = "") -> Task:
    task = db.query(Task).filter(Task.id == task_id, Task.user_id == user_id).first()
    if task is None:
        raise NotFound("وظیفه پیدا نشد.")
    task.status = "done"
    task.completed_at = utcnow()
    if actual_minutes and actual_minutes > 0:
        task.duration_min = actual_minutes
    db.flush()
    return task
