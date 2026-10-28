"""Explicit, bounded conversation context and tenant isolation."""
import json

import pytest

from app.ai.base import ChatMessage, ChatRequest, ChatResult
from app.ai.providers import LocalDeterministicProvider
from app.db.models import Conversation, Message
from tests.conftest import H


@pytest.fixture
def captured(monkeypatch):
    from app.agents import orchestrator
    requests = []

    class CaptureRouter:
        def __init__(self, *args, **kwargs):
            pass

        def complete(self, req, ctx):
            requests.append(req)
            return ChatResult(text="پاسخ نمونه برای آزمایش", provider="mock", model="mock")

        def stream(self, req, ctx):
            requests.append(req)
            yield "پاسخ جریانی نمونه"

        def budget_state(self):
            return {}

        def configured_status(self):
            return []

    monkeypatch.setattr(orchestrator, "AIRouter", CaptureRouter)
    return requests


def send(c, csrf, text, conversation_id=None, **kw):
    response = c.post("/api/v1/chat/send", headers=H(csrf),
                      json={"text": text, "conversation_id": conversation_id, **kw})
    assert response.status_code == 200, response.text
    return response.json()


def payload(req):
    return [(m.role, m.content) for m in req.messages if m.role != "system"]


def test_history_requires_explicit_consent_and_is_chronological(auth_client, captured):
    c, csrf, _ = auth_client
    a = send(c, csrf, "اسم پروژه آفتاب است")
    b = send(c, csrf, "اسمش چیست؟", a["conversation_id"])
    assert b["history_turns_used"] == 0
    assert payload(captured[-1]) == [("user", "اسمش چیست؟")]
    result = send(c, csrf, "لطفاً تکرار کن", a["conversation_id"], include_history=True)
    assert result["history_turns_used"] == 2
    assert payload(captured[-1]) == [
        ("user", "اسم پروژه آفتاب است"), ("assistant", "پاسخ نمونه برای آزمایش"),
        ("user", "اسمش چیست؟"), ("assistant", "پاسخ نمونه برای آزمایش"),
        ("user", "لطفاً تکرار کن"),
    ]


def test_history_bounded_to_recent_pairs(auth_client, captured):
    c, csrf, _ = auth_client
    first = send(c, csrf, "پیام صفر")
    conv = first["conversation_id"]
    for n in range(1, 5):
        send(c, csrf, f"پیام {n}", conv)
    r = send(c, csrf, "اکنون", conv, include_history=True)
    assert r["history_turns_used"] == 3
    assert [x[1] for x in payload(captured[-1]) if x[0] == "user"] == ["پیام 2", "پیام 3", "پیام 4", "اکنون"]


def test_history_over_character_cap_is_not_sent(auth_client, captured):
    c, csrf, _ = auth_client
    first = send(c, csrf, "ا" * 6000)
    second = send(c, csrf, "ادامه", first["conversation_id"], include_history=True)
    assert second["history_turns_used"] == 0
    assert payload(captured[-1]) == [("user", "ادامه")]


def test_failed_turn_not_reused(auth_client, db, captured):
    c, csrf, _ = auth_client
    first = send(c, csrf, "یک درخواست")
    msg = db.get(Message, first["message_id"])
    msg.warnings = ["provider_error: provider_unavailable"]
    db.flush()
    second = send(c, csrf, "دوباره", first["conversation_id"], include_history=True)
    assert second["history_turns_used"] == 0
    assert payload(captured[-1]) == [("user", "دوباره")]


def test_stream_uses_same_context_and_invalid_id_is_404(auth_client, captured):
    c, csrf, _ = auth_client
    first = send(c, csrf, "پیام پیشین")
    r = c.post("/api/v1/chat/stream", headers=H(csrf), json={"text": "ادامه", "include_history": True,
               "conversation_id": first["conversation_id"]})
    assert r.status_code == 200
    assert payload(captured[-1]) == [("user", "پیام پیشین"), ("assistant", "پاسخ نمونه برای آزمایش"), ("user", "ادامه")]
    events = [json.loads(line[6:]) for line in r.text.splitlines() if line.startswith("data: ")]
    assert events[-1]["meta"]["history_turns_used"] == 1
    for path in ("/api/v1/chat/send", "/api/v1/chat/stream"):
        bad = c.post(path, headers=H(csrf), json={"text": "سلام", "conversation_id": 999999})
        assert bad.status_code == 404


def test_other_users_conversation_is_rejected_without_writing(auth_client, db, captured):
    c, csrf, user_id = auth_client
    from app.db.models import User
    other = User(email="other@example.com", display_name="other", password_hash="not-a-real-hash")
    db.add(other)
    db.flush()
    foreign = Conversation(user_id=other.id, title="محرمانه")
    db.add(foreign)
    db.flush()
    db.add_all([Message(conversation_id=foreign.id, role="user", content="PRIVATE"),
                Message(conversation_id=foreign.id, role="assistant", content="PRIVATE RESPONSE")])
    db.flush()
    before = db.query(Message).count()
    for path in ("/api/v1/chat/send", "/api/v1/chat/stream"):
        resp = c.post(path, headers=H(csrf), json={"text": "آزمون", "include_history": True,
                      "conversation_id": foreign.id})
        assert resp.status_code == 404
    assert db.query(Message).count() == before
    assert captured == []


def test_local_provider_uses_latest_question(monkeypatch):
    provider = LocalDeterministicProvider()
    monkeypatch.setattr(provider, "_compose", lambda system, user, meta: user)
    req = ChatRequest(messages=[ChatMessage("user", "موضوع اول"),
                                ChatMessage("assistant", "پاسخ قبلی"),
                                ChatMessage("user", "موضوع فعلی")])
    answer = provider.chat(req)
    assert "موضوع فعلی" in answer.text
    assert "موضوع اول" not in answer.text


def test_context_never_crosses_between_own_conversations(auth_client, captured):
    c, csrf, _ = auth_client
    first = send(c, csrf, "گفتگوی اول")
    second = send(c, csrf, "گفتگوی دوم")
    r = send(c, csrf, "ادامه دوم", second["conversation_id"], include_history=True)
    assert first["conversation_id"] != second["conversation_id"]
    assert r["history_turns_used"] == 1
    assert "گفتگوی اول" not in [m.content for m in captured[-1].messages]


def test_router_counts_history_in_estimate_and_blocks_sensitive_marker(db, settings):
    from app.ai.base import BaseProvider
    from app.ai.router import AIRouter, SENSITIVE_MARKER
    from app.core.errors import ProviderUnavailable

    class MeasuringProvider(BaseProvider):
        name = "mock"
        model = "mock"
        is_external = True
        calls = 0
        chars = 0

        @property
        def available(self):
            return True

        def estimate_cost_usd(self, prompt_chars, completion_chars, model):
            self.chars = prompt_chars
            return 0.0

        def chat(self, req):
            self.calls += 1
            return ChatResult(text="ok", provider=self.name, model=self.model)

    provider = MeasuringProvider()
    router = AIRouter(db, user_id=1, settings=settings, providers={"primary": provider})
    req = ChatRequest(messages=[ChatMessage("system", "sys"), ChatMessage("user", "old"),
                                ChatMessage("assistant", "previous"), ChatMessage("user", "now")])
    router.complete(req)
    assert provider.chars == len("sysoldpreviousnow")
    assert provider.calls == 1
    req.messages[1].content = SENSITIVE_MARKER + "private"
    with pytest.raises(ProviderUnavailable):
        router.complete(req)
    assert provider.calls == 1
