"""ROMKA Planning Engine — deterministic, constraint-based, fully testable.

The LLM may *propose* tasks and durations. Only this engine *decides* the
schedule, and its output is validated before it is ever shown to the user.

All times are "minutes from midnight" (integers). Timezone conversion happens at
the API boundary, never inside the solver.
"""
from __future__ import annotations

import heapq
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Iterable

from dateutil.rrule import rrulestr

MIN_DAY = 1440


@dataclass
class TaskSpec:
    id: str
    title: str
    duration_min: int
    priority: int = 3                       # 1 = highest
    energy: str = "medium"                  # low | medium | high
    depends_on: list[str] = field(default_factory=list)
    deadline_min: int | None = None
    earliest_start_min: int | None = None
    latest_end_min: int | None = None
    must_do: bool = False
    deferrable: bool = True
    kind: str = "focus"                     # focus | admin | personal
    project: str | None = None


@dataclass
class FixedBlock:
    id: str
    title: str
    start_min: int
    end_min: int
    category: str = "meeting"               # meeting | workout | meal | commute | personal
    locked: bool = True


@dataclass
class DayConstraints:
    date: str
    wake_min: int = 420
    sleep_min: int = 1380
    buffer_pct: int = 15
    focus_capacity_min: int = 300
    focus_peak_start: int = 480
    focus_peak_end: int = 660
    energy_mode: str = "normal"             # normal | low
    replan_from_min: int | None = None
    completed_task_ids: list[str] = field(default_factory=list)
    meal_windows: list[tuple[int, int, str]] = field(default_factory=list)
    commute_blocks: list[tuple[int, int, str]] = field(default_factory=list)


def min_to_hhmm(value: int) -> str:
    value = max(0, min(value, MIN_DAY))
    return f"{value // 60:02d}:{value % 60:02d}"


def hhmm_to_min(value: str) -> int:
    h, m = value.strip().split(":")[:2]
    total = int(h) * 60 + int(m)
    if not 0 <= total < MIN_DAY:
        raise ValueError("زمان باید بین 00:00 و 23:59 باشد.")
    return total


def _merge(intervals: Iterable[tuple[int, int]]) -> list[tuple[int, int]]:
    ordered = sorted((max(0, s), min(MIN_DAY, e)) for s, e in intervals if e > s)
    merged: list[list[int]] = []
    for s, e in ordered:
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return [(s, e) for s, e in merged]


def _free_slots(busy: list[tuple[int, int]], wake: int, sleep: int) -> list[tuple[int, int]]:
    slots: list[tuple[int, int]] = []
    cursor = wake
    for s, e in _merge(busy):
        if e <= wake or s >= sleep:
            continue
        s, e = max(s, wake), min(e, sleep)
        if s > cursor:
            slots.append((cursor, s))
        cursor = max(cursor, e)
    if cursor < sleep:
        slots.append((cursor, sleep))
    return slots


def find_conflicts(blocks: list[FixedBlock]) -> list[dict]:
    """Report overlaps between fixed commitments instead of silently double-booking."""
    out: list[dict] = []
    ordered = sorted(blocks, key=lambda b: (b.start_min, b.end_min))
    for i, a in enumerate(ordered):
        for b in ordered[i + 1:]:
            if b.start_min >= a.end_min:
                break
            out.append({
                "type": "fixed_overlap",
                "a": a.id, "b": b.id,
                "title_a": a.title, "title_b": b.title,
                "from_min": b.start_min, "to_min": min(a.end_min, b.end_min),
                "message": f"تداخل بین «{a.title}» و «{b.title}» از {min_to_hhmm(b.start_min)}.",
            })
    return out


def _order_tasks(tasks: list[TaskSpec]) -> list[TaskSpec]:
    by_id = {t.id: t for t in tasks}
    deps = {t.id: set(d for d in t.depends_on if d in by_id) for t in tasks}
    children: dict[str, list[str]] = {t.id: [] for t in tasks}
    for tid, ds in deps.items():
        for d in ds:
            children[d].append(tid)
    heap: list[tuple[tuple, str]] = []

    def key(t: TaskSpec) -> tuple:
        return (0 if t.must_do else 1, t.deadline_min if t.deadline_min is not None else MIN_DAY,
                t.priority, -t.duration_min, t.id)

    for tid, ds in deps.items():
        if not ds:
            heapq.heappush(heap, (key(by_id[tid]), tid))
    ordered: list[TaskSpec] = []
    while heap:
        _, tid = heapq.heappop(heap)
        ordered.append(by_id[tid])
        for child in children[tid]:
            deps[child].discard(tid)
            if not deps[child]:
                heapq.heappush(heap, (key(by_id[child]), child))
    if len(ordered) != len(tasks):
        raise ValueError("وابستگی وظایف دارای حلقه است و قابل برنامه‌ریزی نیست.")
    return ordered


def _find_start(slots: list[tuple[int, int]], earliest: int, duration: int,
                latest_end: int, prefer: tuple[int, int] | None = None) -> int | None:
    """Prefer the focus peak for demanding work, but never delay a task >45 min
    just to hit that window: urgency beats chronotype."""
    plain = _first_fit(slots, earliest, duration, latest_end, None)
    if prefer is None or plain is None:
        return plain
    preferred = _first_fit(slots, earliest, duration, latest_end, prefer)
    if preferred is not None and preferred - plain <= 45:
        return preferred
    return plain


def _first_fit(slots: list[tuple[int, int]], earliest: int, duration: int,
               latest_end: int, pref: tuple[int, int] | None) -> int | None:
    for s, e in slots:
        lo = max(s, earliest)
        hi = min(e, latest_end)
        if pref:
            lo, hi = max(lo, pref[0]), min(hi, pref[1])
        if lo + duration <= hi:
            return lo
    return None


def _slot_end(slots: list[tuple[int, int]], start: int) -> int:
    for s, e in slots:
        if s <= start < e:
            return e
    return start


def validate_inputs(tasks: list[TaskSpec], fixed: list[FixedBlock], c: DayConstraints) -> None:
    if not 0 <= c.wake_min < c.sleep_min <= MIN_DAY:
        raise ValueError("بازه بیداری/خواب نامعتبر است.")
    if c.energy_mode not in ("normal", "low"):
        raise ValueError("حالت انرژی نامعتبر است.")
    ids = [t.id for t in tasks]
    if len(ids) != len(set(ids)):
        raise ValueError("شناسه وظایف تکراری است.")
    for t in tasks:
        if t.duration_min <= 0 or t.duration_min > MIN_DAY:
            raise ValueError(f"مدت وظیفه «{t.title}» نامعتبر است.")
        if t.energy not in ("low", "medium", "high"):
            raise ValueError(f"سطح انرژی وظیفه «{t.title}» نامعتبر است.")
        for bound in (t.earliest_start_min, t.latest_end_min, t.deadline_min):
            if bound is not None and not 0 <= bound <= MIN_DAY:
                raise ValueError(f"محدودیت زمانی وظیفه «{t.title}» نامعتبر است.")
    for b in fixed:
        if not 0 <= b.start_min < b.end_min <= MIN_DAY:
            raise ValueError(f"بازه رویداد «{b.title}» نامعتبر است.")
    _order_tasks(tasks)  # raises on cycles


def build_plan(tasks: list[TaskSpec], fixed: list[FixedBlock], c: DayConstraints) -> dict:
    """Build a conflict-free daily plan. Returns a JSON-serialisable dict."""
    validate_inputs(tasks, fixed, c)

    # 1. Fixed commitments + generated meals/commute become immovable busy time.
    busy: list[tuple[int, int]] = [(b.start_min, b.end_min) for b in fixed]
    plan_blocks: list[dict] = []
    for b in sorted(fixed, key=lambda x: x.start_min):
        plan_blocks.append({
            "id": b.id, "task_id": None, "title": b.title,
            "start_min": b.start_min, "end_min": b.end_min,
            "type": "fixed", "category": b.category, "priority": None,
            "start": min_to_hhmm(b.start_min), "end": min_to_hhmm(b.end_min),
        })
    generated: list[FixedBlock] = []
    for i, (s, e, title) in enumerate(c.meal_windows):
        generated.append(FixedBlock(f"meal-{i}", title, s, e, "meal"))
    for i, (s, e, title) in enumerate(c.commute_blocks):
        generated.append(FixedBlock(f"commute-{i}", title, s, e, "commute"))
    for b in generated:
        busy.append((b.start_min, b.end_min))
        plan_blocks.append({"id": b.id, "task_id": None, "title": b.title,
                            "start_min": b.start_min, "end_min": b.end_min,
                            "type": "fixed", "category": b.category, "priority": None,
                            "start": min_to_hhmm(b.start_min), "end": min_to_hhmm(b.end_min)})
    # Conflicts among ALL fixed commitments (including generated meals/commute).
    conflicts = find_conflicts(fixed + generated)

    free_slots = _free_slots(busy, c.wake_min, c.sleep_min)
    free_minutes = sum(e - s for s, e in free_slots)
    capacity = c.focus_capacity_min * (0.6 if c.energy_mode == "low" else 1.0)

    by_id = {t.id: t for t in tasks}
    completed = set(c.completed_task_ids)
    scheduled: list[dict] = []
    deferred: list[dict] = []
    dep_end: dict[str, int] = {}
    focus_used = 0.0
    gap_base = max(0, c.buffer_pct)

    for t in _order_tasks([t for t in tasks if t.id not in completed]):
        if t.energy == "high" and c.energy_mode == "low" and not t.must_do and t.deferrable:
            deferred.append({"task_id": t.id, "title": t.title, "reason": "low_energy",
                             "message": "در روز کم‌انرژی، کارهای سنگین به تعویق افتادند."})
            continue
        missing = [d for d in t.depends_on if d in by_id and d in deferred_ids(deferred)]
        if missing:
            deferred.append({"task_id": t.id, "title": t.title, "reason": "dependency",
                             "message": f"کار وابسته به «{', '.join(missing)}» انجام نشده است."})
            continue
        duration = t.duration_min
        if t.kind == "focus" and focus_used + duration > capacity:
            deferred.append({"task_id": t.id, "title": t.title, "reason": "capacity",
                             "message": "ظرفیت تمرکز واقعی روز تمام شده است."})
            continue

        earliest = max(c.wake_min, c.replan_from_min or 0,
                       t.earliest_start_min or 0,
                       max((dep_end.get(d, 0) for d in t.depends_on if d in by_id), default=0))
        latest_end = min(c.sleep_min, t.deadline_min or c.sleep_min,
                         t.latest_end_min or c.sleep_min)
        prefer = (c.focus_peak_start, c.focus_peak_end) if t.energy == "high" else None
        start = _find_start(free_slots, earliest, duration, latest_end, prefer)
        if start is None:
            deferred.append({"task_id": t.id, "title": t.title, "reason": "no_slot",
                             "message": "هیچ بازه آزادی با محدودیتهای این کار پیدا نشد."})
            continue

        end = start + duration
        gap = max(5, round(duration * gap_base / 100))
        # A buffer may never spill into an existing commitment or past bedtime.
        gap_end = min(end + gap, c.sleep_min, _slot_end(free_slots, start))
        busy.append((start, gap_end))
        free_slots = _free_slots(busy, c.wake_min, c.sleep_min)
        dep_end[t.id] = end
        if t.kind == "focus":
            focus_used += duration
        entry = {"task_id": t.id, "title": t.title, "start_min": start, "end_min": end,
                 "type": "task", "category": t.kind, "priority": t.priority,
                 "start": min_to_hhmm(start), "end": min_to_hhmm(end),
                 "duration_min": duration, "energy": t.energy,
                 "project": t.project, "must_do": t.must_do}
        scheduled.append(entry)
        plan_blocks.append({"id": f"task-{t.id}", **entry})
        if gap_end > end:
            plan_blocks.append({"id": f"buffer-{t.id}", "task_id": None, "title": "زمان بافر",
                                "start_min": end, "end_min": gap_end, "type": "buffer",
                                "category": "buffer", "priority": None,
                                "start": min_to_hhmm(end), "end": min_to_hhmm(gap_end)})

    plan_blocks.sort(key=lambda b: (b["start_min"], 0 if b["type"] == "fixed" else 1, b["end_min"]))
    scheduled_minutes = sum(b["end_min"] - b["start_min"] for b in scheduled)
    utilization = round(100 * scheduled_minutes / free_minutes, 1) if free_minutes else 0.0
    warnings: list[str] = []
    if conflicts:
        warnings.append(f"{len(conflicts)} تداخل میان تعهدات ثابت شناسایی شد.")
    if deferred:
        warnings.append(f"{len(deferred)} کار در برنامه امروز جا نشد و بهتعویق افتاد.")
    if utilization > 85:
        warnings.append("برنامه بیش از ۸۵٪ زمان آزاد را پر کرده و غیرواقعبینانه است.")
    if c.energy_mode == "low":
        warnings.append("حالت کمانرژی فعال است؛ ظرفیت تمرکز ۴۰٪ کاهش یافت.")

    result = {
        "date": c.date, "energy_mode": c.energy_mode, "version": 1,
        "replan_from_min": c.replan_from_min,
        "blocks": plan_blocks,
        "scheduled": sorted(scheduled, key=lambda x: x["start_min"]),
        "deferred": deferred,
        "conflicts": conflicts,
        "warnings": warnings,
        "metrics": {
            "free_minutes": free_minutes,
            "scheduled_minutes": scheduled_minutes,
            "utilization_pct": utilization,
            "focus_capacity_min": int(capacity),
            "focus_used_min": int(focus_used),
            "buffer_minutes": sum(b["end_min"] - b["start_min"] for b in plan_blocks if b["type"] == "buffer"),
            "unrealistic": utilization > 85 or bool(conflicts),
        },
    }
    result["validation"] = validate_plan(result, tasks, fixed, c)
    return result


def deferred_ids(deferred: list[dict]) -> set[str]:
    return {d["task_id"] for d in deferred}


def validate_plan(plan: dict, tasks: list[TaskSpec], fixed: list[FixedBlock],
                  c: DayConstraints) -> dict:
    """Independent verifier: no overlaps, bounds, durations, dependencies, deadlines."""
    violations: list[str] = []
    by_id = {t.id: t for t in tasks}
    blocks = [b for b in plan["blocks"] if b["type"] in ("fixed", "task")]
    ordered = sorted(blocks, key=lambda b: b["start_min"])
    for a, b in zip(ordered, ordered[1:]):
        if b["start_min"] < a["end_min"]:
            if a["type"] == "fixed" and b["type"] == "fixed":
                violations.append(f"fixed_conflict: {a['id']} / {b['id']}")
            else:
                violations.append(f"overlap: {a['id']} / {b['id']}")
    for blk in plan["blocks"]:
        if blk["start_min"] < c.wake_min or blk["end_min"] > c.sleep_min:
            violations.append(f"out_of_bounds: {blk['id']}")
        if blk["end_min"] <= blk["start_min"]:
            violations.append(f"non_positive_duration: {blk['id']}")
    starts = {b["task_id"]: b for b in plan["blocks"] if b["type"] == "task"}
    for tid, blk in starts.items():
        t = by_id.get(tid)
        if t is None:
            violations.append(f"unknown_task: {tid}")
            continue
        if blk["end_min"] - blk["start_min"] != t.duration_min:
            violations.append(f"duration_mismatch: {tid}")
        for d in t.depends_on:
            if d in by_id and d in starts and starts[d]["end_min"] > blk["start_min"]:
                violations.append(f"dependency_violated: {tid} after {d}")
            if d in by_id and d not in starts and d not in c.completed_task_ids:
                violations.append(f"missing_dependency: {tid} needs {d}")
        if t.deadline_min is not None and blk["end_min"] > t.deadline_min:
            violations.append(f"deadline_missed: {tid}")
        if t.latest_end_min is not None and blk["end_min"] > t.latest_end_min:
            violations.append(f"latest_end_missed: {tid}")
    if plan["metrics"]["focus_used_min"] > plan["metrics"]["focus_capacity_min"] + 1:
        violations.append("focus_capacity_exceeded")
    return {"valid": not violations, "violations": violations}


def replan(tasks: list[TaskSpec], fixed: list[FixedBlock], c: DayConstraints,
           *, extended_events: dict[str, int] | None = None,
           previous: dict | None = None) -> dict:
    """Recompute the remaining day after reality changed (scenario B).

    `extended_events` maps a fixed block id to its new end time (e.g. a meeting
    that overran). Completed tasks are never re-scheduled; the rest are re-solved
    from `replan_from_min`.
    """
    new_fixed: list[FixedBlock] = []
    for b in fixed:
        new_end = (extended_events or {}).get(b.id, b.end_min)
        if new_end < b.end_min:
            raise ValueError("زمان پایان رویداد نمیتواند کوتاهتر از زمان قبلی باشد.")
        new_fixed.append(FixedBlock(b.id, b.title, b.start_min, new_end, b.category, b.locked))
    if c.replan_from_min is None and extended_events:
        c.replan_from_min = max(
            (b.end_min for b in new_fixed if b.id in extended_events), default=c.wake_min
        )
    result = build_plan(tasks, new_fixed, c)
    result["version"] = (previous or {}).get("version", 1) + 1
    previous_start = {b["task_id"]: b["start_min"] for b in (previous or {}).get("blocks", []) if b["type"] == "task"}
    moved, kept = [], []
    for blk in result["scheduled"]:
        old = previous_start.get(blk["task_id"])
        if old is None or old == blk["start_min"]:
            kept.append(blk["task_id"])
        else:
            moved.append({"task_id": blk["task_id"], "from_min": old, "to_min": blk["start_min"],
                          "from": min_to_hhmm(old) if old is not None else None,
                          "to": blk["start"]})
    result["diff"] = {
        "moved": moved,
        "kept": kept,
        "newly_deferred": [d["task_id"] for d in result["deferred"]
                           if d["task_id"] not in deferred_ids((previous or {}).get("deferred", []))],
        "completed_preserved": list(c.completed_task_ids),
    }
    return result


def expand_recurrence(rule: str, start: date, count: int = 10) -> list[date]:
    """RFC 5545 RRULE expansion via python-dateutil (integrated, pinned, tested)."""
    if count <= 0 or count > 365:
        raise ValueError("تعداد تکرارها باید بین ۱ و ۳۶۵ باشد.")
    try:
        rr = rrulestr(rule, dtstart=datetime.combine(start, datetime.min.time()))
    except (ValueError, TypeError) as exc:
        raise ValueError(f"قانون تکرار نامعتبر است: {exc}") from exc
    return [d.date() for d in list(rr)[:count]]


def light_day_plan(tasks: list[TaskSpec], fixed: list[FixedBlock],
                   c: DayConstraints) -> dict:
    """A genuine alternative: keep must-do + top priority, drop the rest."""
    keep = [t for t in tasks if t.must_do or t.priority <= 2]
    low = DayConstraints(**{**asdict(c), "energy_mode": "low"})
    return build_plan(keep, fixed, low)
