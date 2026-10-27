from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import rate_limiter
from app.bootstrap import bootstrap
from app.config import Settings
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app

TEST_SECRET = "test-only-secret-key-not-for-production-abcdefghijklmnop"


@pytest.fixture
def engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False},
                        poolclass=StaticPool, future=True)
    import app.db.models  # noqa: F401
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture
def db(engine):
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    s = Session()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def settings():
    return Settings(
        ENVIRONMENT="testing", SECRET_KEY=TEST_SECRET, DATABASE_URL="sqlite://",
        RATE_LIMIT_PER_MINUTE=10000, ROMKA_AUTO_DEMO=True,
        AI_PRIMARY_PROVIDER="local", AI_DAILY_BUDGET_USD=1.0,
        AI_MONTHLY_BUDGET_USD=20.0, AI_MAX_CALLS_PER_REQUEST=3,
        AI_MAX_RETRIES=1, AI_ALLOW_FALLBACK=False,
    )


@pytest.fixture
def client(engine, db, settings):
    app = create_app(settings)
    app.dependency_overrides[get_db] = lambda: db
    rate_limiter.reset()
    bootstrap(db)
    db.commit()
    return TestClient(app)


@pytest.fixture
def auth_client(client):
    """A client with a real registered user and its CSRF token."""
    r = client.post("/api/v1/auth/register", json={
        "email": "owner@romka.local", "password": "RomkaDemo2026!",
        "display_name": "مالک رومکا", "timezone": "Asia/Tehran"})
    assert r.status_code == 200, r.text
    csrf = r.json()["csrf_token"]
    return client, csrf, r.json()["user"]["id"]


def H(csrf, extra=None):
    h = {"X-CSRF-Token": csrf}
    if extra:
        h.update(extra)
    return h
