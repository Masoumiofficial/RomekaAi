# START HERE — ROMKA v0.2.0

این بسته، نسخهٔ کامل و قابل اجرای ROMKA روی سیستم خودتان است. هیچ کلید API و هیچ
توکنی داخل بسته نیست؛ همهٔ فایل‌های حساس (`romka.db`، `.env`، `.romka_dev_secret`)
عمداً حذف شده‌اند و اولین اجرا آن‌ها را خودش می‌سازد.

---

## گزینهٔ ۱ — ویندوز (یک‌کلیکی)

پیش‌نیاز: **Python 3.11 یا 3.12** از <https://www.python.org/downloads/windows/>
(در نصب، تیک `Add python.exe to PATH` را بزنید).

1. پوشه را از حالت zip خارج کنید (مثلاً `C:\romka`؛ مسیر با فاصله و حروف فارسی نباشد).
2. در PowerShell داخل همان پوشه اجرا کنید:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\setup.ps1
```

3. سپس برنامه را اجرا کنید:

```powershell
.\scripts\run_dev.ps1
```

4. مرورگر: <http://127.0.0.1:8000/auth>

**ورود آزمایشی (فقط محیط توسعه):**

```
demo@romka.local
RomkaDemo2026!
```

> این رمز عمومی است. برای سرور واقعی `ROMKA_AUTO_DEMO=false` بگذارید.

## گزینهٔ ۲ — لینوکس / مک

```bash
unzip romka-v0.2.0.zip -d romka && cd romka
./scripts/setup.sh
./scripts/run_dev.sh
```

سپس <http://127.0.0.1:8000/auth> و همان اعتبارنامهٔ بالا.

---

## آیا درست کار می‌کند؟

```bash
# ویندوز:  .\scripts\run_tests.ps1
# لینوکس:  ./scripts/setup.sh --test-only   یا:  . .venv/bin/activate && pytest -q
```

انتظار: **۱۲۶ تست عبور می‌کند** (بدون هیچ سرویس خارجی و بدون کلید API).

سالم‌بودن سرور: <http://127.0.0.1:8000/api/v1/health> باید `{"ok": true}` بدهد.

---

## اتصال GapGPT (اختیاری، برای پاسخ‌های زبانی واقعی)

بدون کلید، برنامه با «موتور محلی قطعی» کار می‌کند (بدون اینترنت، بدون هزینه).
برای فعال‌کردن مدل واقعی:

1. کلید را از پنل GapGPT بسازید: <https://gapgpt.app/platform-v2/tokens>
2. در فایل `.env` (کنار همین راهنما) این‌ها را تنظیم کنید:

```env
AI_PRIMARY_PROVIDER=gapgpt
AI_PRIMARY_API_KEY=کلید-شما
GAPGPT_DEFAULT_MODEL=gpt-4o-mini
AI_PRIMARY_PRICE_PER_MILLION_USD=0.6
AI_DAILY_BUDGET_USD=0.50
AI_MONTHLY_BUDGET_USD=10.00
```

3. **قبل از هر چیز** یک تست تک‌درخواستی بزنید (کلید هرگز چاپ نمی‌شود):

```powershell
$env:GAPGPT_API_KEY="کلید-شما"
.\.venv\Scripts\python.exe scripts\verify_provider.py
```

```bash
export GAPGPT_API_KEY="کلید-شما"
.venv/bin/python scripts/verify_provider.py
```

کدهای خروج: `0` = تأیید زنده شد · `2` = پیکربندی ناقص · `3` = خطای ارائه‌دهنده
(۴۰۱/۴۰۴/۴۲۹/شبکه) · `4` = سقف بودجه. اگر `0` گرفتید، سرور را ری‌استارت کنید و در
صفحهٔ **تنظیمات → مدل‌ها و بودجه** دکمهٔ «تست اتصال زنده» را بزنید تا وضعیت
`verified_live` هم ثبت شود.

> نکتهٔ صادقانه: قیمت GapGPT ریالی است؛ عدد `AI_PRIMARY_PRICE_PER_MILLION_USD` فقط
> برای سقف بودجهٔ داخلی است و ادعای صورت‌حساب واقعی نمی‌کند.

---

## دو نکتهٔ مهم دربارهٔ «وارد نشدن»

1. **ایمیل دمو `demo@romka.local` است، نه `owner@romka.local`.** اگر با ایمیل
   `owner@` حساب ساخته‌اید، رمز خودتان را با دمو قاطی نکنید؛ نام کاربری شما همان است
   که ثبت کرده‌اید.
2. اگر برنامه را داخل یک iframe/پیش‌نمایش ابری باز کرده‌اید، مرورگر کوکی سایت ثالث را
   مسدود می‌کند؛ نسخهٔ ۰٫۲٫۰ نشست را با هدر امضاشده هم می‌پذیرد و این مشکل را ندارد.
   در سیستم خودتان (`127.0.0.1`) هیچ محدودیتی نیست.

---

## چه چیزی در این بسته واقعاً کار می‌کند (و چه چیزی نه)

| بخش | وضعیت |
|---|---|
| برنامه‌ریز محاسباتی (ظرفیت، تداخل، بافر، وابستگی، بازبرنامه‌ریزی) | ✅ تست‌شده |
| ثبت «مدت واقعی» + کالیبراسیون تخمین (حداقل ۵ نمونه، clamp ۰٫۶–۱٫۸) | ✅ تست‌شده |
| مرور صبح/شب، بار ۷ روزه، حافظهٔ ۶لایه، ۱۱ متخصص، منتقد مستقل | ✅ تست‌شده |
| امنیت: PBKDF2، نشست امضاشده، CSRF، rate limit، جداسازی کاربران | ✅ تست‌شده |
| GapGPT / OpenAI-compatible | ✅ کد + تست با Mock · ❌ **تأیید زنده نیاز به کلید شما** |
| تلگرام / بله | ✅ آداپتور + وب‌هوک امن · ❌ **بدون توکن، زنده تأیید نشده** |
| PostgreSQL / nginx / HTTPS / بک‌آپ | 📄 مستند و اسکریپت آماده در `deploy/` · ❌ روی VPS شما اجرا نشده |

جزئیات کامل: `docs/STATUS.md` · `docs/SECURITY.md` · `docs/AI-PROVIDERS.md` ·
`docs/DEPLOYMENT.md`

---

## اگر خطا گرفتید

| خطا | راه‌حل |
|---|---|
| `python` شناخته نمی‌شود | Python را با گزینهٔ «Add to PATH» نصب کنید یا `py -3.11 scripts\...` |
| `Activate.ps1 cannot be loaded` | `Set-ExecutionPolicy -Scope Process Bypass` |
| `Port 8000 already in use` | `.\scripts\run_dev.ps1 -Port 8010` (یا `--port 8010`) |
| `no such table` | `alembic upgrade head` را اجرا کنید (اسکریپت setup خودش انجام می‌دهد) |
| ورود دمو ناموفق | مطمئن شوید `ROMKA_AUTO_DEMO=true` و `ENVIRONMENT=development` است |

نسخه: `0.2.0` · همهٔ ۱۲۶ تست در زمان ساخت این بسته روی محتوای همین zip اجرا شد.
