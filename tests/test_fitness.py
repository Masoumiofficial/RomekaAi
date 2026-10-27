from __future__ import annotations

import pytest

from app.fitness import BodyInput, estimate_energy, meal_plan, progression, workout_plan


def B(**kw):
    base = dict(weight_kg=80, height_cm=180, age=30, sex="male", activity="moderate",
                goal="maintain", experience="beginner", days_per_week=3,
                session_minutes=60, equipment=["gym"], injuries=[], allergies=[])
    base.update(kw)
    return BodyInput(**base)


def test_energy_is_estimate_and_goal_aware():
    m = estimate_energy(B())
    cut = estimate_energy(B(goal="cut"))
    bulk = estimate_energy(B(goal="bulk"))
    assert cut["target_kcal"] < m["target_kcal"] < bulk["target_kcal"]
    assert "تخمین" in m["method"] and m["water_ml"] > 0
    with pytest.raises(ValueError):
        estimate_energy(B(weight_kg=0))


def test_workout_plan_has_required_fields_and_adapts_to_injury():
    plan = workout_plan(B(days_per_week=3, injuries=["زانو"]))
    assert len(plan["sessions"]) == 3
    ex = plan["sessions"][0]["exercises"][0]
    for k in ("sets", "reps", "rest_seconds", "intensity", "technique", "alternative",
              "safety", "progression_rule", "weight_selection"):
        assert k in ex
    assert "هیچ وزنهای" in ex["weight_selection"]


def test_progression_never_increases_with_pain_or_missing_data():
    assert progression([{"date": "2026-10-01", "sets": 3, "reps": 10, "weight_kg": 60,
                         "rpe": 7, "pain_flag": False}])["can_increase"] is False
    logs = [
        {"date": "2026-10-01", "sets": 3, "reps": 10, "weight_kg": 60, "rpe": 7, "pain_flag": False},
        {"date": "2026-10-08", "sets": 3, "reps": 10, "weight_kg": 60, "rpe": 9, "pain_flag": True},
    ]
    out = progression(logs)
    assert out["decision"] == "hold_or_reduce" and not out["can_increase"]
    assert out["reasons"]


def test_progression_allows_gradual_increase_only_when_safe():
    logs = [
        {"date": "2026-10-01", "sets": 3, "reps": 10, "weight_kg": 60, "rpe": 7,
         "pain_flag": False, "planned_sets": 3},
        {"date": "2026-10-08", "sets": 3, "reps": 10, "weight_kg": 60, "rpe": 7,
         "pain_flag": False, "planned_sets": 3},
    ]
    out = progression(logs)
    assert out["can_increase"] and out["suggested_weight_kg"] > 60
    assert "پیشنهاد" in out["message"]


def test_meal_plan_respects_allergy_and_has_measurable_amounts():
    e = estimate_energy(B(allergies=["تخممرغ"]))
    m = meal_plan(e, B(allergies=["تخممرغ"]))
    assert m["meals"][0]["items"][0]["name"] != "تخممرغ"
    assert all("amount" in i for meal in m["meals"] for i in meal["items"])
    assert m["target_kcal"] == e["target_kcal"]
