"""Reviews and estimate calibration — computational, never LLM invention.

Why this module exists: a plan is only useful if its time estimates match
reality. ROMKA therefore stores what actually happened (``Task.actual_min``) and
derives a *transparent, bounded* correction factor from real history only.

Rules enforced here:
- No correction is applied before there is enough evidence (``MIN_SAMPLES``).
- The factor is clamped, so one catastrophic day can never wreck a whole plan.
- The estimate is never silently overwritten by the actual value; both remain
  visible, and every number in a review traces back to a database row.
- Nothing is invented: when data is missing the review says so explicitly.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from statistics import median

from sqlalchemy.orm import Session

from app.db.models import FixedEvent, Plan, Task

log = logging.getLogger("romka.planning.review")

MIN_SAMPLES = 5           # below this we do NOT adjust estimates
MIN_RATIO, MAX_RATIO = 0.6, 1.8
REVIEW_LOOKBACK_DAYS = 7


def task_ratio_samples(db: Session, user_id: int) -> list[float]:
    """actual/estimated ratios from completed tasks that recorded real minutes."""
    rows = (db.query(Task)
            .filter(Task.user_id == user_id, Task.status == "done",
                    Task.actual_min.isnot(None), Task.duration_min > 0)
            .all())
    out: list[float] = []
    for r in rows:
        if r.actual_min and r.actual_min > 0:
            out.append(r.actual_min / r.duration_min)
    return out


def calibration(db: Session, user_id: int) -> dict:
    """Bounded estimate correction derived from real completions.

    ``ratio`` is the median(actual/estimated). 1.15 means "your estimates run
    15% short, so plan 15% more time". Applied only when evidence is sufficient.
    """
    samples = task_ratio_samples(db, user_id)
    n = len(samples)
    state = {"samples": n, "min_samples": MIN_SAMPLES, "ratio": 1.0, "applied": False,
             "raw_ratio": None, "suggested_ratio": None, "clamped": False,
             "confidence": "insufficient"}
    if n == 0:
        state["note"] = ("هنوز مدت واقعی هیچ کاری ثبت نشده است؛ تخمین‌ها دست‌نخورده‌اند. "
                         "هنگام تکمیل وظیفه، دقیقه واقعی را وارد کنید.")
        return state
    raw = median(samples)
    clamped = min(MAX_RATIO, max(MIN_RATIO, raw))
    # ``ratio`` is what the planner actually multiplies by; it stays 1.0 until
    # the evidence threshold is met. ``suggested_ratio`` shows the pending value.
    state.update(raw_ratio=round(raw, 3), suggested_ratio=round(clamped, 3),
                 clamped=round(clamped, 3) != round(raw, 3))
    if n < MIN_SAMPLES:
        state["confidence"] = "low"
        state["note"] = (f"فقط {n} نمونه واقعی ثبت شده است (حداقل {MIN_SAMPLES} لازم است)؛ "
                         f"برای جلوگیری از تصمیم‌گیری روی داده کم، تخمین‌ها تغییر نمی‌کنند "
                         f"(نسبت پیشنهادی {state['suggested_ratio']} هنوز اعمال نشده است).")
        return state
    state.update(applied=True, ratio=round(clamped, 3),
                 confidence="high" if n >= 15 else "medium",
                 note=(f"تخمین‌ها بر اساس {n} کار انجام‌شده با ضریب {state['ratio']} "
                       f"اصلاح می‌شوند."
                       + (" (مقدار خام به سقف ایمن محدود شد.)" if state["clamped"] else "")))
    return state


def _day_tasks(db: Session, user_id: int, day: date) -> list[Task]:
    """Tasks belonging to that day (planned_for is stamped on completion)."""
    return (db.query(Task)
            .filter(Task.user_id == user_id, Task.planned_for == day)
            .order_by(Task.priority, Task.id).all())


def _plan_for(db: Session, user_id: int, day: date) -> Plan | None:
    return (db.query(Plan).filter(Plan.user_id == user_id, Plan.date == day,
                                  Plan.is_active.is_(True))
            .order_by(Plan.version.desc()).first())


def daily_review(db: Session, *, user_id: int, day: date, mode: str = "night") -> dict:
    """Morning plan preview or evening honest review — from stored rows only."""
    tasks = _day_tasks(db, user_id, day)
    done = [t for t in tasks if t.status == "done"]
    open_tasks = [t for t in tasks if t.status != "done"]
    plan = _plan_for(db, user_id, day)
    payload = plan.payload if plan else {}
    metrics = payload.get("metrics", {}) if payload else {}

    with_actual = [t for t in done if t.actual_min and t.actual_min > 0]
    estimated = sum(t.duration_min for t in with_actual)
    actual = sum(t.actual_min for t in with_actual)
    overrun = [(t.title, t.duration_min, t.actual_min) for t in with_actual
               if t.actual_min > t.duration_min * 1.2]
    under = [(t.title, t.duration_min, t.actual_min) for t in with_actual
             if t.actual_min < t.duration_min * 0.8]

    events = (db.query(FixedEvent)
              .filter(FixedEvent.user_id == user_id, FixedEvent.date == day)
              .order_by(FixedEvent.start_min).all())

    tomorrow = day + timedelta(days=1)
    upcoming = (db.query(Task)
                .filter(Task.user_id == user_id, Task.status != "done")
                .order_by(Task.priority, Task.id).limit(20).all())
    top_next = [{"id": t.id, "title": t.title, "duration_min": t.duration_min,
                 "priority": t.priority,
                 "reason": ("موعد نزدیک" if t.deadline and t.deadline.date() <= tomorrow
                            else "بالاترین اولویت" if t.priority <= 2 else "کار باز")}
                for t in upcoming[:3]]

    adherence = None
    if tasks:
        adherence = round(100.0 * len(done) / len(tasks), 1)
    load_ratio = None
    if metrics.get("scheduled_minutes") is not None:
        scheduled = metrics["scheduled_minutes"]
        load_ratio = round(actual / scheduled, 2) if scheduled and with_actual else None

    warnings: list[str] = []
    if plan and plan.payload.get("conflicts"):
        warnings.append(f"{len(plan.payload['conflicts'])} تعارض زمان در برنامه این روز ثبت شده است.")
    if overrun:
        warnings.append(f"{len(overrun)} کار بیش از ۲۰٪ طول کشید؛ برنامه فردا با کالیبراسیون واقعی ساخته می‌شود.")
    if estimate_gap := (actual - estimated):
        warnings.append(f"اختلاف تخمین و واقعیت در این روز: {estimate_gap:+d} دقیقه.")
    if not with_actual and done:
        warnings.append("کارها انجام‌شده ثبت شده‌اند ولی مدت واقعی وارد نشده؛ کالیبراسیون ممکن نیست.")

    if mode == "morning":
        summary = (f"صبح {day.isoformat()}: {len(open_tasks)} کار باز، "
                   f"{len(events)} تعهد ثابت"
                   + (f"، {metrics.get('scheduled_minutes')} دقیقه برنامه‌ریزی‌شده"
                      if metrics else "؛ هنوز برنامه‌ای ساخته نشده است"))
    else:
        summary = (f"شب {day.isoformat()}: {len(done)} از {len(tasks)} کار انجام شد"
                   if tasks else f"شب {day.isoformat()}: کاری برای این روز ثبت نشده است")

    return {
        "ok": True, "date": day.isoformat(), "mode": mode, "summary": summary,
        "counts": {"tasks": len(tasks), "done": len(done), "open": len(open_tasks),
                   "events": len(events), "with_actual_minutes": len(with_actual)},
        "time": {"estimated_min": estimated, "actual_min": actual,
                 "delta_min": actual - estimated, "load_ratio": load_ratio},
        "adherence_pct": adherence,
        "overruns": [{"title": t, "estimated_min": e, "actual_min": a}
                     for t, e, a in overrun],
        "early_finishes": [{"title": t, "estimated_min": e, "actual_min": a}
                           for t, e, a in under],
        "next_actions": top_next,
        "calibration": calibration(db, user_id),
        "warnings": warnings,
        "note": ("همه اعداد از ردیف‌های ثبت‌شده در دیتابیس محاسبه شده‌اند؛ "
                 "این مرور قضاوت پزشکی یا روان‌شناختی نیست."),
    }


def weekly_load(db: Session, *, user_id: int, end_day: date,
                days: int = REVIEW_LOOKBACK_DAYS) -> dict:
    """Real 7-day load from tasks/events/plans. No decorative charts."""
    start = end_day - timedelta(days=days - 1)
    tasks = (db.query(Task)
             .filter(Task.user_id == user_id, Task.planned_for.isnot(None),
                     Task.planned_for >= start, Task.planned_for <= end_day)
             .all())
    events = (db.query(FixedEvent)
              .filter(FixedEvent.user_id == user_id, FixedEvent.date >= start,
                      FixedEvent.date <= end_day).all())
    by_day: dict[str, dict] = {}
    cursor = start
    while cursor <= end_day:
        by_day[cursor.isoformat()] = {"planned_min": 0, "done": 0, "tasks": 0,
                                      "actual_min": 0, "fixed_min": 0}
        cursor += timedelta(days=1)
    for t in tasks:
        key = t.planned_for.isoformat() if t.planned_for else None
        if key in by_day:
            row = by_day[key]
            row["tasks"] += 1
            row["planned_min"] += t.duration_min
            row["actual_min"] += t.actual_min or 0
            row["done"] += 1 if t.status == "done" else 0
    for e in events:
        key = e.date.isoformat() if e.date else None
        if key in by_day:
            by_day[key]["fixed_min"] += max(0, e.end_min - e.start_min)
    days_out = [{"date": k, **v} for k, v in by_day.items()]
    total_planned = sum(d["planned_min"] for d in days_out)
    total_done = sum(d["done"] for d in days_out)
    total_tasks = sum(d["tasks"] for d in days_out)
    return {
        "ok": True, "start": start.isoformat(), "end": end_day.isoformat(), "days": days_out,
        "totals": {"tasks": total_tasks, "done": total_done, "planned_min": total_planned,
                   "fixed_min": sum(d["fixed_min"] for d in days_out),
                   "completion_pct": round(100.0 * total_done / total_tasks, 1) if total_tasks else None},
        "calibration": calibration(db, user_id),
        "note": ("فقط روزهایی که وظیفه/رویداد ثبت‌شده دارند معنا دارند؛ "
                 "روزهای خالی نشانه «عدم ثبت» است، نه «عدم پیشرفت»."),
    }
