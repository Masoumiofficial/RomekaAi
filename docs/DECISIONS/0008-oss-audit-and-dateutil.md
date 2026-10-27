# ADR-0008 — ممیزی متنباز و ادغام python-dateutil

- **تاریخ:** 2026-10-27 · **وضعیت:** Accepted

## زمینه
پس از ممیزی ۱۲ کاندیدا (شواهد GitHub API/PyPI)، نیاز فوری «تکرار وظایف» بود.
پیادهسازی RFC 5545 بهصورت دستی پرخطاست.

## تصمیم
ادغام `python-dateutil` (2.9.0.post0) بهعنوان تنها وابستگی جدید مسئلهمحور، صرفاً
پشت تابع `expand_recurrence()` در `app/planning/engine.py`. هسته کتابخانه تغییر نکرد.
مجوز از فایل LICENSE منبع تأیید شد (Apache-2.0 OR BSD-3-Clause) چون فراداده API
`NOASSERTION` بود.

## ردشدهها
LangGraph / crewAI / mem0 / AutoGen / MCP servers / anthropics/skills /
FullCalendar / Chart.js / APScheduler — دلایل در `docs/OSINT-AUDIT.md`.

## معیار اثر
تست دقیق خروجی RRULE؛ حذف ~۱۰۰+ خط پیادهسازی دستی پرخطا؛ تنها ۱ وابستگی ترانزیتیو
(six). هزینه نگهداری در برابر ارزش: قابلقبول.

## زمان بازبینی
وقتی نمای هفتگی/ماهانه و نمودارها بر اساس ۳۰+ نقطه داده واقعی نیاز شد،
FullCalendar/Chart.js دوباره ارزیابی شوند.
