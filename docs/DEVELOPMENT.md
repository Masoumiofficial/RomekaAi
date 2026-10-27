# DEVELOPMENT — محیط توسعه قابل بازسازی

## الزامات

- Python 3.11+ (تست شده روی 3.11.2)
- ویندوز 10/11 یا لینوکس؛ بدون نیاز به Docker در فاز توسعه
- SQLite (همراه Python) برای توسعه؛ PostgreSQL اختیاری

## راهاندازی ویندوز (PowerShell)

```powershell
git clone https://github.com/Masoumiofficial/RomekaAi.git
cd RomekaAi
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
copy .env.example .env
# ویرایش .env و قرار دادن SECRET_KEY (تولید: python -c "import secrets;print(secrets.token_urlsafe(48))")
alembic upgrade head
.\scripts\run_dev.ps1
```

اگر `Activate.ps1` توسط Execution Policy مسدود شد:
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

## راهاندازی لینوکس

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
alembic upgrade head
./scripts/run_dev.sh
```

> در محیط توسعه، lifespan برنامه خودکار `create_all()` را اجرا میکند و رجیستری
> مهارتها را seed میکند؛ ولی مسیر رسمی همچنان `alembic upgrade head` است.

## تستها

```bash
pytest -q                                    # ۵۹ تست
pytest -q --cov=app --cov-report=term-missing
pytest tests/test_planning.py -q             # فقط موتور برنامهسازی
pytest -q -k "scenario"                      # سناریوهای پذیرش
```

تستها از SQLite درونحافظهای با `StaticPool` و `dependency_overrides` استفاده میکنند؛
هیچ سرویس خارجی و هیچ کلید API لازم نیست. ارائهدهندهها با mock تست میشوند.

## مهاجرتها

```bash
alembic revision --autogenerate -m "add X"   # سپس فایل تولیدشده را بازبینی کنید
alembic upgrade head
alembic downgrade -1                          # مسیر بازگشت
```

قبل از هر تغییر مدل، از `romka.db` نسخه پشتیبان بگیرید:
`cp romka.db backups/romka-$(date +%F).db`.

## افزودن یک متخصص

1. یک ورودی به `app/agents/definitions.json` اضافه کنید (شناسه، نام، مأموریت،
   محدودیتها، کلماتکلیدی، لایههای مجاز، ابزارهای مجاز، نسخه، `active`).
2. ابزارها **فقط** اگر قبلاً در `app/core/action_engine.py` ثبت شده باشند پذیرفته میشوند؛
   موارد ناشناخته هنگام بارگذاری حذف و لاگ میشوند (`/api/v1/agents` → `load_warnings`).
3. تست اضافه کنید: `assert registry.select("متن مرتبط")`.

## افزودن یک مهارت/کتابخانه

به [OSINT-AUDIT.md](OSINT-AUDIT.md) مراجعه کنید. خلاصه: شواهد (stars/license/push)،
`evaluate_candidate`، `sandbox_check`، تست ایزوله، سپس `skill_registry.activate`.
**هرگز کد خارجی را بدون بررسی اجرا نکنید.**

## ساختار پوشهها

```
app/
  api/         مسیرهای FastAPI
  core/        امنیت، خطاها، ActionEngine
  db/          مدلها و نشستها
  memory/      حافظه لایهای
  planning/    موتور زمانبندی + سرویس DB
  ai/          رابط ارائهدهنده، آداپتورها، روتِر
  agents/      رجیستری، تعاریف، orchestrator، منتقد
  skills/      رجیستری مهارتها و کاتالوگ شواهد
  channels/    تلگرام و بله
  web/         تمپلیتها و فایلهای استاتیک
tests/         واحد، یکپارچگی، امنیت، E2E
migrations/    Alembic
docs/          مستندات و ADRها
scripts/       اسکریپتهای ویندوز/لینوکس
deploy/        systemd، nginx، بکآپ
```

## عیبیابی

| مشکل | راهحل |
|---|---|
| `no such table: ...` | `alembic upgrade head` اجرا کنید |
| 403 `csrf_failed` | هدر `X-CSRF-Token` را از `/api/v1/auth/me` بگیرید |
| 401 بعد از ریاستارت | `SECRET_KEY` ثابت در `.env` قرار دهید (در غیر اینصورت فایل `.romka_dev_secret` ساخته میشود) |
| 429 | محدودیت نرخ؛ `RATE_LIMIT_PER_MINUTE` را موقتاً بالا ببرید |
| خطای RTL/فونت | از فونت Vazirmatn/IRANSans روی سیستم استفاده کنید؛ فونت جایگزین Segoe UI/Tahoma است |
