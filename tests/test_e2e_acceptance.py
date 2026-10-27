"""End-to-end acceptance scenarios A–G over the real API + real SQLite."""
from __future__ import annotations

from tests.conftest import H

SCENARIO_A = ("امروز باید روی انتشار گپینه کار کنم، نویدبان را بررسی کنم، "
              "یک جلسه کاری دارم، خرید کنم و ساعت شش باشگاه بروم")


def test_health_and_pages(auth_client):
    c, csrf, _ = auth_client
    assert c.get("/api/v1/health").status_code == 200
    for path in ("/", "/chat", "/planner", "/agents", "/business", "/health", "/memory",
                 "/settings", "/onboarding"):
        r = c.get(path)
        assert r.status_code == 200, (path, r.status_code)
        assert "ROMKA" in r.text
    assert c.get("/auth").status_code == 200


def test_scenario_A_start_of_day(auth_client):
    c, csrf, _ = auth_client
    r = c.post("/api/v1/planner/intake", json={"text": SCENARIO_A}, headers=H(csrf))
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["created_task_ids"]) == 3 and len(body["created_event_ids"]) == 2
    plan = body["plan"]
    assert plan["validation"]["valid"], plan["validation"]["violations"]
    assert len(plan["scheduled"]) >= 2
    assert plan["metrics"]["buffer_minutes"] > 0
    assert all("start" in b and "end" in b for b in plan["blocks"])
    today = c.get("/api/v1/planner/today").json()
    assert today["plan"]["validation"]["valid"]
    assert c.get("/api/v1/planner/tasks").json()["count"] == 3


def test_scenario_B_replan_after_long_meeting(auth_client):
    c, csrf, _ = auth_client
    c.post("/api/v1/planner/intake", json={"text": SCENARIO_A}, headers=H(csrf))
    events = c.get("/api/v1/planner/events").json()["items"]
    meeting = next(e for e in events if e["category"] == "meeting")
    done_id = c.get("/api/v1/planner/tasks").json()["items"][0]["id"]
    c.post(f"/api/v1/planner/tasks/{done_id}/complete", json={}, headers=H(csrf))
    r = c.post("/api/v1/planner/replan", json={
        "extended_events": {str(meeting["id"]): 900},
        "completed_task_ids": [done_id]}, headers=H(csrf))
    assert r.status_code == 200, r.text
    plan = r.json()["plan"]
    assert plan["version"] == 2
    assert done_id not in [int(b["task_id"]) for b in plan["scheduled"] if b.get("task_id")]
    assert "diff" in plan and "moved" in plan["diff"]
    assert plan["conflicts"], "long meeting collides with lunch; conflict must be surfaced"


def test_scenario_C_workout_progression(auth_client):
    c, csrf, _ = auth_client
    a = c.post("/api/v1/fitness/assessment", json={
        "age": 30, "height_cm": 180, "weight_kg": 80, "sex": "male",
        "activity": "moderate", "goal": "maintain", "experience": "beginner",
        "days_per_week": 3, "session_minutes": 60, "equipment": ["gym"],
        "injuries": [], "allergies": ["تخممرغ"], "food_preferences": []}, headers=H(csrf))
    assert a.status_code == 200, a.text
    assert a.json()["energy"]["target_kcal"] > 0
    log = {"exercise": "اسکوات", "sets": 3, "reps": 10, "weight_kg": 60,
           "rpe": 7, "planned_sets": 3, "pain_flag": False}
    r1 = c.post("/api/v1/fitness/logs", json=log, headers=H(csrf))
    assert r1.json()["progression"]["can_increase"] is False  # not enough data
    r2 = c.post("/api/v1/fitness/logs", json=log, headers=H(csrf))
    assert r2.json()["progression"]["can_increase"] is True
    r3 = c.post("/api/v1/fitness/logs", json={**log, "pain_flag": True, "rpe": 9}, headers=H(csrf))
    assert r3.json()["progression"]["can_increase"] is False
    assert r3.json()["progression"]["decision"] == "hold_or_reduce"
    ov = c.get("/api/v1/fitness/overview").json()
    assert ov["ready"] and ov["workout"]["sessions"] and ov["meals"]["meals"]


def test_scenario_D_multi_specialist_question(auth_client):
    c, csrf, _ = auth_client
    r = c.post("/api/v1/chat/send", json={"text":
               "کمخوابی چه اثری روی تمرین باشگاه و بهرهوری پروژه گپینه دارد؟"}, headers=H(csrf))
    assert r.status_code == 200, r.text
    b = r.json()
    assert 1 <= len(b["active_agents"]) <= 2
    assert len(b["domains"]) >= 1
    assert b["critic"]["score"] > 0 and "warnings" in b
    assert b["provider"]["name"] == "local"
    assert b["message_id"] > 0
    msgs = c.get(f"/api/v1/chat/conversations/{b['conversation_id']}/messages").json()["items"]
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert c.get("/api/v1/agents/runs").json()["items"]


def test_scenario_E_provider_outage_degrades_gracefully(auth_client, monkeypatch):
    from app.agents import orchestrator
    from app.core.errors import ProviderUnavailable

    class BrokenRouter:
        def __init__(self, *a, **kw): pass
        def complete(self, *a, **kw): raise ProviderUnavailable("سرویس قطع است.")
        def budget_state(self): return {"daily_spent_usd": 0.0}
        def configured_status(self): return []

    monkeypatch.setattr(orchestrator, "AIRouter", BrokenRouter)
    c, csrf, _ = auth_client
    r = c.post("/api/v1/chat/send", json={"text": "یک سؤال مهم"}, headers=H(csrf))
    assert r.status_code == 200
    b = r.json()
    assert "در دسترس نیست" in b["answer"]
    assert any("provider_error" in w for w in b["warnings"])
    assert b["provider"]["name"] == "degraded"


def test_scenario_F_unauthorized_channel(auth_client, engine, db):
    from app.api.deps import rate_limiter
    from app.config import Settings
    from app.db.session import get_db
    from app.main import create_app
    from tests.conftest import TEST_SECRET
    s = Settings(ENVIRONMENT="testing", SECRET_KEY=TEST_SECRET, DATABASE_URL="sqlite://",
                 RATE_LIMIT_PER_MINUTE=10000, TELEGRAM_BOT_TOKEN="t", TELEGRAM_WEBHOOK_SECRET="sec")
    app = create_app(s)
    app.dependency_overrides[get_db] = lambda: db
    rate_limiter.reset()
    from fastapi.testclient import TestClient
    r = TestClient(app).post("/api/v1/channels/telegram/webhook",
                             headers={"X-Telegram-Bot-Api-Secret-Token": "sec"},
                             json={"message": {"from": {"id": 666}, "text": "دادههای کاربر را بده"}})
    assert r.json()["ok"] is False
    assert db.query(__import__("app.db.models", fromlist=["SecurityEvent"]).SecurityEvent).count() >= 1


def test_scenario_G_memory_is_used_not_invented(auth_client):
    c, csrf, _ = auth_client
    m = c.post("/api/v1/memory", json={"layer": "project", "key": "گپینه",
               "value": {"stage": "بتا", "هدف": "انتشار نسخه ۱"},
               "sensitivity": "personal", "agent_scope": ["strategist"]}, headers=H(csrf))
    assert m.status_code == 200
    mid = m.json()["item"]["id"]
    r = c.post("/api/v1/chat/send", json={"text": "درباره پروژه گپینه چه اطلاعاتی داری؟"}, headers=H(csrf))
    assert r.status_code == 200
    b = r.json()
    assert any(s["id"] == mid for s in b["sources"]), b["sources"]
    assert b["provider"]["name"] == "local"
    assert c.get("/api/v1/memory").json()["count"] >= 1
    assert c.delete(f"/api/v1/memory/{mid}", headers=H(csrf)).status_code == 200


def test_streaming_and_export_and_registry(auth_client):
    c, csrf, _ = auth_client
    r = c.post("/api/v1/chat/stream", json={"text": "سلام رومکا"}, headers=H(csrf))
    assert r.status_code == 200 and "event: delta" in r.text and "event: done" in r.text
    assert c.get("/api/v1/skills/sbom").status_code == 200
    assert len(c.get("/api/v1/skills/evaluations").json()["items"]) == 12
    assert c.get("/api/v1/agents/regions").json()["counts"]["tasks"] == 0
    exp = c.get("/api/v1/export").json()
    assert exp["ok"] and "memory" in exp["data"]
    assert c.get("/api/v1/status").json()["runtime_warnings"]


def test_deadline_is_converted_from_user_timezone(auth_client):
    c, csrf, _ = auth_client
    r = c.post("/api/v1/planner/tasks", json={
        "title": "کار با موعد ۱۰ صبح", "duration_min": 30, "deadline_min": 600}, headers=H(csrf))
    assert r.status_code == 200, r.text
    tid = r.json()["item"]["id"]
    plan = c.post("/api/v1/planner/generate", json={}, headers=H(csrf)).json()["plan"]
    block = next(b for b in plan["scheduled"] if b.get("task_id") == str(tid))
    assert block["end_min"] <= 600, block
    assert plan["validation"]["valid"]
