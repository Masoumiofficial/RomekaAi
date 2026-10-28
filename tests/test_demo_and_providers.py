"""Demo account, cookie/iframe session transport, and provider verification.

These tests exercise the two real problems found in the embedded preview:
1. the login form pre-filled credentials that were never seeded;
2. third-party cookie blocking inside an iframe, which silently dropped the
   session cookie even though login itself succeeded.
"""
from __future__ import annotations

import json

import httpx

from app.ai.base import ChatMessage, ChatRequest
from app.ai.providers import GAPGPT_DEFAULT_BASE_URL, GapGPTProvider
from app.bootstrap import SAMPLE, seed_demo_account
from app.config import Settings, get_settings
from app.core.security import verify_password
from app.db.models import Goal, MemoryItem, Project, Task, User
from tests.conftest import H, TEST_SECRET


# ── demo account ────────────────────────────────────────────────────────────

def test_demo_account_is_seeded_once_with_labelled_sample_data(db, settings, client):
    first = seed_demo_account(db, settings)
    assert first["demo_user"] == "created"
    assert first["sample_rows"] > 0

    user = db.query(User).filter(User.email == settings.ROMKA_DEMO_EMAIL).one()
    assert verify_password(settings.ROMKA_DEMO_PASSWORD, user.password_hash)

    for model in (Project, Goal, Task, MemoryItem):
        rows = db.query(model).filter(model.user_id == user.id).all()
        assert rows, f"{model.__name__} sample rows missing"
    assert db.query(Task).filter(Task.user_id == user.id).first().title.startswith(SAMPLE)

    # Idempotent: restarting the app must not reset the password or duplicate data.
    again = seed_demo_account(db, settings)
    assert again["demo_user"] == "existing" and again["ready"] is True
    assert again["sample_rows"] == 0
    assert db.query(User).filter(User.email == settings.ROMKA_DEMO_EMAIL).count() == 1
    assert db.query(Task).filter(Task.user_id == user.id).count() == 3


def test_demo_account_never_created_in_production(db):
    prod = Settings(ENVIRONMENT="production", SECRET_KEY="p" * 48,
                    ROMKA_AUTO_DEMO=True, ROMKA_DEMO_EMAIL="owner@romka.local")
    out = seed_demo_account(db, prod)
    assert out["demo_user"] == "disabled"
    assert db.query(User).count() == 0


def test_existing_email_with_other_password_is_never_overwritten(db, settings):
    """A user's own registration must keep its password: no silent reset."""
    from app.core.security import hash_password
    from app.db.models import UserProfile
    u = User(email=settings.ROMKA_DEMO_EMAIL, display_name="مالک واقعی",
             password_hash=hash_password("my-own-secret-pw"))
    db.add(u); db.flush()
    db.add(UserProfile(user_id=u.id)); db.flush()

    out = seed_demo_account(db, settings)
    assert out["demo_user"] == "existing" and out["ready"] is False
    assert "بازنویسی" in out["reason"]
    db.refresh(u)
    assert verify_password("my-own-secret-pw", u.password_hash)
    assert not verify_password(settings.ROMKA_DEMO_PASSWORD, u.password_hash)
    assert db.query(Task).filter(Task.user_id == u.id).count() == 0


def test_existing_ready_demo_account_gets_sample_data_only_when_empty(db, settings):
    from app.core.security import hash_password
    u = User(email=settings.ROMKA_DEMO_EMAIL, display_name="دمو",
             password_hash=hash_password(settings.ROMKA_DEMO_PASSWORD))
    db.add(u); db.flush()
    out = seed_demo_account(db, settings)
    assert out["ready"] is True and out["sample_rows"] > 0
    assert db.query(Task).filter(Task.user_id == u.id).count() == 3


def test_demo_credentials_can_log_in_and_see_sample_plan(db, settings, client):
    seed_demo_account(db, settings)
    r = client.post("/api/v1/auth/login", json={
        "email": settings.ROMKA_DEMO_EMAIL, "password": settings.ROMKA_DEMO_PASSWORD})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["email"] == settings.ROMKA_DEMO_EMAIL
    assert body["session_token"] and body["csrf_token"]

    tasks = client.get("/api/v1/planner/tasks", headers=H(body["csrf_token"])).json()
    assert tasks["count"] == 3


# ── session transport (cookies blocked inside an iframe) ────────────────────

def test_login_returns_signed_token_usable_without_cookie(client):
    reg = client.post("/api/v1/auth/register", json={
        "email": "iframe@romka.local", "password": "RomkaDemo2026!"})
    assert reg.status_code == 200
    client.cookies.clear()  # simulate a browser refusing third-party cookies

    login = client.post("/api/v1/auth/login", json={
        "email": "iframe@romka.local", "password": "RomkaDemo2026!"})
    token, csrf = login.json()["session_token"], login.json()["csrf_token"]
    client.cookies.clear()

    headers = {"Authorization": f"Bearer {token}", "X-CSRF-Token": csrf}
    assert client.get("/api/v1/auth/me", headers=headers).json()["user"]["email"] == "iframe@romka.local"
    assert client.get("/api/v1/profile", headers=headers).status_code == 200
    wrote = client.post("/api/v1/memory", headers=headers,
                        json={"layer": "preference", "key": "k", "value": {"v": 1}})
    assert wrote.status_code == 200, wrote.text
    # CSRF is still enforced for header-based sessions.
    assert client.post("/api/v1/memory", headers={"Authorization": f"Bearer {token}"},
                       json={"layer": "preference", "key": "k2", "value": {"v": 1}}
                       ).status_code == 403
    # The explicit header works as well, for tools that cannot set Authorization.
    assert client.get("/api/v1/auth/me", headers={"X-ROMKA-Session": token}).status_code == 200
    # A tampered token is rejected.
    assert client.get("/api/v1/auth/me",
                      headers={"Authorization": f"Bearer {token}x"}).status_code == 401


def test_guest_login_returns_token_and_is_isolated(client):
    r = client.post("/api/v1/auth/guest", json={})
    assert r.status_code == 200
    token, csrf = r.json()["session_token"], r.json()["csrf_token"]
    client.cookies.clear()
    headers = {"Authorization": f"Bearer {token}", "X-CSRF-Token": csrf}
    assert client.get("/api/v1/planner/tasks", headers=headers).json()["count"] == 0


def test_cookie_flags_adapt_to_https_and_http(client):
    r = client.post("/api/v1/auth/register", json={
        "email": "flags@romka.local", "password": "RomkaDemo2026!"})
    set_cookie = r.headers["set-cookie"].lower()
    assert "samesite=lax" in set_cookie and "secure" not in set_cookie

    https = client.post("/api/v1/auth/login",
                        headers={"X-Forwarded-Proto": "https"},
                        json={"email": "flags@romka.local", "password": "RomkaDemo2026!"})
    cookie = https.headers["set-cookie"].lower()
    assert "samesite=none" in cookie and "secure" in cookie


def test_html_shell_is_public_but_data_requires_session(client):
    """The page shell holds no user data; the APIs still gate everything."""
    r = client.get("/")
    assert r.status_code == 200 and 'data-auth="client"' in r.text
    assert "flags@romka.local" not in r.text
    assert client.get("/api/v1/planner/tasks").status_code == 401


def test_authenticated_page_renders_server_session(client):
    client.post("/api/v1/auth/register", json={
        "email": "page@romka.local", "password": "RomkaDemo2026!"})
    r = client.get("/")
    assert r.status_code == 200
    assert 'data-auth="session"' in r.text
    assert 'name="csrf-token" content=""' not in r.text


# ── GapGPT / OpenAI-compatible adapter (mocked transport, not live) ─────────

def _chat_payload(content: str = "OK") -> dict:
    return {"id": "chatcmpl-1", "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 3}}


def test_gapgpt_preset_targets_verified_base_url():
    p = GapGPTProvider(api_key="k")
    assert p.base_url == GAPGPT_DEFAULT_BASE_URL == "https://api.gapgpt.app/v1"
    assert p.model == "gpt-4o-mini" and p.available
    assert GapGPTProvider(api_key="").available is False


def test_gapgpt_adapter_sends_openai_compatible_request_and_prices_it():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=_chat_payload("پاسخ آزمایشی"))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    p = GapGPTProvider(api_key="secret-key", model="gpt-4o-mini",
                       price_per_million=1.0, client=client)
    out = p.chat(ChatRequest(messages=[ChatMessage("user", "سلام")]))

    assert seen["url"] == "https://api.gapgpt.app/v1/chat/completions"
    assert seen["auth"] == "Bearer secret-key"
    assert seen["body"]["stream"] is False and seen["body"]["model"] == "gpt-4o-mini"
    assert out.text == "پاسخ آزمایشی" and out.provider == "gapgpt"
    assert out.prompt_tokens == 12 and out.completion_tokens == 3
    assert out.cost_usd == round(15 / 1_000_000 * 1.0, 6)
    assert "secret-key" not in json.dumps(out.raw)


def test_gapgpt_stream_parses_sse_and_ignores_noise():
    chunks = [b'data: {"choices":[{"delta":{"content":"\xd8\xb3"}}]}\n\n',
              b'data: {"choices":[{"delta":{}}]}\n\n',
              b'data: {"choices":[{"delta":{"content":"\xd9\x84\xd8\xa7\xd9\x85"}}]}\n\n',
              b"data: [DONE]\n\n"]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"".join(chunks),
                              headers={"content-type": "text/event-stream"})

    p = GapGPTProvider(api_key="secret-key",
                       client=httpx.Client(transport=httpx.MockTransport(handler)))
    text = "".join(p.stream(ChatRequest(messages=[ChatMessage("user", "سلام")])))
    assert text == "سلام"


def test_gapgpt_http_error_is_reported_without_leaking_key():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "invalid key secret-key"}})

    p = GapGPTProvider(api_key="secret-key",
                       client=httpx.Client(transport=httpx.MockTransport(handler)))
    from app.ai.base import ProviderError
    try:
        p.chat(ChatRequest(messages=[ChatMessage("user", "سلام")]))
    except ProviderError as exc:
        assert exc.retryable is False and exc.status_code == 401
        assert "secret-key" not in str(exc)
    else:  # pragma: no cover
        raise AssertionError("401 must raise ProviderError")


# ── provider status / explicit verification endpoint ───────────────────────

def _override_settings(client, **updates):
    s = Settings(ENVIRONMENT="testing", SECRET_KEY=TEST_SECRET, DATABASE_URL="sqlite://",
                 RATE_LIMIT_PER_MINUTE=10000, ROMKA_AUTO_DEMO=True, **updates)
    client.app.dependency_overrides[get_settings] = lambda: s
    return s


def test_status_reports_missing_key_instead_of_fake_external_provider(client, auth_client):
    c, csrf, _ = auth_client
    _override_settings(c, AI_PRIMARY_PROVIDER="gapgpt", AI_PRIMARY_API_KEY="")
    body = c.get("/api/v1/status", headers=H(csrf)).json()
    names = {p["name"]: p for p in body["providers"]}
    assert "gapgpt" in names and names["gapgpt"]["available"] is False
    assert "AI_PRIMARY_API_KEY" in names["gapgpt"]["reason"]
    assert names["gapgpt"]["verified_live"] is False
    assert body["provider_verification"]["verified_live"] is False
    assert all(not p["external"] or not p["available"] for p in body["providers"])


def test_verify_endpoint_is_honest_without_external_credentials(client, auth_client):
    c, csrf, _ = auth_client
    _override_settings(c, AI_PRIMARY_PROVIDER="gapgpt", AI_PRIMARY_API_KEY="")
    r = c.post("/api/v1/providers/verify", headers=H(csrf), json={})
    assert r.status_code == 200
    body = r.json()
    assert body["verified_live"] is False and "reason" in body


def test_provider_key_is_never_returned_by_status(client, auth_client):
    c, csrf, _ = auth_client
    _override_settings(c, AI_PRIMARY_PROVIDER="gapgpt", AI_PRIMARY_API_KEY="super-secret-key")
    body = c.get("/api/v1/status", headers=H(csrf))
    assert "super-secret-key" not in body.text
    providers = body.json()["providers"]
    gap = next(p for p in providers if p["name"] == "gapgpt")
    assert gap["available"] is True and gap["verified_live"] is False
    assert gap["base_url"] == "https://api.gapgpt.app/v1"
