from __future__ import annotations

from app.core.security import (
    SessionSigner, constant_time_equal, hash_password, new_csrf_token, verify_password,
)
from app.logging_conf import redact
from tests.conftest import H, TEST_SECRET


def test_password_hashing_is_salted_and_verifiable():
    a = hash_password("correct horse battery staple")
    b = hash_password("correct horse battery staple")
    assert a != b, "salts must make hashes differ"
    assert a.startswith("pbkdf2_sha256$260000$")
    assert verify_password("correct horse battery staple", a)
    assert not verify_password("wrong", a)
    assert not verify_password("x", "garbage")


def test_session_tamper_and_expiry():
    s = SessionSigner(TEST_SECRET, 3600)
    token = s.create(7, new_csrf_token())
    assert s.read(token) is not None
    assert s.read(token + "tamper") is None
    assert s.read("nonsense") is None
    assert SessionSigner(TEST_SECRET, -1).read(token) is None  # forced expiry


def test_csrf_token_compare():
    assert constant_time_equal("abc", "abc")
    assert not constant_time_equal("abc", "abd")


def test_secret_redaction_in_logs():
    assert "***REDACTED***" in redact("api_key=supersecretvalue and password: hunter2")
    assert "supersecretvalue" not in redact("api_key=supersecretvalue")


def test_csrf_required_on_state_changing_api(client, auth_client):
    c, csrf, _ = auth_client
    r = c.post("/api/v1/memory", json={"layer": "preference", "key": "x", "value": {"a": 1}})
    assert r.status_code == 403 and r.json()["error"]["code"] == "csrf_failed"
    r2 = c.post("/api/v1/memory", json={"layer": "preference", "key": "x", "value": {"a": 1}},
                headers=H(csrf))
    assert r2.status_code == 200


def test_unauthenticated_access_denied(client):
    for path in ("/api/v1/profile", "/api/v1/memory", "/api/v1/planner/tasks",
                 "/api/v1/chat/conversations", "/api/v1/skills", "/api/v1/fitness/overview"):
        r = client.get(path)
        assert r.status_code == 401, (path, r.status_code, r.text)


def test_cross_user_data_isolation(client):
    r1 = client.post("/api/v1/auth/register", json={"email": "a@x.com", "password": "password123"})
    csrf1 = r1.json()["csrf_token"]
    c1 = client.post("/api/v1/memory", json={"layer": "preference", "key": "secret", "value": {"v": "A"}},
                     headers=H(csrf1))
    item_id = c1.json()["item"]["id"]
    r2 = client.post("/api/v1/auth/register", json={"email": "b@x.com", "password": "password123"})
    csrf2 = r2.json()["csrf_token"]
    mine = client.get("/api/v1/memory", headers=H(csrf2)).json()["items"]
    assert all(i["id"] != item_id for i in mine)
    assert client.delete(f"/api/v1/memory/{item_id}", headers=H(csrf2)).status_code in (403, 404)
    assert client.put(f"/api/v1/memory/{item_id}", json={"value": {"v": "hacked"}},
                      headers=H(csrf2)).status_code in (403, 404)
