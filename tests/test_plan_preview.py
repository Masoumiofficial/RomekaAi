"""Read-only previews and explicit, owner-scoped plan activation."""
from app.db.models import Plan, Task
from tests.conftest import H

DAY = "2026-10-28"


def add_task(c, csrf, title="کار واقعی"):
    r = c.post('/api/v1/planner/tasks', headers=H(csrf), json={"title": title, "duration_min": 30})
    assert r.status_code == 200, r.text
    return r.json()['item']['id']


def preview(c, csrf, **kwargs):
    r = c.post('/api/v1/planner/preview', headers=H(csrf), json={"date": DAY, **kwargs})
    assert r.status_code == 200, r.text
    return r.json()


def test_preview_is_read_only_and_confirm_preserves_existing_plan(auth_client, db):
    c, csrf, uid = auth_client
    task_id = add_task(c, csrf)
    old = c.post('/api/v1/planner/generate', headers=H(csrf), json={"date": DAY}).json()['plan']
    old_id = old['plan_id']
    before = db.get(Plan, old_id).payload
    count = db.query(Plan).filter_by(user_id=uid).count()
    task = db.get(Task, task_id)
    previous_status, previous_date = task.status, task.planned_for
    assert c.post('/api/v1/planner/preview', json={"date": DAY}).status_code == 403
    draft = preview(c, csrf)
    assert draft['token'] and draft['active_plan_id'] == old_id
    assert draft['plan']['plan_id'] is None and draft['plan']['validation']['valid']
    assert db.query(Plan).filter_by(user_id=uid).count() == count
    assert (task.status, task.planned_for) == (previous_status, previous_date)
    assert db.get(Plan, old_id).is_active
    assert c.post('/api/v1/planner/preview/confirm', json={"token":draft['token']}).status_code == 403
    saved = c.post('/api/v1/planner/preview/confirm', headers=H(csrf), json={"token":draft['token']})
    assert saved.status_code == 200, saved.text
    new_id = saved.json()['plan_db_id']
    db.expire_all()
    assert new_id != old_id and db.get(Plan, old_id).payload == before
    assert not db.get(Plan, old_id).is_active and db.get(Plan, new_id).is_active
    assert c.get(f'/api/v1/planner/today?day={DAY}').json()['plan_db_id'] == new_id
    # Replaying the same signed preview cannot overwrite the newer active plan.
    assert c.post('/api/v1/planner/preview/confirm', headers=H(csrf), json={"token":draft['token']}).status_code == 409
    assert db.query(Plan).filter_by(user_id=uid).count() == count + 1


def test_preview_rejects_changed_tasks_and_active_plan(auth_client, db):
    c, csrf, uid = auth_client
    tid = add_task(c, csrf)
    draft = preview(c, csrf)
    task = db.get(Task, tid); task.title = "عنوان تغییر کرده"; db.flush()
    assert c.post('/api/v1/planner/preview/confirm', headers=H(csrf), json={"token":draft['token']}).status_code == 409
    assert db.query(Plan).filter_by(user_id=uid).count() == 0
    draft = preview(c, csrf)
    assert c.post('/api/v1/planner/generate', headers=H(csrf), json={"date":DAY}).status_code == 200
    assert c.post('/api/v1/planner/preview/confirm', headers=H(csrf), json={"token":draft['token']}).status_code == 409
    assert db.query(Plan).filter_by(user_id=uid).count() == 1


def test_preview_rejects_tampering_expiry_and_other_users(auth_client, db, monkeypatch):
    c, csrf, uid = auth_client
    token = preview(c, csrf)['token']
    # Signature is not accepted after modification.
    r = c.post('/api/v1/planner/preview/confirm', headers=H(csrf), json={"token":token + 'x'})
    assert r.status_code == 409
    from app.api import planner
    monkeypatch.setattr(planner, 'PREVIEW_MAX_AGE', -1)
    assert c.post('/api/v1/planner/preview/confirm', headers=H(csrf), json={"token":token}).status_code == 409
    monkeypatch.setattr(planner, 'PREVIEW_MAX_AGE', 900)
    other = c.post('/api/v1/auth/register', json={"email":"other-preview@example.com", "password":"RomkaDemo2026!", "display_name":"دیگری", "timezone":"Asia/Tehran"})
    assert other.status_code == 200
    other_csrf = other.json()['csrf_token']
    assert c.post('/api/v1/planner/preview/confirm', headers=H(other_csrf), json={"token":token}).status_code == 409
    assert db.query(Plan).filter_by(user_id=uid).count() == 0
    assert db.query(Plan).filter_by(user_id=other.json()['user']['id']).count() == 0


def test_invalid_preview_cannot_be_activated(auth_client, db):
    c, csrf, uid = auth_client
    for title, start, end in [('جلسه اول', 600, 660), ('جلسه دوم', 630, 690)]:
        r = c.post(f'/api/v1/planner/events?day={DAY}', headers=H(csrf),
                   json={'title':title, 'start_min':start, 'end_min':end})
        assert r.status_code == 200, r.text
    draft = preview(c, csrf)
    assert not draft['plan']['validation']['valid'] and draft['plan']['conflicts']
    assert draft['token'] is None
    assert db.query(Plan).filter_by(user_id=uid).count() == 0


def test_two_simultaneous_confirmations_do_not_both_activate(tmp_path):
    """Real file-backed SQLite, separate DB sessions and competing HTTP requests."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import Session
    from app.config import Settings
    from app.db.base import Base
    from app.db.session import get_db
    from app.main import create_app
    from tests.conftest import TEST_SECRET

    engine = create_engine('sqlite:///' + (tmp_path / 'race.sqlite').as_posix(),
                           connect_args={'check_same_thread': False, 'timeout': 10})
    @event.listens_for(engine, 'connect')
    def pragmas(conn, _):
        conn.execute('PRAGMA foreign_keys=ON')
        conn.execute('PRAGMA journal_mode=WAL')
    Base.metadata.create_all(engine)
    app = create_app(Settings(ENVIRONMENT='testing', SECRET_KEY=TEST_SECRET,
                              DATABASE_URL='sqlite://', RATE_LIMIT_PER_MINUTE=10000))
    def session_override():
        with Session(engine, expire_on_commit=False) as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise
    app.dependency_overrides[get_db] = session_override
    client = TestClient(app)
    reg = client.post('/api/v1/auth/register', json={'email':'race@example.com',
                      'password':'RomkaDemo2026!', 'timezone':'Asia/Tehran'}).json()
    headers = {'Authorization':'Bearer ' + reg['session_token'], 'X-CSRF-Token':reg['csrf_token']}
    draft = client.post('/api/v1/planner/preview', headers=headers, json={'date':DAY}).json()
    gate = Barrier(2)
    def confirm(_):
        gate.wait(timeout=10)
        isolated_client = TestClient(app)
        return isolated_client.post('/api/v1/planner/preview/confirm',
                                    headers=headers, json={'token':draft['token']}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = sorted(pool.map(confirm, range(2)))
    assert codes == [200, 409]
    with Session(engine) as s:
        plans = s.query(Plan).filter_by(user_id=reg['user']['id']).all()
        assert len(plans) == 1 and plans[0].is_active
    engine.dispose()


def test_preview_uses_account_today_and_low_energy(auth_client):
    c, csrf, _ = auth_client
    today = c.get('/api/v1/planner/today').json()['date']
    r = c.post('/api/v1/planner/preview', headers=H(csrf), json={'energy_mode':'low'})
    assert r.status_code == 200
    body = r.json()
    assert body['plan']['date'] == today and body['plan']['energy_mode'] == 'low'
    saved = c.post('/api/v1/planner/preview/confirm', headers=H(csrf), json={'token':body['token']})
    assert saved.status_code == 200 and saved.json()['plan']['energy_mode'] == 'low'


def test_changed_fixed_event_rejects_preview(auth_client, db):
    c, csrf, uid = auth_client
    draft = preview(c, csrf)
    r = c.post(f'/api/v1/planner/events?day={DAY}', headers=H(csrf),
               json={'title':'جلسه جدید', 'start_min':600, 'end_min':660})
    assert r.status_code == 200
    assert c.post('/api/v1/planner/preview/confirm', headers=H(csrf), json={'token':draft['token']}).status_code == 409
    assert db.query(Plan).filter_by(user_id=uid).count() == 0
