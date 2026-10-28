"""Estimate calibration, day review and weekly load — real numbers, no invention.

The rule under test: ROMKA may only correct its own time estimates from
*recorded history*, never before there is enough evidence, and never silently.
"""
from __future__ import annotations

import subprocess
import sys
from datetime import date, timedelta

import pytest

from app.db.models import Task
from app.planning.review import MAX_RATIO, MIN_RATIO, MIN_SAMPLES, calibration, daily_review, weekly_load
from app.planning.service import generate, load_tasks
from tests.conftest import H


def _task(db, user_id: int, *, duration=60, actual=None, status="done", day=None,
          priority=3, title="کار"):
    row = Task(user_id=user_id, title=title, duration_min=duration, actual_min=actual,
               status=status, priority=priority,
               planned_for=day or date.today())
    db.add(row)
    db.flush()
    return row


# ── calibration math and its guardrails ─────────────────────────────────────

def test_calibration_needs_evidence_before_changing_estimates(db):
    for i in range(MIN_SAMPLES - 1):
        _task(db, 1, duration=60, actual=90, title=f"t{i}")
    state = calibration(db, 1)
    assert state["samples"] == MIN_SAMPLES - 1
    assert state["applied"] is False and state["ratio"] == 1.0
    assert "حداقل" in state["note"]


def test_calibration_applies_median_ratio_once_enough_samples(db):
    for i, ratio in enumerate([1.5, 1.5, 1.5, 1.5, 3.0]):
        _task(db, 1, duration=60, actual=int(60 * ratio), title=f"t{i}")
    state = calibration(db, 1)
    assert state["samples"] == 5 and state["applied"] is True
    assert state["ratio"] == 1.5 and state["confidence"] == "medium"
    assert state["clamped"] is False


@pytest.mark.parametrize("raw,expected", [(3.0, MAX_RATIO), (0.2, MIN_RATIO)])
def test_calibration_is_clamped_so_one_bad_day_cannot_wreck_a_plan(db, raw, expected):
    for i in range(MIN_SAMPLES):
        _task(db, 1, duration=100, actual=int(100 * raw), title=f"t{i}")
    state = calibration(db, 1)
    assert state["ratio"] == expected and state["clamped"] is True
    assert state["applied"] is True


def test_tasks_without_real_minutes_are_not_used_as_samples(db):
    for i in range(MIN_SAMPLES):
        _task(db, 1, duration=60, actual=None, title=f"noactual{i}")
    _task(db, 1, duration=60, actual=120, title="only-real")
    assert calibration(db, 1)["samples"] == 1


def test_calibration_never_touches_status_open_tasks(db):
    _task(db, 1, duration=60, actual=600, status="todo", title="open")
    assert calibration(db, 1)["samples"] == 0


# ── planner integration ─────────────────────────────────────────────────────

def test_calibrated_ratio_scales_engine_specs_but_not_stored_estimates(db):
    for i in range(MIN_SAMPLES):
        _task(db, 1, duration=60, actual=90, title=f"hist{i}")
    live = _task(db, 1, duration=100, status="todo", title="کاری برای فردا")
    specs = load_tasks(db, 1, date.today(), "UTC", calibration_ratio=1.5)
    spec = next(s for s in specs if s.id == str(live.id))
    assert spec.duration_min == 150
    db.refresh(live)
    assert live.duration_min == 100, "stored estimate must stay untouched"


def test_generate_reports_calibration_and_can_be_disabled(db, settings):
    for i in range(MIN_SAMPLES):
        _task(db, 1, duration=60, actual=90, title=f"hist{i}")
    _task(db, 1, duration=60, status="todo", title="کار")

    on = generate(db, user_id=1, day=date.today(), profile=None, persist=False)
    assert on["calibration"]["applied"] is True
    assert on["calibration"]["applied_ratio"] == 1.5

    off = generate(db, user_id=1, day=date.today(), profile=None, persist=False,
                   apply_calibration=False)
    assert off["calibration"]["applied"] is False
    assert off["calibration"]["applied_ratio"] == 1.0


def test_daily_review_module_marks_unrecorded_minutes(db):
    _task(db, 7, duration=60, actual=None, title="کار بدون مدت")
    body = daily_review(db, user_id=7, day=date.today(), mode="night")
    assert body["counts"] == {"tasks": 1, "done": 1, "open": 0, "events": 0,
                              "with_actual_minutes": 0}
    assert body["time"] == {"estimated_min": 0, "actual_min": 0, "delta_min": 0,
                            "load_ratio": None}
    assert any("مدت واقعی" in w for w in body["warnings"])
    assert body["adherence_pct"] == 100.0


def test_weekly_load_groups_by_real_day_and_flags_empty_ones(db):
    base = date.today()
    _task(db, 8, duration=30, actual=40, day=base, title="امروز")
    _task(db, 8, duration=90, actual=None, status="todo", day=base - timedelta(days=2),
          title="دو روز پیش")
    body = weekly_load(db, user_id=8, end_day=base, days=7)
    assert body["start"] == (base - timedelta(days=6)).isoformat()
    assert body["totals"] == {"tasks": 2, "done": 1, "planned_min": 120,
                              "fixed_min": 0, "completion_pct": 50.0}
    assert body["days"][-1]["actual_min"] == 40
    assert body["days"][0]["tasks"] == 0 and "ثبت" in body["note"]


# ── API: completing with real minutes ───────────────────────────────────────

def test_complete_keeps_estimate_and_records_actual(auth_client):
    c, csrf, _ = auth_client
    task = c.post("/api/v1/planner/tasks", json={"title": "نوشتن", "duration_min": 60},
                  headers=H(csrf)).json()["item"]
    r = c.post(f"/api/v1/planner/tasks/{task['id']}/complete",
               json={"actual_minutes": 95}, headers=H(csrf))
    assert r.status_code == 200, r.text
    item = r.json()["item"]
    assert item["duration_min"] == 60, "estimate must survive completion"
    assert item["actual_min"] == 95
    assert r.json()["calibration"]["samples"] == 1
    assert r.json()["calibration"]["applied"] is False


def test_complete_without_actual_is_allowed_but_flagged(auth_client):
    c, csrf, _ = auth_client
    task = c.post("/api/v1/planner/tasks", json={"title": "بدون مدت"}, headers=H(csrf)).json()["item"]
    r = c.post(f"/api/v1/planner/tasks/{task['id']}/complete", json={}, headers=H(csrf))
    assert r.status_code == 200 and r.json()["item"]["actual_min"] is None
    review = c.get("/api/v1/planner/review", headers=H(csrf)).json()
    assert any("مدت واقعی" in w for w in review["warnings"])


@pytest.mark.parametrize("bad", [0, -5, 5000])
def test_complete_rejects_impossible_actual_minutes(auth_client, bad):
    c, csrf, _ = auth_client
    task = c.post("/api/v1/planner/tasks", json={"title": "x"}, headers=H(csrf)).json()["item"]
    r = c.post(f"/api/v1/planner/tasks/{task['id']}/complete",
               json={"actual_minutes": bad}, headers=H(csrf))
    assert r.status_code == 422


# ── API: daily review & weekly load ────────────────────────────────────────

def test_daily_review_reports_only_recorded_numbers(auth_client):
    c, csrf, _ = auth_client
    today = c.get("/api/v1/planner/today").json()["date"]
    a = c.post("/api/v1/planner/tasks", json={"title": "کار الف", "duration_min": 60,
                                              "priority": 1}, headers=H(csrf)).json()["item"]
    b = c.post("/api/v1/planner/tasks", json={"title": "کار ب", "duration_min": 30},
               headers=H(csrf)).json()["item"]
    c.post(f"/api/v1/planner/tasks/{a['id']}/complete", json={"actual_minutes": 120},
           headers=H(csrf))

    r = c.get(f"/api/v1/planner/review?day={today}", headers=H(csrf))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["counts"]["with_actual_minutes"] == 1
    assert body["time"] == {"estimated_min": 60, "actual_min": 120, "delta_min": 60,
                            "load_ratio": None}
    assert body["overruns"][0]["title"] == "کار الف"
    assert any("۲۰٪" in w for w in body["warnings"])
    # next actions come from open tasks, with a stated reason
    assert all(a["reason"] for a in body["next_actions"])
    assert b["id"] in [x["id"] for x in body["next_actions"]]
    assert "پزشکی" in body["note"] or "روان" in body["note"] or "قضاوت" in body["note"]


def test_morning_mode_previews_instead_of_judging(auth_client):
    c, csrf, _ = auth_client
    c.post("/api/v1/planner/tasks", json={"title": "کار باز"}, headers=H(csrf))
    body = c.get("/api/v1/planner/review?mode=morning", headers=H(csrf)).json()
    assert body["mode"] == "morning" and "کار باز" in body["summary"]


def test_review_on_empty_day_is_explicit_not_invented(auth_client):
    c, csrf, _ = auth_client
    empty = (date.today() - timedelta(days=30)).isoformat()
    body = c.get(f"/api/v1/planner/review?day={empty}", headers=H(csrf)).json()
    assert body["counts"]["tasks"] == 0 and body["adherence_pct"] is None
    assert body["time"]["actual_min"] == 0


def test_weekly_load_covers_seven_real_days(auth_client, db):
    c, csrf, _ = auth_client
    uid = c.get("/api/v1/auth/me", headers=H(csrf)).json()["user"]["id"]
    day = date.today() - timedelta(days=3)
    db.add(Task(user_id=uid, title="گذشته", duration_min=45, status="done",
                actual_min=50, planned_for=day))
    db.flush()
    body = c.get("/api/v1/planner/week", headers=H(csrf)).json()
    assert len(body["days"]) == 7
    assert body["totals"]["tasks"] == 1 and body["totals"]["done"] == 1
    assert body["days"][3]["date"] == day.isoformat()
    assert body["days"][3]["planned_min"] == 45
    assert "ثبت" in body["note"]


def test_calibration_endpoint_is_public_state_not_advice(auth_client):
    c, csrf, _ = auth_client
    body = c.get("/api/v1/planner/calibration", headers=H(csrf)).json()
    assert body["calibration"]["applied"] is False
    assert body["calibration"]["min_samples"] == MIN_SAMPLES


def test_daily_review_user_isolation(auth_client, client):
    c, csrf, _ = auth_client
    c.post("/api/v1/planner/tasks", json={"title": "خصوصی"}, headers=H(csrf))
    other = client.post("/api/v1/auth/register", json={
        "email": "other@romka.local", "password": "RomkaDemo2026!"}).json()
    body = client.get("/api/v1/planner/review",
                      headers=H(other["csrf_token"])).json()
    assert body["counts"]["tasks"] == 0


# ── CLI verification script (honest failure paths, no network) ─────────────

def test_verify_provider_script_refuses_without_key(tmp_path):
    out = subprocess.run([sys.executable, "scripts/verify_provider.py",
                          "--env-file", str(tmp_path / "missing.env")],
                         capture_output=True, text=True,
                         env={"PATH": "/usr/bin:/bin"})
    assert out.returncode == 2
    assert "Nothing was sent" in out.stdout


def test_verify_provider_script_requires_base_url_for_generic_provider(tmp_path):
    out = subprocess.run([sys.executable, "scripts/verify_provider.py",
                          "--provider", "openai_compatible", "--key-env", "PATH",
                          "--env-file", str(tmp_path / "missing.env")],
                         capture_output=True, text=True)
    assert out.returncode == 2
    assert "base-url" in out.stdout
