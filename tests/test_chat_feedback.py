"""User-owned, optional response feedback is local, reversible and bounded."""
from app.db.models import Conversation, Message, MessageFeedback, User
from tests.conftest import H


def test_rate_update_reason_export_and_delete(auth_client, db):
    c, csrf, uid = auth_client
    response = c.post('/api/v1/chat/send', json={'text': 'سلام'}, headers=H(csrf)).json()
    mid, conv = response['message_id'], response['conversation_id']
    path = f'/api/v1/chat/messages/{mid}/feedback'
    assert c.get('/api/v1/chat/feedback/summary').json()['total'] == 0
    assert c.put(path, json={'rating': 'helpful'}).status_code == 403
    assert c.put(path, headers=H(csrf), json={'rating': 'helpful'}).status_code == 200
    assert c.put(path, headers=H(csrf), json={'rating': 'not_helpful', 'reason': 'incorrect'}).status_code == 200
    assert db.query(MessageFeedback).filter_by(user_id=uid, message_id=mid).count() == 1
    feedback = c.get(f'/api/v1/chat/conversations/{conv}/messages').json()['items'][-1]['feedback']
    assert feedback == {'rating': 'not_helpful', 'reason': 'incorrect'}
    assert c.get('/api/v1/chat/feedback/summary').json() == {'ok': True, 'helpful': 0, 'not_helpful': 1, 'total': 1}
    exported = c.get('/api/v1/export').json()['data']['feedback']
    assert exported == [{'message_id': mid, 'rating': 'not_helpful', 'reason': 'incorrect'}]
    assert c.put(path, headers=H(csrf), json={'rating': 'helpful', 'reason': 'unsafe'}).json()['feedback']['reason'] == ''
    assert c.delete(path, headers=H(csrf)).status_code == 200
    assert c.delete(path, headers=H(csrf)).status_code == 200
    assert c.get('/api/v1/chat/feedback/summary').json()['total'] == 0
    assert c.get('/api/v1/export').json()['data']['feedback'] == []


def test_feedback_rejects_unknown_values_and_user_messages(auth_client, db):
    c, csrf, _ = auth_client
    response = c.post('/api/v1/chat/send', json={'text': 'سلام'}, headers=H(csrf)).json()
    path = f"/api/v1/chat/messages/{response['message_id']}/feedback"
    assert c.put(path, headers=H(csrf), json={'rating': 'okay'}).status_code == 422
    assert c.put(path, headers=H(csrf), json={'rating': 'not_helpful', 'reason': '<script>'}).status_code == 422
    user_msg = db.query(Message).filter_by(conversation_id=response['conversation_id'], role='user').one()
    assert c.put(f'/api/v1/chat/messages/{user_msg.id}/feedback', headers=H(csrf), json={'rating':'helpful'}).status_code == 404
    assert db.query(MessageFeedback).count() == 0


def test_other_users_feedback_and_message_are_isolated(auth_client, db):
    c, csrf, _ = auth_client
    other = User(email='else@example.com', password_hash='unused')
    db.add(other); db.flush()
    conv = Conversation(user_id=other.id)
    db.add(conv); db.flush()
    msg = Message(conversation_id=conv.id, role='assistant', content='private')
    db.add(msg); db.flush()
    db.add(MessageFeedback(user_id=other.id, message_id=msg.id, rating='helpful', reason=''))
    db.flush()
    path = f'/api/v1/chat/messages/{msg.id}/feedback'
    assert c.put(path, headers=H(csrf), json={'rating':'helpful'}).status_code == 404
    assert c.delete(path, headers=H(csrf)).status_code == 404
    assert c.get(f'/api/v1/chat/conversations/{conv.id}/messages').status_code == 404
    assert c.get('/api/v1/chat/feedback/summary').json()['total'] == 0
    assert c.get('/api/v1/export').json()['data']['feedback'] == []


def test_chat_page_feedback_ui(client):
    page = client.get('/chat').text
    assert 'feedback-summary' in page and 'بازخوردهای من' in page


def test_migration_preserves_existing_conversation(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    root = Path(__file__).resolve().parents[1]
    url = 'sqlite:///' + (tmp_path / 'existing.sqlite').as_posix()
    env = {**os.environ, 'DATABASE_URL': url}

    def alembic(*args):
        subprocess.run([sys.executable, '-m', 'alembic', *args], cwd=root, env=env,
                       check=True, capture_output=True, text=True, timeout=30)

    alembic('upgrade', '66c743d0c078')
    engine = create_engine(url)
    with Session(engine) as session:
        user = User(email='migration@example.com', password_hash='unused')
        session.add(user); session.flush()
        conv = Conversation(user_id=user.id, title='قدیمی')
        session.add(conv); session.flush()
        msg = Message(conversation_id=conv.id, role='assistant', content='داده قبلی')
        session.add(msg); session.commit()
        uid, mid = user.id, msg.id
    alembic('upgrade', 'head')
    with Session(engine) as session:
        assert session.get(Message, mid).content == 'داده قبلی'
        session.add(MessageFeedback(user_id=uid, message_id=mid, rating='helpful'))
        session.commit()
    # Destructive downgrade is exercised ONLY on this disposable test DB.
    alembic('downgrade', '66c743d0c078')
    alembic('upgrade', 'head')
    with Session(engine) as session:
        assert session.get(Message, mid).content == 'داده قبلی'
        assert session.query(MessageFeedback).count() == 0
    engine.dispose()


def test_core_windows_runner_does_not_start_after_migration_failure():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    script = (root / 'scripts' / 'run_dev.ps1').read_text(encoding='ascii')
    assert 'throw "alembic upgrade failed; server was not started"' in script
