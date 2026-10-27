# ADR-0002 — SQLAlchemy + Alembic؛ SQLite در توسعه، PostgreSQL در تولید

- **تاریخ:** 2026-10-27 · **وضعیت:** Accepted

## زمینه
نیاز به ۲۱ موجودیت (کاربران، حافظه، وظایف، برنامهها، مکالمات، امنیت، مهارتها، سلامت)
با قابلیت مهاجرت نسخهدار و مسیر بازگشت.

## تصمیم
SQLAlchemy 2.x (ORM-only) + Alembic. `DATABASE_URL` از env. SQLite محلی (WAL،
foreign_keys=ON) و PostgreSQL روی VPS.

## دلایل
- SQLite بدون نصب سرویس روی ویندوز کار میکند؛ PostgreSQL برای همزمانی و بکآپ production.
- ORM-only یعنی عدم ساخت رشته SQL از ورودی کاربر → کاهش SQL Injection.
- Alembic مسیر `upgrade`/`downgrade` قابلآزمون میدهد (hهر دو اجرا شدند).

## ریسکها
- تفاوت رفتار JSON/تایپ بین SQLite و PostgreSQL: قبل از استقرار باید تست یکپارچگی
  روی PostgreSQL اجرا شود (انجام نشده؛ ثبت شد).
- SQLite همزمانینویسی محدودی دارد؛ در production استفاده نشود.

## جایگزین ردشده
Migration دستی با اسکریپت SQL: بدون history و downgrade قابلاعتماد.
