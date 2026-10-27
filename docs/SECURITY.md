# SECURITY — اصول، مدل تهدید و کنترلها

> امنیت بخشی از معماری است، نه مرحله آخر. این سند وضعیت **پیادهسازیشده** را توضیح میدهد،
> نه آرمانها. موارد تستنشده صریحاً مشخص شدهاند.

## مدل تهدید (ساده و عملی)

| # | تهدید | کنترل پیادهسازیشده | تست |
|---|---|---|---|
| T1 | دسترسی غیرمجاز به داده کاربر | نشست امضاشده (itsdangerous)، PBKDF2 260k، فیلتر `user_id` در تمام کوئریها | ✅ |
| T2 | CSRF روی عملیات تغییردهنده | توکن دوگانه در کوکی + هدر `X-CSRF-Token`، middleware سراسری | ✅ |
| T3 | SQL Injection | فقط ORM/SQLAlchemy، بدون رشته SQL از ورودی، Pydantic validation | ✅ (طراحی) |
| T4 | XSS | autoescape Jinja2، escape در JS، CSP | ✅ (طراحی) |
| T5 | Prompt Injection از حافظه/اسناد خارجی | دادهها بهعنوان «داده» برچسب میخورند؛ ابزارها allowlist شدهااند؛ منتقد بررسی میکند؛ هیچ کد خارجی اجرا نمیشود | 🟡 جزئی |
| T6 | اجرای اقدام خطرناک توسط ایجنت | `ActionEngine`: ابزار فقط در کد ثبت میشود؛ ریسک بالا نیازمند تأیید صریح؛ idempotency | ✅ |
| T7 | دسترسی نامحدود متخصصها به حافظه | `agent_scope` + لایههای مجاز + وتوی داده حساس (دو دروازه) | ✅ |
| T8 | افشای اسرار | secrets فقط از env؛ `.gitignore`؛ فیلتر redaction در لاگ؛ هدر Authorization هرگز لاگ نمیشود | ✅ |
| T9 | حمله از طریق پیامرسان | تأیید امضای وبحوک، allowlist صریح `channel_identities`، ثبت رخداد | ✅ (mock) |
| T10 | هزینه بیسقف مدل | سقف روز/ماه، سقف تعداد فراخوانی، تشخیص حلقه، محدودیت گام ایجنت، ثبت مصرف | ✅ |
| T11 | حمله Brute force / DoS ساده | محدودیت نرخ درونپردازهای (پنجره لغزنده)، محدودیت طول پیام | 🟡 |
| T12 | نشت داده حساس به LLM خارجی | علامتگذاری `SENSITIVE_MARKER`، `AI_ALLOW_SENSITIVE_TO_EXTERNAL=false` پیشفرض | ✅ |
| T13 | آسیبپذیری وابستگیها | نسخههای محدودشده در `requirements.txt`، SBOM، رد کاندیداهای پردسترسی | 🟡 دستی |
| T14 | شنود شبکه | `COOKIE_SECURE` + HTTPS (الزامی در production) | ❌ محیط هدف |

## کنترلهای پیادهسازیشده

- **رمز عبور:** `pbkdf2_sha256$260000$<salt>$<digest>`، salt تصادفی ۱۶ بایت، مقایسه ثابتزمان.
- **نشست:** `URLSafeTimedSerializer`، `HttpOnly`, `SameSite=Lax`, `Secure` در production،
  حداکثر عمر ۷ روز قابل تنظیم. SECRET_KEY خالی در production → **خطا و توقف startup**.
- **CSRF:** تمام `POST/PUT/PATCH/DELETE` زیر `/api/v1` بهجز ثبتنام/ورود/مهمان/وبحوکها.
- **اعتبارسنجی:** Pydantic v2 در همهٔ ورودیها؛ محدودیت طول پیام ۸۰۰۰ کاراکتر.
- **خطاها:** پوشش واحد (`ok:false / error.code`)؛ استثناءهای داخلی با جزئیات کامل لاگ میشوند
  ولی به کلاینت پیام عمومی برمیگردد (عدم افشای stack trace).
- **هدرها:** `X-Content-Type-Options`, `Referrer-Policy`, CSP (بدون `frame-ancestors` تا
  پیشنمایش iframe شکسته نشود؛ در production باید `frame-ancestors 'none'` اضافه شود).
- **لاگ امنیتی:** `security_events` برای ورود ناموفق، وبحوک نامعتبر و دسترسی غیرمجاز.
- **محدودیت نرخ:** `SlidingWindowRateLimiter` درونپردازهای. **محدودیت:** با چند worker
  مستقل نمیشود؛ در production باید Redis جایگزین شود.
- **ابزارها:** `ActionEngine` فقط ۳ ابزار کمخطر/نیازمند تأیید دارد؛ هیچ ابزاری دسترسی
  به shell، فایل یا شبکه ندارد.

## چکلیست production (انجامشده/انجامنشده)

- [x] `.env.example` و عدم وجود secret در Git
- [x] `SECRET_KEY` الزامی در production
- [x] مهاجرت نسخهدار با مسیر downgrade
- [ ] `ENVIRONMENT=production` + `COOKIE_SECURE=true` روی VPS
- [ ] PostgreSQL بهجای SQLite؛ پشتیبانگیری خودکار و تست restore
- [ ] HTTPS با HSTS؛ افزودن `frame-ancestors 'none'` به CSP
- [ ] Redis برای rate limit و نشستها
- [ ] اسکن وابستگیها (`pip-audit`) در CI
- [ ] ممیزی امنیتی خارجی و تست نفوذ
- [ ] چرخش منظم کلیدها و لاگبرداری متمرکز

## گزارش آسیبپذیری

لطفاً مشکلات امنیتی را مستقیماً به مالک مخزن گزارش دهید (نه issue عمومی) تا پیش از
انتشار عمومی بررسی شوند.
