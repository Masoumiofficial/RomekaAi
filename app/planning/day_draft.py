"""Conservative, local draft extraction; never writes or invents missing times.

This is a heuristic, not a language model. Every proposed item remains editable
and unselected until the user explicitly reviews and approves it.
"""
from __future__ import annotations

import re

from app.core.errors import ValidationFailed

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_NUMBERS = {"یک": 1, "یه": 1, "دو": 2, "سه": 3, "چهار": 4, "پنج": 5,
            "شش": 6, "هفت": 7, "هشت": 8, "نه": 9, "ده": 10}
_EVENT_WORDS = ("جلسه", "قرار", "کلاس", "ویزیت", "وبینار", "مصاحبه")
_OTHER_DAY = re.compile(r"فردا|دیروز|پس\s*فردا|شنبه|یکشنبه|دوشنبه|سه\s*شنبه|چهارشنبه|پنج\s*شنبه|جمعه|هفته|ماه|\b1[34]\d{2}\b|\d{1,4}[/\-]\d{1,2}(?:[/\-]\d{1,4})?")
_NUM_WORD = r"(?:\d{1,3}|یک|یه|دو|سه|چهار|پنج|شش|هفت|هشت|نه|ده)"
_SPLIT = re.compile(r"[،,؛;\n]+|\s+و\s+(?!نیم(?:\s|$)|" + _NUM_WORD + r"\s*(?:ساعت|دقیقه))")
_DURATION = re.compile(r"(?<!\w)(" + _NUM_WORD + r")\s*(دقیقه|ساعت)(?:\s+و\s+نیم)?")
_TIME = re.compile(r"ساعت\s*(\d{1,2})(?:\s*[:：]\s*(\d{1,2}))?")


def _number(s: str) -> int:
    return int(s) if s.isdigit() else _NUMBERS[s]


def _duration(text: str) -> int | None:
    if re.search(r"نیم\s*ساعت", text):
        return 30
    m = _DURATION.search(text)
    if not m:
        return None
    result = _number(m.group(1)) * (60 if m.group(2) == "ساعت" else 1)
    if m.group(2) == "ساعت" and re.search(r"و\s+نیم", m.group(0)):
        result += 30
    return result if 5 <= result <= 720 else None


def _start(text: str) -> int | None:
    m = _TIME.search(text)
    if not m:
        return None
    hour, minute = int(m.group(1)), int(m.group(2) or 0)
    # «نه و نیم» means 09:30, not a 30-minute duration.
    if m.group(2) is None and re.match(r"\s+و\s+نیم(?:\s|$)", text[m.end():]):
        minute = 30
    if hour > 23 or minute > 59:
        return None
    # 1–12 without a period is ambiguous; do not infer AM/PM from context.
    if 1 <= hour <= 11:
        if re.search(r"صبح", text):
            pass
        elif re.search(r"عصر|شب|بعد\s*از\s*ظهر|بعدازظهر", text):
            hour += 12
        else:
            return None
    elif hour == 12 and not re.search(r"ظهر", text):
        return None
    return hour * 60 + minute


def propose_day(text: str) -> dict:
    original = text.strip()
    if not original:
        raise ValidationFailed("متن روز خالی است.")
    if len(original) > 4000:
        raise ValidationFailed("متن روز بیش از ۴۰۰۰ نویسه است.")
    # Digits are normalized for parsing only; the original text remains visible.
    chunks = [c.strip() for c in _SPLIT.split(original) if c.strip()]
    if not 1 <= len(chunks) <= 20:
        raise ValidationFailed("حداکثر ۲۰ بخش در هر بار قابل بررسی است.")
    if any(len(c) > 400 for c in chunks):
        raise ValidationFailed("هر بخش باید حداکثر ۴۰۰ نویسه باشد؛ آن را جدا کنید.")
    items = []
    for chunk in chunks:
        normalized = chunk.translate(_DIGITS).replace("ي", "ی").replace("ك", "ک").replace("‌", " ")
        kind = "event" if any(word in normalized for word in _EVENT_WORDS) else "task"
        duration = _duration(normalized)
        start = _start(normalized) if kind == "event" else None
        end = start + duration if start is not None and duration is not None and start + duration <= 1440 else None
        items.append({"title": chunk, "kind": kind, "duration_min": duration,
                      "start_min": start, "end_min": end})
    normalized_text = original.translate(_DIGITS).replace("‌", " ")
    return {"items": items, "date_uncertain": bool(_OTHER_DAY.search(normalized_text))}
