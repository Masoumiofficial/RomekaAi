from __future__ import annotations

import pytest

from app.ai.base import BaseProvider, ChatMessage, ChatRequest, ChatResult, ProviderError
from app.ai.router import AIRouter, SENSITIVE_MARKER
from app.core.errors import BudgetExceeded, ProviderUnavailable
from app.db.models import AIUsage


class FakeProvider(BaseProvider):
    name = "fake_external"
    is_external = True
    model = "fake-1"

    def __init__(self, *, fail=False, cost=0.01):
        self.fail, self.cost = fail, cost

    @property
    def available(self): return True

    def estimate_cost_usd(self, p, c, m): return self.cost

    def chat(self, req):
        if self.fail:
            raise ProviderError("سرویس قطع است.", retryable=True)
        return ChatResult("پاسخ آزمایشی", self.name, self.model,
                          prompt_tokens=10, completion_tokens=5, cost_usd=self.cost)

    def stream(self, req):
        yield "پاسخ "
        yield "جریانی"


def req(text="سلام"):
    return ChatRequest(messages=[ChatMessage("user", text)])


def test_local_provider_is_offline_and_logged(db, settings):
    r = AIRouter(db, user_id=1, settings=settings)
    out = r.complete(req())
    assert out.provider == "local" and out.cost_usd == 0.0
    assert "رومکا" in out.text
    assert db.query(AIUsage).count() == 1
    assert db.query(AIUsage).first().status == "ok"


def test_budget_cap_blocks_expensive_calls(db, settings):
    s = settings.model_copy(update={"AI_DAILY_BUDGET_USD": 0.0, "AI_PRIMARY_PROVIDER": "openai_compatible"})
    r = AIRouter(db, user_id=1, settings=s,
                 providers={"primary": FakeProvider(cost=0.5), "local": __import__("app.ai.providers", fromlist=["LocalDeterministicProvider"]).LocalDeterministicProvider()})
    with pytest.raises(BudgetExceeded):
        r.complete(req())
    assert r.calls == 0


def test_loop_detection_stops_repeated_calls(db, settings):
    s = settings.model_copy(update={"AI_MAX_CALLS_PER_REQUEST": 10})
    r = AIRouter(db, user_id=1, settings=s)
    r.complete(req("تکرار")); r.complete(req("تکرار"))
    with pytest.raises(BudgetExceeded):
        r.complete(req("تکرار"))


def test_sensitive_data_never_reaches_external_provider(db, settings):
    s = settings.model_copy(update={"AI_PRIMARY_PROVIDER": "openai_compatible"})
    r = AIRouter(db, user_id=1, settings=s,
                 providers={"primary": FakeProvider(), "local": __import__("app.ai.providers", fromlist=["LocalDeterministicProvider"]).LocalDeterministicProvider()})
    with pytest.raises(ProviderUnavailable):
        r.complete(ChatRequest(messages=[ChatMessage("user", f"{SENSITIVE_MARKER} اطلاعات پزشکی")]))


def test_bounded_retry_and_opt_in_fallback(db, settings):
    from app.ai.providers import LocalDeterministicProvider
    s = settings.model_copy(update={"AI_ALLOW_FALLBACK": True, "AI_MAX_RETRIES": 1,
                                    "AI_MAX_CALLS_PER_REQUEST": 6})
    r = AIRouter(db, user_id=1, settings=s,
                 providers={"primary": FakeProvider(fail=True), "local": LocalDeterministicProvider()})
    out = r.complete(req())
    assert "جایگزین" in out.text and out.provider == "local"
    statuses = [u.status for u in db.query(AIUsage).order_by(AIUsage.id).all()]
    assert statuses.count("error") >= 2  # bounded retries, not an infinite loop
    assert statuses[-1] == "ok"


def test_no_fallback_when_not_opted_in(db, settings):
    from app.ai.providers import LocalDeterministicProvider
    s = settings.model_copy(update={"AI_ALLOW_FALLBACK": False, "AI_MAX_RETRIES": 0})
    r = AIRouter(db, user_id=1, settings=s,
                 providers={"primary": FakeProvider(fail=True), "local": LocalDeterministicProvider()})
    with pytest.raises(ProviderUnavailable):
        r.complete(req())


def test_streaming_yields_chunks_and_logs(db, settings):
    r = AIRouter(db, user_id=1, settings=settings)
    chunks = list(r.stream(req()))
    assert "".join(chunks)
    assert db.query(AIUsage).count() == 1
