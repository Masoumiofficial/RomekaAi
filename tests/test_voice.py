"""Optional voice widget uses existing, authorized APIs; no real speech service."""
from pathlib import Path
import shutil
import subprocess

import pytest

from app.db.models import ActionRecord, MemoryItem, Task, User
from tests.conftest import H

ROOT = Path(__file__).resolve().parents[1]


def test_voice_widget_is_on_every_workspace_page(client):
    for path in ("/", "/chat", "/planner", "/agents", "/business", "/health", "/memory", "/settings", "/onboarding"):
        response = client.get(path)
        assert response.status_code == 200
        for item in ("voice-widget", "voice-mic", "voice-text", "voice-confirm", "voice-plan-confirm", "voice-today", "voice-preview", '/static/js/voice.js?v=0.2.19'):
            assert item in response.text
        assert 'id="voice-panel" class="voice-panel card" aria-label="دستیار صوتی رومکا" hidden' in response.text
    assert client.get('/static/js/voice.js').status_code == 200


def test_voice_browser_simulation():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is needed to simulate the browser APIs")
    subprocess.run([node, "tests/voice_widget_test.js"], cwd=ROOT, check=True, timeout=30)


def test_voice_chat_disables_implicit_memory_writes(auth_client, db):
    c, csrf, uid = auth_client
    text = "به خاطر بسپار نام پروژه من ستاره است"
    response = c.post('/api/v1/chat/send', headers=H(csrf),
                      json={"text": text, "allow_remember": False})
    assert response.status_code == 200, response.text
    assert response.json()['remembered'] is None
    assert db.query(MemoryItem).filter_by(user_id=uid).count() == 0
    assert db.query(ActionRecord).filter_by(user_id=uid).count() == 0
    # The existing chat's opt-in default behavior remains unchanged.
    response = c.post('/api/v1/chat/send', headers=H(csrf), json={"text": text})
    assert response.status_code == 200 and response.json()['remembered']
    assert db.query(MemoryItem).filter_by(user_id=uid).count() == 1


def test_task_api_for_voice_keeps_csrf_and_owner_isolation(auth_client, db):
    c, csrf, uid = auth_client
    data = {"title": "کاری از دستیار", "duration_min": 30}
    assert c.post('/api/v1/planner/tasks', json=data).status_code == 403
    r = c.post('/api/v1/planner/tasks', headers=H(csrf), json=data)
    assert r.status_code == 200 and r.json()['item']['title'] == data['title']
    other = User(email='voice-other@example.com', password_hash='unused')
    db.add(other); db.flush()
    secret = Task(user_id=other.id, title='other private task', duration_min=30)
    db.add(secret); db.flush()
    listed = c.get('/api/v1/planner/tasks').json()['items']
    assert any(t['title'] == data['title'] for t in listed)
    assert all(t['id'] != secret.id for t in listed)
    assert db.query(Task).filter_by(user_id=uid, title=data['title']).count() == 1
