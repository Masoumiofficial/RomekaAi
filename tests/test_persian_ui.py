"""Persian calendar is presentation-only; APIs continue to accept ISO dates."""
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_persian_calendar_round_trip_and_tehran_midnight():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is needed for the browser calendar tests")
    script = r'''
const assert = require('node:assert/strict');
const d = require('./app/web/static/js/persian-date.js');
assert.equal(d.display('2024-03-20'), '۱۴۰۳/۰۱/۰۱');
assert.equal(d.toISO('۱۴۰۳/۱۲/۳۰'), '2025-03-20');
assert.equal(d.toISO('١٤٠٤/١/١'), '2025-03-21');
assert.equal(d.toISO('1405/8/6'), '2026-10-28');
assert.equal(d.toISO('۱۴۰۴/۱۲/۳۰'), null);
assert.equal(d.toISO('۱۴۰۵/۰۷/۳۱'), null);
assert.equal(d.toISO('1405/13/01'), null);
assert.equal(d.toISO(''), null);
assert.equal(d.fromISO('2025-02-30'), '');
assert.equal(d.todayTehran(new Date('2026-03-20T20:29:59Z')), '2026-03-20');
assert.equal(d.todayTehran(new Date('2026-03-20T20:30:00Z')), '2026-03-21');
for (let t=Date.UTC(2020,0,1); t < Date.UTC(2031,0,1); t+=86400000) {
 const iso = new Date(t).toISOString().slice(0,10);
 assert.equal(d.toISO(d.fromISO(iso)), iso);
}
'''
    subprocess.run([node, "-e", script], cwd=ROOT, check=True, timeout=30)


def test_planner_and_project_show_persian_date_inputs(client):
    planner = client.get("/planner")
    business = client.get("/business")
    assert planner.status_code == business.status_code == 200
    assert 'id="plan-date"' in planner.text and "تاریخ شمسی" in planner.text
    assert 'id="proj-due"' in business.text and "موعد شمسی" in business.text
    assert 'src="/static/js/persian-date.js?v=' in planner.text
    assert 'type="date"' not in planner.text + business.text
    assert client.get("/static/js/persian-date.js").status_code == 200


def test_iso_api_dates_unchanged(auth_client):
    client, csrf, _ = auth_client
    h = {"X-CSRF-Token": csrf}
    r = client.post("/api/v1/planner/generate", headers=h, json={"date": "2025-03-21"})
    assert r.status_code == 200, r.text
    assert client.get("/api/v1/planner/today?day=2025-03-21").json()["date"] == "2025-03-21"
    r = client.post("/api/v1/data/projects", headers=h,
                    json={"name": "آزمون", "due_date": "2025-03-21"})
    assert r.status_code == 200, r.text
