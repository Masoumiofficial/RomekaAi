"""Explicit, budget-capped live verification of an external AI provider.

Nothing here runs automatically. A signed-in owner must press the button (or
call this endpoint) once; exactly one tiny request is sent, and the outcome is
recorded in AIUsage. The API key is never returned, logged or persisted here.
"""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.ai.base import ChatMessage, ChatRequest, ProviderError
from app.ai.router import AIRouter
from app.api.deps import AuthContext, get_auth_context, require_role
from app.ai.runtime_state import mark_verified, reset_verification, verification_state
from app.config import Settings, get_settings
from app.db.session import get_db

router = APIRouter(prefix="/providers", tags=["providers"])

PROBE_MESSAGES = [
    ChatMessage("system", "You are a connectivity probe. Reply with exactly: OK"),
    ChatMessage("user", "ping"),
]


@router.get("")
def list_providers(ctx: AuthContext = Depends(get_auth_context),
                   db: Session = Depends(get_db),
                   settings: Settings = Depends(get_settings)) -> dict:
    r = AIRouter(db, user_id=ctx.user.id, settings=settings)
    return {"ok": True, "items": r.configured_status(),
            "verification": verification_state()}


@router.post("/verify")
def verify(ctx: AuthContext = Depends(require_role("owner")),
           db: Session = Depends(get_db),
           settings: Settings = Depends(get_settings)) -> dict:
    r = AIRouter(db, user_id=ctx.user.id, settings=settings)
    provider = r.providers.get("primary")
    if provider is None or not provider.is_external:
        return {"ok": True, "verified_live": False,
                "reason": "هیچ ارائهدهنده خارجی پیکربندی نشده است؛ موتور محلی آفلاین فعال است."}
    req = ChatRequest(messages=PROBE_MESSAGES, model=provider.model, max_tokens=16)
    estimate = provider.estimate_cost_usd(
        sum(len(m.content) for m in req.messages), 48, req.model)
    r._check_budget(estimate)  # raises BudgetExceeded before any network call
    started = time.perf_counter()
    try:
        result = provider.chat(req)
    except ProviderError as exc:
        latency = int((time.perf_counter() - started) * 1000)
        r._log(provider, provider.model, "error", latency=latency, error=str(exc))
        reset_verification()
        return {"ok": False, "verified_live": False, "provider": provider.name,
                "model": provider.model, "error": str(exc)}
    r._log(provider, result.model, "ok", cost=result.cost_usd,
           pt=result.prompt_tokens, ct=result.completion_tokens,
           latency=result.latency_ms)
    mark_verified(provider.name, result.model, result.latency_ms)
    return {"ok": True, "verified_live": True, "provider": provider.name,
            "model": result.model, "latency_ms": result.latency_ms,
            "cost_usd": result.cost_usd, "sample": result.text[:120],
            "note": "یک فراخوانی واقعی انجام شد؛ نتیجه فقط تا راهاندازی مجدد معتبر است."}
