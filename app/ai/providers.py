"""Adapters. Support claims here are about *implemented code*, not marketing.

- local: offline deterministic responder. No key, no network, fully testable.
- openai_compatible: real /chat/completions HTTP adapter. Untested against a live
  paid endpoint in this workspace because no credentials are present.
- gapgpt: the same adapter with verified defaults for GapGPT's OpenAI-compatible
  gateway (https://api.gapgpt.app/v1, docs/quickstart fetched 2026-10-28).
  Documentation is verified; LIVE connectivity is not (no API key in workspace).
- Native Claude / Gemini adapters are NOT implemented. See docs/AI-PROVIDERS.md.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Iterator

import httpx

from app.ai.base import BaseProvider, ChatRequest, ChatResult, ProviderError

log = logging.getLogger("romka.ai.providers")

# Rough public list prices (USD / 1M tokens) used ONLY for budget estimation.
# Operators should override these in Settings for their actual contract.
PRICE_TABLE: dict[str, float] = {
    "gpt-4o-mini": 0.60, "gpt-4o": 6.25, "gpt-4.1-mini": 0.80,
    "gemini-1.5-flash": 0.30, "gemini-2.5-flash": 0.60, "gemini-2.5-pro": 3.50,
    "claude-3-5-haiku": 1.60, "default": 1.0,
}
GAPGPT_DEFAULT_BASE_URL = "https://api.gapgpt.app/v1"
GAPGPT_DOCS_URL = "https://gapgpt.app/platform-v2/docs/quickstart"


def _approx_tokens(text: str) -> int:
    # 4 chars/token is a coarse ASCII heuristic; Persian is usually denser.
    # Deliberately conservative (over-estimate) so budgets err on the safe side.
    return max(1, (len(text) + 2) // 3)


class LocalDeterministicProvider(BaseProvider):
    """Grounded, rule-based responder.

    Honest limitation: this is NOT a large language model. It never invents
    user data; it only recombines the context handed to it by the core, and
    states uncertainty explicitly. It exists so the whole product works and is
    testable without any credential.
    """
    name = "local"
    is_external = False

    @property
    def available(self) -> bool:
        return True

    @property
    def model(self) -> str:
        return "romka-local-v1"

    def estimate_cost_usd(self, prompt_chars: int, completion_chars: int, model: str) -> float:
        return 0.0

    def chat(self, req: ChatRequest) -> ChatResult:
        started = time.perf_counter()
        system = next((m.content for m in req.messages if m.role == "system"), "")
        user = next((m.content for m in req.messages if m.role == "user"), "")
        meta = req.metadata or {}
        text = self._compose(system, user, meta)
        prompt_chars = sum(len(m.content) for m in req.messages)
        return ChatResult(
            text=text, provider=self.name, model=self.model,
            prompt_tokens=_approx_tokens("".join(m.content for m in req.messages)),
            completion_tokens=_approx_tokens(text), cost_usd=0.0,
            latency_ms=int((time.perf_counter() - started) * 1000),
            raw={"deterministic": True, "prompt_chars": prompt_chars},
        )

    def stream(self, req: ChatRequest) -> Iterator[str]:
        result = self.chat(req)
        for i in range(0, len(result.text), 24):
            yield result.text[i:i + 24]

    def _compose(self, system: str, user: str, meta: dict) -> str:
        facts: list[str] = meta.get("facts", []) or []
        agents: list[str] = meta.get("agent_names", []) or []
        plan: dict = meta.get("plan_summary") or {}
        warnings: list[str] = meta.get("context_warnings", []) or []
        mode = meta.get("intent", "general")

        head = "رومکا — پاسخ مبتنی بر دادههای ثبتشده شما"
        if agents:
            head += f" | متخصص فعال: { ' + '.join(agents) }"
        lines = [head, "", "آنچه از اطلاعات شما دارم:"]
        lines += [f"• {f}" for f in facts[:8]] if facts else ["• هنوز داده تأییدشدهای در این حوزه ثبت نشده است."]
        if plan:
            lines.append(f"• برنامه ثبتشده: {plan.get('scheduled_minutes', 0)} دقیقه کار، "
                         f"{plan.get('free_minutes', 0)} دقیقه زمان آزاد، "
                         f"{plan.get('utilization_pct', 0)}٪ اشغال.")

        low = user.lower()
        if "برنامه" in user or mode == "plan":
            lines += ["", "پیشنهاد اجرایی:",
                      "۱. تعهدات ثابت (جلسه، باشگاه، غذا) را ابتدا قفل کنید.",
                      "۲. کارهای وابسته به هم را پشتسرهم قرار دهید.",
                      "۳. بین هر دو کار، زمان بافر نگه دارید.",
                      "۴. با دکمه «ساخت برنامه» خروجی دقیق و بررسیشده بگیرید؛ متن من جایگزین محاسبه نیست."]
        elif any(w in low for w in ("خواب", "استراحت", "خسته", "انرژی")):
            lines += ["", "تحلیل:", "کمخوابی معمولاً هم کیفیت تمرین و هم تمرکز را کاهش میدهد. "
                      "این یک رابطه کلی است، نه تشخیص پزشکی.",
                      "پیشنهاد: در روز کمخوابی بار تمرین را ثابت نگه دارید (افزایش ندهید) و "
                      "یک کار غیرضروری را به فردا منتقل کنید. اگر خواب کمتر از ۶ ساعت "
                      "تکرار شد، ابتدا علت را بررسی کنید."]
        elif any(w in low for w in ("تمرین", "وزنه", "باشگاه", "بدن")):
            lines += ["", "پیشنهاد:", "افزایش بار فقط وقتی منطقی است که ستهای قبل، "
                      "بدون درد و با شدت قابلتحمل کامل شده باشند. در غیر این صورت همان بار را حفظ کنید.",
                      "نکته ایمنی: درد تیز یا طولانیمدت، علامت توقف و مشورت با متخصص انسانی است."]
        elif any(w in low for w in ("پروژه", "کسبوکار", "فروش", "بازار")):
            lines += ["", "چارچوب تصمیم:",
                      "۱. مسئله واقعی را بنویسید (چه چیزی الان اندازهگیری میشود؟)",
                      "۲. یک آزمون کوچک و قابل اندازهگیری تعریف کنید.",
                      "۳. معیار توقف داشته باشید؛ مشغولبودن معادل پیشرفت نیست."]
        else:
            lines += ["", "پیشنهاد:", "برای پاسخ دقیقتر، اطلاعات مرتبط (زمان، محدودیت، هدف) "
                      "را در پروفایل یا حافظه ثبت کنید تا بهجای حدس، بر اساس واقعیت برنامه بدهم."]

        if not facts:
            lines.append("")
            lines.append("⚠ عدم قطعیت: هیچ داده تأییدشدهای در حافظه پیدا نشد؛ "
                         "این پاسخ عمومی است و عدد یا وزنهای را تجویز نمیکند.")
        if warnings:
            lines.append("⚠ " + " / ".join(warnings[:3]))
        lines += ["", "یادآوری: این موتور پاسخ محلی و قطعی رومکاست، نه یک مدل زبانی خارجی. "
                  "برای پاسخهای زبانی گسترده، یک ارائهدهنده معتبر در تنظیمات پیکربندی کنید."]
        return "\n".join(lines)


class OpenAICompatibleProvider(BaseProvider):
    """Real HTTP adapter for OpenAI-compatible chat completion endpoints."""
    name = "openai_compatible"
    is_external = True

    def __init__(self, *, base_url: str, api_key: str, model: str,
                 timeout: float = 30.0, price_per_million: float | None = None,
                 client: httpx.Client | None = None) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.price = price_per_million if price_per_million is not None else PRICE_TABLE.get(model, PRICE_TABLE["default"])
        self._client = client

    @property
    def available(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)

    def estimate_cost_usd(self, prompt_chars: int, completion_chars: int, model: str) -> float:
        tokens = _approx_tokens("x" * (prompt_chars + completion_chars // 2))
        return round(tokens / 1_000_000 * self.price, 6)

    def _payload(self, req: ChatRequest, stream: bool = False) -> dict:
        payload = {
            "model": req.model or self.model,
            "messages": [m.as_dict() for m in req.messages],
            "temperature": req.temperature,
            "max_tokens": req.max_tokens,
            "stream": stream,
        }
        return payload

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def _post(self, payload: dict, *, stream: bool = False):
        url = f"{self.base_url}/chat/completions"
        try:
            if self._client is not None:
                if stream:
                    return self._client.stream("POST", url, json=payload, headers=self._headers(), timeout=self.timeout)
                return self._client.post(url, json=payload, headers=self._headers(), timeout=self.timeout)
            if stream:
                return httpx.stream("POST", url, json=payload, headers=self._headers(), timeout=self.timeout)
            return httpx.post(url, json=payload, headers=self._headers(), timeout=self.timeout)
        except httpx.TimeoutException as exc:
            raise ProviderError("زمان انتظار ارائهدهنده تمام شد.", retryable=True) from exc
        except httpx.RequestError as exc:
            raise ProviderError(f"خطای شبکه: {type(exc).__name__}", retryable=True) from exc

    @staticmethod
    def _check(resp: httpx.Response) -> dict:
        if resp.status_code >= 500 or resp.status_code == 429:
            raise ProviderError(f"ارائهدهنده پاسخ {resp.status_code} داد.", retryable=True, status_code=resp.status_code)
        if resp.status_code >= 400:
            raise ProviderError(f"درخواست رد شد ({resp.status_code}).", retryable=False, status_code=resp.status_code)
        try:
            return resp.json()
        except json.JSONDecodeError as exc:
            raise ProviderError("پاسخ غیرقابلتجزیه (JSON نامعتبر).", retryable=False) from exc

    def chat(self, req: ChatRequest) -> ChatResult:
        if not self.available:
            raise ProviderError("ارائهدهنده پیکربندی نشده است.", retryable=False)
        started = time.perf_counter()
        resp = self._post(self._payload(req))
        data = self._check(resp)
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("ساختار پاسخ ارائهدهنده نامعتبر است.", retryable=False) from exc
        usage = data.get("usage") or {}
        pt = int(usage.get("prompt_tokens") or _approx_tokens("".join(m.content for m in req.messages)))
        ct = int(usage.get("completion_tokens") or _approx_tokens(text))
        cost = round((pt + ct) / 1_000_000 * self.price, 6)
        return ChatResult(text=text, provider=self.name, model=req.model or self.model,
                          prompt_tokens=pt, completion_tokens=ct, cost_usd=cost,
                          latency_ms=int((time.perf_counter() - started) * 1000),
                          raw={"id": data.get("id", "")})

    def stream(self, req: ChatRequest) -> Iterator[str]:
        if not self.available:
            raise ProviderError("ارائهدهنده پیکربندی نشده است.", retryable=False)
        with self._post(self._payload(req, stream=True), stream=True) as resp:
            if resp.status_code >= 400:
                resp.read()
                self._check(resp)
            for line in resp.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                chunk = line[5:].strip()
                if chunk == "[DONE]":
                    break
                try:
                    delta = json.loads(chunk)["choices"][0]["delta"].get("content", "")
                except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                    continue
                if delta:
                    yield delta


class GapGPTProvider(OpenAICompatibleProvider):
    """GapGPT preset: verified OpenAI-compatible base URL and header shape.

    Evidence (quickstart page, fetched 2026-10-28): ``OpenAI(base_url=
    'https://api.gapgpt.app/v1', api_key=...)`` plus ``chat.completions.create``
    with model names such as ``gpt-4o`` / ``gemini-2.5-pro``. An alternative CDN
    base is ``https://api.gapapi.com/v1``. Model availability and IRR prices are
    account-specific: see /models, /pricing and /usage in the GapGPT panel.
    This class only changes defaults and reporting — the HTTP contract is the
    already-tested OpenAICompatibleProvider, not a new unverified client.
    """
    name = "gapgpt"
    is_external = True

    def __init__(self, *, base_url: str = "", api_key: str, model: str = "",
                 timeout: float = 30.0, price_per_million: float | None = None,
                 client: httpx.Client | None = None) -> None:
        super().__init__(base_url=base_url or GAPGPT_DEFAULT_BASE_URL, api_key=api_key,
                         model=model or "gpt-4o-mini", timeout=timeout,
                         price_per_million=price_per_million, client=client)
