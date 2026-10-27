from __future__ import annotations

from datetime import date

import pytest

from app.planning.engine import (
    DayConstraints, FixedBlock, TaskSpec, build_plan, expand_recurrence,
    find_conflicts, light_day_plan, min_to_hhmm, replan, validate_plan,
)
from app.planning.service import parse_natural_request


def C(**kw):
    return DayConstraints("2026-10-27", **kw)


def test_clock_helpers():
    assert min_to_hhmm(420) == "07:00"
    assert min_to_hhmm(1080) == "18:00"


def test_no_overlap_and_validation():
    tasks = [TaskSpec("a", "کار الف", 120, priority=1, energy="high", must_do=True),
             TaskSpec("b", "کار ب", 60, priority=2, depends_on=["a"]),
             TaskSpec("c", "خرید", 45, priority=4, energy="low")]
    fixed = [FixedBlock("m", "جلسه", 600, 660), FixedBlock("g", "باشگاه", 1080, 1170, "workout")]
    c = C(meal_windows=[(780, 810, "ناهار")], commute_blocks=[(1020, 1050, "رفتآمد")])
    plan = build_plan(tasks, fixed, c)
    assert plan["validation"]["valid"], plan["validation"]["violations"]
    assert len(plan["scheduled"]) == 3
    assert plan["metrics"]["buffer_minutes"] > 0
    # Buffers must never overlap a fixed commitment.
    for blk in [b for b in plan["blocks"] if b["type"] == "buffer"]:
        for f in fixed:
            assert not (blk["start_min"] < f.end_min and f.start_min < blk["end_min"])
    assert validate_plan(plan, tasks, fixed, c)["valid"]


def test_dependencies_and_deadlines():
    tasks = [TaskSpec("a", "اول", 60, priority=1, deadline_min=600),
             TaskSpec("b", "دوم", 60, depends_on=["a"], priority=2)]
    plan = build_plan(tasks, [], C())
    starts = {b["task_id"]: b for b in plan["blocks"] if b["type"] == "task"}
    assert starts["a"]["end_min"] <= starts["b"]["start_min"]
    assert starts["a"]["end_min"] <= 600


def test_dependency_cycle_rejected():
    with pytest.raises(ValueError):
        build_plan([TaskSpec("a", "a", 30, depends_on=["b"]),
                    TaskSpec("b", "b", 30, depends_on=["a"])], [], C())


def test_capacity_and_unrealistic_warning():
    tasks = [TaskSpec(str(i), f"کار {i}", 120, priority=2) for i in range(8)]
    c = C(focus_capacity_min=180)
    plan = build_plan(tasks, [], c)
    assert plan["deferred"], "over-capacity tasks must be deferred, not squeezed"
    assert any(d["reason"] == "capacity" for d in plan["deferred"])
    assert plan["metrics"]["unrealistic"] or plan["warnings"]


def test_low_energy_mode_defers_heavy_optional_work():
    tasks = [TaskSpec("x", "کار سنگین", 60, energy="high", deferrable=True),
             TaskSpec("y", "کار سبک", 30, energy="low", must_do=True)]
    plan = build_plan(tasks, [], C(energy_mode="low"))
    assert any(d["task_id"] == "x" and d["reason"] == "low_energy" for d in plan["deferred"])
    assert any(b["task_id"] == "y" for b in plan["scheduled"])


def test_fixed_conflicts_detected_including_generated_meals():
    fixed = [FixedBlock("m", "جلسه", 600, 900)]
    conflicts = find_conflicts(fixed + [FixedBlock("meal-0", "ناهار", 780, 810, "meal")])
    assert conflicts and conflicts[0]["type"] == "fixed_overlap"


def test_replan_keeps_completed_and_reports_move():
    tasks = [TaskSpec("a", "لانچ", 120, priority=1, must_do=True),
             TaskSpec("b", "بررسی", 60, priority=2), TaskSpec("c", "خرید", 45, priority=4)]
    fixed = [FixedBlock("m", "جلسه", 600, 660), FixedBlock("g", "باشگاه", 1080, 1170, "workout")]
    first = build_plan(tasks, fixed, C())
    c = C(completed_task_ids=["a"], meal_windows=[(780, 810, "ناهار")])
    second = replan(tasks, fixed, c, extended_events={"m": 900}, previous=first)
    assert second["version"] == 2
    assert second["replan_from_min"] == 900
    assert "a" not in [b["task_id"] for b in second["scheduled"]]
    assert second["diff"]["moved"] or second["diff"]["newly_deferred"]
    assert second["conflicts"], "extended meeting collides with lunch and must be reported"


def test_light_day_is_a_real_alternative():
    tasks = [TaskSpec("a", "ضروری", 60, must_do=True, priority=1),
             TaskSpec("b", "اختیاری", 60, priority=5, deferrable=True)]
    alt = light_day_plan(tasks, [], C())
    assert [b["task_id"] for b in alt["scheduled"]] == ["a"]


def test_recurrence_expansion_uses_dateutil():
    dates = expand_recurrence("FREQ=WEEKLY;BYDAY=MO,WE", date(2026, 10, 27), 4)
    assert [d.isoformat() for d in dates] == ["2026-10-28", "2026-11-02", "2026-11-04", "2026-11-09"]
    with pytest.raises(ValueError):
        expand_recurrence("NOT_A_RULE", date(2026, 1, 1), 2)


def test_scenario_a_natural_language_intake():
    text = ("امروز باید روی انتشار گپینه کار کنم، نویدبان را بررسی کنم، "
            "یک جلسه کاری دارم، خرید کنم و ساعت شش باشگاه بروم")
    parsed = parse_natural_request(text)
    assert len(parsed["tasks"]) == 3
    assert {e["category"] for e in parsed["fixed"]} == {"meeting", "workout"}
    gym = next(e for e in parsed["fixed"] if e["category"] == "workout")
    assert gym["start_min"] == 1080, "ساعت شش عصر = 18:00"


def test_input_validation_rejects_nonsense():
    with pytest.raises(ValueError):
        build_plan([TaskSpec("a", "x", -5)], [], C())
    with pytest.raises(ValueError):
        build_plan([], [], DayConstraints("2026-01-01", wake_min=900, sleep_min=420))


def test_timezone_boundary_conversion():
    from app.core.timeutil import local_minute_to_utc, today_in, utc_to_local_minute
    d = date(2026, 10, 27)
    naive_utc = local_minute_to_utc(d, 600, "Asia/Tehran")
    assert utc_to_local_minute(naive_utc, d, "Asia/Tehran") == 600
    assert utc_to_local_minute(naive_utc, date(2026, 10, 28), "Asia/Tehran") is None
    assert isinstance(today_in("Asia/Tehran"), date)
    assert isinstance(today_in("Not/AZone"), date)  # graceful fallback to UTC
