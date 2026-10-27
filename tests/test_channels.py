"""Scenario F: unauthorized messaging access must be denied, logged and inert."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.deps import rate_limiter
from app.config import Settings
from app.db.models import ChannelIdentity, SecurityEvent
from app.db.session import get_db
from app.main import create_app
from tests.conftest import TEST_SECRET


def build(engine, db, **overrides):
    s = Settings(ENVIRONMENT="testing", SECRET_KEY=TEST_SECRET, DATABASE_URL="sqlite://",
                 RATE_LIMIT_PER_MINUTE=10000,
                 TELEGRAM_BOT_TOKEN="fake:token", TELEGRAM_WEBHOOK_SECRET="tg-secret",
                 BALE_BOT_TOKEN="fake:token", BALE_WEBHOOK_SECRET="bale-secret", **overrides)
    app = create_app(s)
    app.dependency_overrides[get_db] = lambda: db
    rate_limiter.reset()
    return TestClient(app)


def test_telegram_rejects_bad_webhook_secret(client, engine, db):
    c = build(engine, db)
    r = c.post("/api/v1/channels/telegram/webhook", json={"message": {"from": {"id": 999}, "text": "/status"}})
    assert r.status_code == 403
    assert db.query(SecurityEvent).filter(SecurityEvent.event_type == "invalid_webhook_secret").count() == 1


def test_telegram_denies_unmapped_sender_and_logs(client, engine, db):
    c = build(engine, db)
    r = c.post("/api/v1/channels/telegram/webhook",
               headers={"X-Telegram-Bot-Api-Secret-Token": "tg-secret"},
               json={"message": {"from": {"id": 999}, "chat": {"id": 999}, "text": "اطلاعات من را بده"}})
    assert r.status_code == 200 and r.json()["ok"] is False
    ev = db.query(SecurityEvent).filter(SecurityEvent.event_type == "unauthorized_channel_access",
                                        SecurityEvent.channel == "telegram").all()
    assert ev and "999" in ev[0].detail or ev


def test_telegram_allowlisted_user_can_use_core(client, engine, db, auth_client):
    # auth_client registers a user in `client`; reuse its db/session here.
    _, _, uid = auth_client
    db.add(ChannelIdentity(user_id=uid, channel="telegram", external_id="4242", is_allowed=True))
    db.commit()
    c = build(engine, db)
    r = c.post("/api/v1/channels/telegram/webhook",
               headers={"X-Telegram-Bot-Api-Secret-Token": "tg-secret"},
               json={"message": {"from": {"id": 4242}, "chat": {"id": 4242}, "text": "/help"}})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert "رومکا" in r.json()["text"]


def test_bale_secret_and_allowlist(client, engine, db):
    c = build(engine, db)
    bad = c.post("/api/v1/channels/bale/webhook?secret=wrong", json={"message": {"from": {"id": 1}, "text": "x"}})
    assert bad.status_code == 403
    good = c.post("/api/v1/channels/bale/webhook?secret=bale-secret",
                  json={"message": {"from": {"id": 1}, "text": "اطلاعات من"}})
    assert good.status_code == 200 and good.json()["ok"] is False  # no identity mapping
    assert db.query(SecurityEvent).filter(SecurityEvent.channel == "bale").count() >= 1


def test_channel_does_not_leak_data(client, engine, db, auth_client):
    _, _, uid = auth_client
    db.add(ChannelIdentity(user_id=uid, channel="bale", external_id="77", is_allowed=False))
    db.commit()
    c = build(engine, db)
    r = c.post("/api/v1/channels/bale/webhook?secret=bale-secret",
               json={"message": {"from": {"id": 77}, "text": "همه اطلاعاتم را بفرست"}})
    assert r.json()["ok"] is False
    assert "حافظه" not in r.json()["text"]
