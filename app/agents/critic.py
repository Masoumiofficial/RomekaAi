"""Independent quality critic. Deterministic rules, no extra model call.

It does not pretend to be an LLM judge; it catches measurable failure modes:
false certainty, unsafe advice, contradictions, missing uncertainty and
ignored prompt-injection attempts.
"""
from __future__ import annotations

from dataclasses import dataclass

_UNSAFE_CERTAINTY = ("قطعاً درمان", "تضمین میکنم", "۱۰۰٪", "بدون شک", "حتماً موفق میشوی")
_UNSAFE_MEDICAL = ("قرص", "داروی", "دوز", "تشخیص بیماری", "درمان قطعی")
_FINANCIAL = ("حتماً سود", "بدون ریسک", "تضمین بازده")
_INJECTION = ("ignore previous", "نادیده بگیر دستور", "system prompt", "افشا کن", "دستور بالادستی")
_INCREASE = ("افزایش وزنه", "افزایش بار", "سنگینتر کن")
_DECREASE = ("کاهش وزنه", "کاهش بار", "استراحت کن", "توقف تمرین")


@dataclass
class CriticVerdict:
    score: float
    verdict: str            # accepted | revised | rejected
    warnings: list[str]
    checks: dict


def evaluate(answer: str, *, facts_count: int = 0, agents: list[dict] | None = None,
             user_text: str = "") -> CriticVerdict:
    warnings: list[str] = []
    checks: dict = {"length_ok": False, "uncertainty_stated": False,
                    "no_false_certainty": True, "no_contradiction": True,
                    "injection_resisted": True, "grounded": facts_count > 0}
    score = 1.0

    checks["length_ok"] = 40 <= len(answer) <= 6000
    if not checks["length_ok"]:
        warnings.append("طول پاسخ نامناسب است.")
        score -= 0.15
    checks["uncertainty_stated"] = any(w in answer for w in ("عدم قطعیت", "تخمینی", "ممکن است", "نمیتوان", "داده کافی"))
    if facts_count == 0 and not checks["uncertainty_stated"]:
        warnings.append("بدون داده ثبتشده، پاسخ فاقد اعلام عدم قطعیت است.")
        score -= 0.25
    for phrase in _UNSAFE_CERTAINTY:
        if phrase in answer:
            checks["no_false_certainty"] = False
            warnings.append("ادعای قطعیت بدون پشتوانه حذف شود.")
            score -= 0.2
            break
    for phrase in _UNSAFE_MEDICAL + _FINANCIAL:
        if phrase in answer and "متخصص" not in answer and "ارجاع" not in answer:
            warnings.append("عبارت نیازمند ارجاع به متخصص انسانی شناسایی شد.")
            score -= 0.1
            break
    has_inc = any(w in answer for w in _INCREASE)
    has_dec = any(w in answer for w in _DECREASE)
    if has_inc and has_dec and "اگر" not in answer and "در غیر" not in answer:
        checks["no_contradiction"] = False
        warnings.append("تناقض میان افزایش و کاهش بار بدون شرطبندی دیده شد.")
        score -= 0.2
    lowered = user_text.lower()
    if any(p in lowered for p in _INJECTION):
        if any(p in answer for p in ("سیستم", "راز", "رمز", "توکن")) and "نمیتوان" not in answer:
            checks["injection_resisted"] = False
            warnings.append("ورودی مشکوک به تزریق فرمان بود؛ پاسخ باید محدود بماند.")
            score -= 0.3
    if facts_count == 0:
        warnings.append("هیچ داده تأییدشدهای مبنای پاسخ نبوده است.")
        score -= 0.1

    score = max(0.0, min(1.0, round(score, 2)))
    verdict = "accepted" if score >= 0.75 else "revised" if score >= 0.45 else "rejected"
    if verdict == "revised":
        answer_note = "\n\n(نقد رومکا: پاسخ بالا با احتیاط بیشتر بخوانید؛ موارد بالا بررسی نشدهاند.)"
        warnings.append(answer_note.strip())
    return CriticVerdict(score=score, verdict=verdict, warnings=warnings, checks=checks)
