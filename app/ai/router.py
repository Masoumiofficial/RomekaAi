"""Model routing, cost control, bounded retries and privacy guard.

Non-negotiable rules:
- No request can make an unbounded number of model calls.
- Sensitive memory never reaches an external provider by accident.
- Every attempt (success or failure) is recorded with its estimated cost.
- Fallback is opt-in and only between providers with the same privacy class.
"""
from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterator

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.ai.base import BaseProvider, ChatRequest, ChatResult, ProviderError
from app.ai.providers import LocalDeterministicProvider, OpenAICompatibleProvider
from app.config import Settings, get_settings
from app.core.errors import BudgetExceeded, ProviderUnavailable
from app.db.models import AIUsage

log = logging.getLogger("romka.ai.router")

SENSITIVE_MARKER = "[ROMKA:SENSITIVE]"


@dataclass
class RouteContext:
    tier: str = "standard"          # cheap | standard | premium
    allow_sensitive: bool = False
    request_id: str = ""


class AIRouter:
    def __init__(self, db: Session, *, user_id: int | None, settings: Settings | None = None,
                 providers: dict[str, BaseProvider] | None = None) -> None:
        self.db = db
        self.user_id = user_id
        self.settings = settings or get_settings()
        self.providers = providers or self._default_providers()
        self.calls = 0
        self._recent_hashes: list[str] = []
        self.max_steps = max(1, self.settings.AI_MAX_AGENT_STEPS)

    def _default_providers(self) -> dict[str, BaseProvider]:
        out: dict[str, BaseProvider] = {"local": LocalDeterministicProvider()}
        s = self.settings
        if s.AI_PRIMARY_PROVIDER == "openai_compatible" and s.AI_PRIMARY_BASE_URL and s.AI_PRIMARY_API_KEY:
            out["primary"] = OpenAICompatibleProvider(
                base_url=s.AI_PRIMARY_BASE_URL, api_key=s.AI_PRIMARY_API_KEY,
                model=s.AI_PRIMARY_MODEL, timeout=s.AI_TIMEOUT_SECONDS)
        if s.AI_FALLBACK_PROVIDER == "openai_compatible" and s.AI_FALLBACK_BASE_URL and s.AI_FALLBACK_API_KEY:
            out["fallback"] = OpenAICompatibleProvider(
                base_url=s.AI_FALLBACK_BASE_URL, api_key=s.AI_FALLBACK_API_KEY,
                model=s.AI_FALLBACK_MODEL, timeout=s.AI_TIMEOUT_SECONDS)
        return out

    # ── providers ──
    def primary(self) -> BaseProvider:
        p = self.providers.get("primary") or self.providers.get("local")
        if p is None or not p.available:
            raise ProviderUnavailable("هیچ ارائهدهنده فعالی پیکربندی نشده است.")
        return p

    def configured_status(self) -> list[dict]:
        return [{"name": k, "available": v.available, "external": v.is_external,
                 "model": getattr(v, "model", "")} for k, v in self.providers.items()]

    # ── budget ──
    def _spent(self, since: datetime) -> float:
        q = self.db.query(func.coalesce(func.sum(AIUsage.cost_usd), 0.0)).filter(AIUsage.created_at >= since)
        if self.user_id is not None:
            q = q.filter(AIUsage.user_id == self.user_id)
        return float(q.scalar() or 0.0)

    def budget_state(self) -> dict:
        now = datetime.now(timezone.utc)
        day = self._spent(now - timedelta(days=1))
        month = self._spent(now - timedelta(days=30))
        return {
            "daily_spent_usd": round(day, 6), "monthly_spent_usd": round(month, 6),
            "daily_budget_usd": self.settings.AI_DAILY_BUDGET_USD,
            "monthly_budget_usd": self.settings.AI_MONTHLY_BUDGET_USD,
            "calls_this_request": self.calls,
            "max_calls_per_request": self.settings.AI_MAX_CALLS_PER_REQUEST,
            "max_agent_steps": self.max_steps,
        }

    def _check_budget(self, estimate: float) -> None:
        state = self.budget_state()
        if self.calls >= self.settings.AI_MAX_CALLS_PER_REQUEST:
            raise BudgetExceeded("سقف تعداد فراخوانی مدل در یک درخواست رسید.", details=state)
        if state["daily_spent_usd"] + estimate > self.settings.AI_DAILY_BUDGET_USD:
            raise BudgetExceeded("سقف هزینه روزانه مدل رسید.", details=state)
        if state["monthly_spent_usd"] + estimate > self.settings.AI_MONTHLY_BUDGET_USD:
            raise BudgetExceeded("سقف هزینه ماهانه مدل رسید.", details=state)

    # ── loop / prompt-injection style repetition guard ──
    def _fingerprint(self, req: ChatRequest) -> str:
        blob = "|".join(m.content for m in req.messages)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def _check_loop(self, fingerprint: str) -> None:
        self._recent_hashes.append(fingerprint)
        self._recent_hashes = self._recent_hashes[-self.settings.AI_MAX_CALLS_PER_REQUEST:]
        if len(self._recent_hashes) >= 3 and len(set(self._recent_hashes)) == 1:
            raise BudgetExceeded("حلقه تکراری فراخوانی مدل شناسایی و متوقف شد.")

    # ── privacy ──
    def _privacy_guard(self, provider: BaseProvider, req: ChatRequest, ctx: RouteContext) -> None:
        if not provider.is_external:
            return
        if SENSITIVE_MARKER in "".join(m.content for m in req.messages) and not (
            ctx.allow_sensitive and self.settings.AI_ALLOW_SENSITIVE_TO_EXTERNAL
        ):
            raise ProviderUnavailable(
                "ارسال داده حساس به ارائهدهنده خارجی مجاز نیست. ابتدا کاهش/حذف اطلاعات انجام شود."
            )

    # ── logging ──
    def _log(self, provider: BaseProvider, model: str, status: str, *, cost: float = 0.0,
             pt: int = 0, ct: int = 0, latency: int = 0, error: str = "") -> None:
        self.db.add(AIUsage(user_id=self.user_id, provider=provider.name, model=model,
                            prompt_tokens=pt, completion_tokens=ct, cost_usd=cost,
                            status=status, latency_ms=latency, error=error[:500]))
        self.db.flush()

    # ── main ──
    def complete(self, req: ChatRequest, ctx: RouteContext | None = None) -> ChatResult:
        ctx = ctx or RouteContext()
        primary = self.primary()
        fingerprint = self._fingerprint(req)
        estimate = primary.estimate_cost_usd(
            sum(len(m.content) for m in req.messages), req.max_tokens * 3, req.model
        )
        self._check_budget(estimate)
        self._check_loop(fingerprint)
        self._privacy_guard(primary, req, ctx)

        chain: list[tuple[str, BaseProvider]] = [("primary", primary)]
        if primary.is_external:
            if self.settings.AI_ALLOW_FALLBACK and "fallback" in self.providers:
                fb = self.providers["fallback"]
                if fb.available and fb.is_external == primary.is_external:
                    chain.append(("fallback", fb))
            if self.settings.AI_ALLOW_FALLBACK:
                chain.append(("local", self.providers["local"]))

        last_error: ProviderError | None = None
        for label, provider in chain:
            if provider is None or not provider.available:
                continue
            attempts = self.settings.AI_MAX_RETRIES + 1 if label == "primary" else 1
            for attempt in range(attempts):
                started = time.perf_counter()
                self.calls += 1
                try:
                    self._privacy_guard(provider, req, ctx)
                    result = provider.chat(req)
                    self._log(provider, result.model, "ok", cost=result.cost_usd,
                              pt=result.prompt_tokens, ct=result.completion_tokens,
                              latency=result.latency_ms)
                    if label != "primary":
                        result.text += f"\n\n(پاسخ از مسیر جایگزین {label} تولید شد.)"
                    return result
                except ProviderError as exc:
                    last_error = exc
                    self._log(provider, getattr(provider, "model", ""), "error", latency=int(
                        (time.perf_counter() - started) * 1000), error=str(exc))
                    log.warning("provider %s attempt %s failed: %s", label, attempt + 1, exc)
                    if not exc.retryable:
                        break
                    if attempt + 1 < attempts:
                        time.sleep(min(0.05 * (2 ** attempt), 0.4))
                if self.calls >= self.settings.AI_MAX_CALLS_PER_REQUEST:
                    break
        raise ProviderUnavailable(
            f"همه ارائهدهندگان در دسترس نبودند. آخرین خطا: {last_error}",
            details={"attempts": self.calls},
        )

    def stream(self, req: ChatRequest, ctx: RouteContext | None = None) -> Iterator[str]:
        ctx = ctx or RouteContext()
        provider = self.primary()
        estimate = provider.estimate_cost_usd(sum(len(m.content) for m in req.messages),
                                              req.max_tokens * 3, req.model)
        self._check_budget(estimate)
        self._privacy_guard(provider, req, ctx)
        self.calls += 1
        chunks: list[str] = []
        started = time.perf_counter()
        try:
            for piece in provider.stream(req):
                chunks.append(piece)
                yield piece
            text = "".join(chunks)
            self._log(provider, getattr(provider, "model", ""), "ok",
                      cost=provider.estimate_cost_usd(sum(len(m.content) for m in req.messages),
                                                      len(text), req.model),
                      pt=0, ct=0, latency=int((time.perf_counter() - started) * 1000))
        except ProviderError as exc:
            self._log(provider, getattr(provider, "model", ""), "error",
                      latency=int((time.perf_counter() - started) * 1000), error=str(exc))
            yield f"\n[خطای ارائهدهنده: {exc}]"
