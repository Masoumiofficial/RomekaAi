# ROMKA

**Personal Intelligence. One Connected Life.**

رومکا یک سیستمعامل شخصی است که اهداف، زمان، بدن، ذهن، پروژهها و تصمیمهای شما را
در یک سیستم واحد به هم وصل میکند. هدف نهایی ساده و سختگیرانه است:

> اطلاعاتتان را ثبت کنید → برنامه بگیرید → در زندگی واقعی اجرا کنید → نتیجه را گزارش دهید →
> برنامه بعدی بر اساس **واقعیت** ساخته شود، نه حدس.

این مخزن نتیجهٔ «فاز صفر تا هستهٔ قابلاستفاده» است. برنامهنویسی بر اساس یک **موتور
محاسباتی واقعی** انجام میشود، نه متن تولیدشده توسط مدل زبانی.

---

## دانلود بستهٔ آماده (بدون clone)

| | |
|---|---|
| **آرشیو کامل** | [`downloads/romka-v0.2.7.zip`](https://github.com/Masoumiofficial/RomekaAi/raw/arena/4ebd498f-romekaai/downloads/romka-v0.2.7.zip) |
| **نسخهٔ Core (دوست آنتی‌ویروس)** | [`downloads/romka-v0.2.7-core.zip`](https://github.com/Masoumiofficial/RomekaAi/raw/arena/4ebd498f-romekaai/downloads/romka-v0.2.7-core.zip) |
| **چک‌سام هر دو** | [`downloads/CHECKSUMS.txt`](https://github.com/Masoumiofficial/RomekaAi/blob/arena/4ebd498f-romekaai/downloads/CHECKSUMS.txt) (یک فایل، بدون دانلود) |
| **راهنمای نصب** | [`START_HERE.md`](START_HERE.md) |

```bash
# ویندوز (PowerShell):  Expand-Archive romka-v0.2.7.zip -DestinationPath C:\ ; cd C:\romka
unzip romka-v0.2.7.zip && cd romka        # خود آرشیو پوشهٔ romka را می‌سازد
./scripts/setup.sh && ./scripts/run_dev.sh      # ویندوز: .\scripts\setup.ps1 و .\scripts\run_dev.ps1
```

سپس <http://127.0.0.1:8000/auth> — ورود آزمایشی (فقط توسعه):
`demo@romka.local` / `RomkaDemo2026!`

> اگر ویندوز هشدار «ویروس» داد، اول `docs/ANTIVIRUS.md` را بخوانید: بسته هیچ `.exe`
> ندارد و هش معمولاً SmartScreen یا هیوریستیک است؛ نسخهٔ Core یا ساخت از منبع، مسیر امن است.
>
> این آرشیو همان بایتی است که از پوشهٔ خالی استخراج، نصب و تست شد. هش معتبر همیشه
> در فایل `downloads/CHECKSUMS.txt` کنار خود آرشیو است (چون هر تغییر
> مستندات هش را عوض می‌کند، عدد در متن‌ها تکرار نمی‌شود). ساختش تکرارپذیر است:
> `python scripts/build_release.py`. اگر مرورگر صفحهٔ
> `404 File not found` نشان داد، یعنی سرور دیگری روی پورت است: `python scripts/doctor.py`.

---

## وضعیت واقعی (۲۸ اکتبر ۲۰۲۶)

| بخش | وضعیت | توضیح |
|---|---|---|
| مخزن اولیه | ✅ بررسی شد | فقط `README.md` با یک خط؛ بدون کد، بدون وابستگی |
| Foundation (DB، مهاجرت، احراز هویت، امنیت، لاگ) | ✅ Implemented + Tested | ۲۲ جدول، Alembic (۲ مهاجرت)، نشست امضاشده + هدر Bearer، CSRF، PBKDF2 |
| ROMKA CORE (گفتوگو، حافظه، مسیریابی، منتقد) | ✅ Implemented + Tested | ۱۱ متخصص، حافظهٔ لایهای با دامنه دسترسی |
| Life Planner | ✅ Implemented + Tested | زمانبندی مبتنی بر محدودیت، بافر، وابستگی، بازبرنامهریزی |
| Fitness & Nutrition | ✅ Implemented + Tested (پایه) | تخمین انرژی، برنامه تمرین/غذا، منطق پیشرفت ایمن |
| Projects / Business | ✅ Implemented + Tested | پروژهها، اهداف، تصمیمها، شاخص پیشرفت واقعی |
| Skill Intelligence (بخش ۲۱) | ✅ Implemented + Tested | رجیستری ارزیابی، مجوز، SBOM، فعالسازی/بازگشت |
| رابط وب (RTL، دارک/لایت، آناتومی تعاملی) | ✅ Implemented + Tested (مسیرها) | SVG بومی، بدون کتابخانه نمودار/CDN |
| Telegram / Bale | ⚠️ Implemented, **live Verified: خیر** | منطق و امنیت تست شده؛ توکن/دسترسی زنده وجود ندارد |
| ارائهدهنده LLM خارجی | ⚠️ Implemented, **live Verified: خیر** | آداپتور OpenAI-compatible نوشته شده؛ بدون کلید تست نشده |
| Claude / Gemini بومی، MCP، صدا، اپ موبایل | ❌ Planned | عمداً در این فاز ساخته نشدند |

**تستها:** ۵۹ تست اجرا و عبور کردهاند؛ پوشش ۸۲٪ (`pytest --cov=app`).
**پیشنمایش زنده:** سرور توسعه روی پورت ۸۰۰۰ در حال اجراست (`/auth` نقطه ورود).

---

## شروع سریع (لینوکس / macOS)

```bash
git clone https://github.com/Masoumiofficial/RomekaAi.git
cd RomekaAi
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp .env.example .env
.venv/bin/alembic upgrade head        # ساخت نسخهدار جداول
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

سپس `http://localhost:8000/auth` را باز کنید. در محیط توسعه دکمهٔ
**«شروع سریع مهمان»** یک حساب ایزوله و بیرمز عبور میسازد. در production غیرفعال است.

### ویندوز (PowerShell)

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
copy .env.example .env
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

دستورهای آماده: `scripts/run_dev.ps1` و `scripts/run_tests.ps1`.

### اجرای تستها

```bash
.venv/bin/python -m pytest -q --cov=app --cov-report=term-missing
```

---

## یک سناریوی واقعی (بدون کلید API)

```
POST /api/v1/planner/intake
{"text":"امروز باید روی انتشار گپینه کار کنم، نویدبان را بررسی کنم،
         یک جلسه کاری دارم، خرید کنم و ساعت شش باشگاه بروم."}
```

خروجی: ۳ وظیفه و ۲ رویداد ثابت ذخیره میشوند، موتور برنامهسازی زمانبندی میسازد،
تداخلها/بافر/ظرفیت بررسی میشود و `plan.validation.valid` قبل از نمایش تأیید میگردد.

---

## معماری در یک نگاه

```
Web (Jinja2 + vanilla JS/CSS, RTL)  ─┐
Telegram / Bale adapters           ─┼─> FastAPI API (auth, CSRF, rate limit)
                                    │        │
                                    │        ├─> ROMKA CORE (intent, agents, critic)
                                    │        ├─> Memory Engine (6 layers, scoped)
                                    │        ├─> Planning Engine (deterministic)
                                    │        ├─> Action Engine (allowlisted tools)
                                    │        ├─> AI Router (budget, retry, fallback)
                                    │        └─> Skill Registry (OSS governance)
                                    └─> SQLAlchemy + Alembic → SQLite / PostgreSQL
```

جزئیات: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

---

## مستندات

| سند | محتوا |
|---|---|
| [PRODUCT](docs/PRODUCT.md) | اهداف، محدوده، هویت برند، چیزهایی که عمداً نساختیم |
| [ARCHITECTURE](docs/ARCHITECTURE.md) | لایهها، جریان داده، مدل دادهها |
| [ROADMAP](docs/ROADMAP.md) | فازها و وضعیت شفاف هرکدام |
| [SECURITY](docs/SECURITY.md) | مدل تهدید و کنترلها |
| [DEPLOYMENT](docs/DEPLOYMENT.md) | استقرار VPS، HTTPS، بکآپ |
| [DEVELOPMENT](docs/DEVELOPMENT.md) | محیط توسعه ویندوز/لینوکس |
| [AI-PROVIDERS](docs/AI-PROVIDERS.md) | وضعیت واقعی ارائهدهندگان |
| [AGENTS](docs/AGENTS.md) | تعریف و مدیریت متخصصها |
| [DATA-PRIVACY](docs/DATA-PRIVACY.md) | دادهها، رضایت، حذف و خروجی |
| [OSINT-AUDIT](docs/OSINT-AUDIT.md) | ممیزی منابع متنباز و SBOM |
| [STATUS](docs/STATUS.md) | **گزارش اول: بررسیها، تصمیمات، تستها، مسدودیتها و اقدام بعدی** |
| [EVALUATION](docs/EVALUATION.md) | نتایج تستها و سناریوهای پذیرش |
| [DECISIONS](docs/DECISIONS/) | ADRهای معماری |

---

## محدودیتهای صادقانه

- موتور AI پیشفرض **محلی و قطعی** است، نه LLM. بدون کلید API محصول کامل کار میکند،
  ولی پاسخهای زبانی محدودتری میدهد.
- اتصال زنده به تلگرام/بله و ارائهدهندههای پولی در این محیط **تأیید نشده** است
  (توکن و دسترسی وجود نداشت). کد و تستهای آنها با mock نوشته شدهاند.
- بار سنگین (load test)، ممیزی امنیتی خارجی و استقرار واقعی روی VPS انجام نشدهاند.
- نمودارها و آناتومی از **داده واقعی** استفاده میکنند؛ اگر دادهای نباشد، عدد ساختگی نشان داده نمیشود.

هیچ قابلیتی صرفاً بهخاطر وجود فایل، «تکمیلشده» اعلام نشده است.
