"""User-reviewed day intake: no provider, no implicit writes, atomic commit."""
from uuid import uuid4

from app.db.models import ActionRecord, FixedEvent, Plan, Task, User
from app.planning.day_draft import propose_day
from tests.conftest import H


def test_parser_does_not_invent_time_or_duration():
    p = propose_day('جلسه ساعت ۶، خرید، جلسه ساعت ۹ صبح برای ۹۰ دقیقه')
    assert len(p['items']) == 3
    assert p['items'][0]['kind'] == 'event' and p['items'][0]['start_min'] is None
    assert p['items'][0]['duration_min'] is None and p['items'][0]['end_min'] is None
    assert p['items'][1]['kind'] == 'task' and p['items'][1]['duration_min'] is None
    assert p['items'][2]['start_min'] == 540 and p['items'][2]['end_min'] == 630
    assert propose_day('جلسه ساعت ۱۴:۳۰ به مدت ۲ ساعت و نیم')['items'][0]['end_min'] == 1020
    assert len(propose_day('نوشتن گزارش ۲ ساعت و نیم')['items']) == 1
    assert propose_day('جلسه فردا ساعت ۱۴')['date_uncertain']
    assert propose_day('جلسه ساعت ۱۲')['items'][0]['start_min'] is None
    assert propose_day('جلسه ساعت ۹ و نیم صبح')['items'][0]['start_min'] == 570
    assert propose_day('جلسه 2026-10-29')['date_uncertain']


def test_parse_is_read_only_csrf_and_no_model(auth_client, db, monkeypatch):
    from app.agents import orchestrator
    c, csrf, uid = auth_client
    def disallow(*args, **kwargs):
        raise AssertionError('No model should be called for parsing')
    monkeypatch.setattr(orchestrator, 'AIRouter', disallow)
    assert c.post('/api/v1/planner/day-draft/parse', json={'text':'جلسه'}).status_code == 403
    response = c.post('/api/v1/planner/day-draft/parse', headers=H(csrf),
                      json={'text':'جلسه فردا ساعت ۶، خرید'})
    assert response.status_code == 200, response.text
    assert response.json()['suggested_date'] is None
    assert db.query(Task).filter_by(user_id=uid).count() == 0
    assert db.query(FixedEvent).filter_by(user_id=uid).count() == 0
    assert db.query(Plan).filter_by(user_id=uid).count() == 0
    assert db.query(ActionRecord).filter_by(user_id=uid).count() == 0


def test_commit_explicit_items_atomic_replay_and_existing_plan(auth_client, db):
    c, csrf, uid = auth_client
    old = c.post('/api/v1/planner/generate', headers=H(csrf), json={'date':'2026-10-28'}).json()['plan']
    old_id = old['plan_id']
    body = {'date':'2026-10-28','request_id':str(uuid4()),
            'tasks':[{'title':'خرید','duration_min':30}],
            'events':[{'title':'جلسه','start_min':540,'end_min':600,'category':'meeting'}]}
    assert c.post('/api/v1/planner/day-draft/commit', json=body).status_code == 403
    first = c.post('/api/v1/planner/day-draft/commit', headers=H(csrf), json=body)
    assert first.status_code == 200, first.text
    assert not first.json()['replayed']
    assert len(first.json()['task_ids']) == len(first.json()['event_ids']) == 1
    second = c.post('/api/v1/planner/day-draft/commit', headers=H(csrf), json=body)
    assert second.status_code == 200 and second.json()['replayed']
    assert second.json()['task_ids'] == first.json()['task_ids']
    changed = {**body, 'tasks':[{'title':'دیگر','duration_min':30}]}
    assert c.post('/api/v1/planner/day-draft/commit', headers=H(csrf), json=changed).status_code == 409
    assert db.query(Task).filter_by(user_id=uid).count() == 1
    assert db.query(FixedEvent).filter_by(user_id=uid).count() == 1
    assert db.query(Plan).filter_by(user_id=uid).count() == 1 and db.get(Plan, old_id).is_active
    rec = db.query(ActionRecord).filter_by(user_id=uid, tool='planner.day_draft').one()
    assert set(rec.inputs) == {'payload_sha256'} and 'خرید' not in str(rec.inputs)
    assert c.post(f'/api/v1/actions/{rec.id}/approve?approve=false', headers=H(csrf)).status_code == 422
    assert c.post('/api/v1/planner/day-draft/commit', headers=H(csrf), json=body).json()['replayed']


def test_same_request_id_is_isolated_between_users(auth_client, db):
    c, csrf, uid = auth_client
    body = {'date':'2026-10-28','request_id':str(uuid4()),
            'tasks':[{'title':'کار اول','duration_min':30}]}
    first = c.post('/api/v1/planner/day-draft/commit', headers=H(csrf), json=body)
    assert first.status_code == 200
    other = c.post('/api/v1/auth/register', json={'email':'draft-second@example.com',
                   'password':'RomkaDemo2026!', 'timezone':'Asia/Tehran'}).json()
    second_body = {**body, 'tasks':[{'title':'کار دوم','duration_min':60}]}
    second = c.post('/api/v1/planner/day-draft/commit', headers=H(other['csrf_token']), json=second_body)
    assert second.status_code == 200 and not second.json()['replayed']
    assert db.query(Task).filter_by(user_id=uid).one().title == 'کار اول'
    assert db.query(Task).filter_by(user_id=other['user']['id']).one().title == 'کار دوم'


def test_invalid_commit_is_all_or_nothing_and_isolated(auth_client, db):
    c, csrf, uid = auth_client
    body = {'date':'2026-10-28','request_id':str(uuid4()),
            'tasks':[{'title':'کار','duration_min':30}],
            'events':[{'title':'جلسه','start_min':700,'end_min':600}]}
    assert c.post('/api/v1/planner/day-draft/commit', headers=H(csrf), json=body).status_code == 422
    assert db.query(Task).filter_by(user_id=uid).count() == 0
    assert db.query(FixedEvent).filter_by(user_id=uid).count() == 0
    assert db.query(ActionRecord).filter_by(user_id=uid, tool='planner.day_draft').count() == 0
    assert c.post('/api/v1/planner/day-draft/commit', headers=H(csrf), json={**body,'events':[],'tasks':[]}).status_code == 422
    assert c.post('/api/v1/planner/day-draft/commit', headers=H(csrf), json={**body,'events':[],'tasks':[{'title':'کار'}]}).status_code == 422
    other = User(email='draft-other@example.com', password_hash='unused'); db.add(other); db.flush()
    db.add(Task(user_id=other.id,title='خصوصی',duration_min=60)); db.flush()
    parsed = c.post('/api/v1/planner/day-draft/parse',headers=H(csrf),json={'text':'خرید'}).json()
    assert 'خصوصی' not in str(parsed)


def test_real_sqlite_atomic_rollback_and_simultaneous_retry(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import Session
    from app.api import planner
    from app.config import Settings
    from app.db.base import Base
    from app.db.session import get_db
    from app.main import create_app
    from tests.conftest import TEST_SECRET

    engine = create_engine('sqlite:///' + (tmp_path / 'draft.sqlite').as_posix(),
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
    client = TestClient(app, raise_server_exceptions=False)
    reg = client.post('/api/v1/auth/register', json={'email':'draft-race@example.com',
                      'password':'RomkaDemo2026!', 'timezone':'Asia/Tehran'}).json()
    headers = {'Authorization':'Bearer ' + reg['session_token'], 'X-CSRF-Token':reg['csrf_token']}
    body = {'date':'2026-10-28','request_id':str(uuid4()),
            'tasks':[{'title':'کار','duration_min':30}],
            'events':[{'title':'جلسه','start_min':540,'end_min':600}]}
    # Crash after rows have been flushed but before the idempotency record exists.
    with monkeypatch.context() as patch:
        def fail():
            raise RuntimeError('injected failure')
        patch.setattr(planner, 'utcnow', fail)
        assert client.post('/api/v1/planner/day-draft/commit', headers=headers, json=body).status_code == 500
    with Session(engine) as s:
        assert s.query(Task).count() == 0 and s.query(FixedEvent).count() == 0
        assert s.query(ActionRecord).filter_by(tool='planner.day_draft').count() == 0
    gate = Barrier(2)
    def commit(_):
        gate.wait(timeout=10)
        return TestClient(app).post('/api/v1/planner/day-draft/commit', headers=headers, json=body)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(commit, range(2)))
    assert [r.status_code for r in responses] == [200, 200]
    assert sorted(r.json()['replayed'] for r in responses) == [False, True]
    assert responses[0].json()['task_ids'] == responses[1].json()['task_ids']
    with Session(engine) as s:
        assert s.query(Task).count() == 1 and s.query(FixedEvent).count() == 1
        assert s.query(ActionRecord).filter_by(tool='planner.day_draft').count() == 1
    engine.dispose()


def test_day_draft_requires_auth(client):
    assert client.post('/api/v1/planner/day-draft/parse', headers=H('x'), json={'text':'کار'}).status_code in (401, 403)
    assert client.post('/api/v1/planner/day-draft/commit', headers=H('x'), json={}).status_code in (401, 403)


def test_day_draft_node_ui():
    import shutil
    import subprocess
    import pytest
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js is needed to simulate the browser DOM')
    subprocess.run([node, 'tests/day_draft_widget_test.js'], check=True, timeout=30)
