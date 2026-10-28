# START HERE — ROMKA v0.2.4

این بسته، نسخهٔ کامل و قابل اجرای ROMKA روی سیستم خودتان است. هیچ کلید API و هیچ
توکنی داخل بسته نیست؛ همهٔ فایل‌های حساس (`romka.db`، `.env`، `.romka_dev_secret`)
عمداً حذف شده‌اند و اولین اجرا آن‌ها را خودش می‌سازد.

---

## گزینهٔ ۱ — ویندوز (یک‌کلیکی)

پیش‌نیاز: **Python 3.11 یا 3.12** از <https://www.python.org/downloads/windows/>
(در نصب، تیک `Add python.exe to PATH` را بزنید).

1. آرشیو را در درایو `C:\` خارج کنید؛ خودِ zip یک پوشهٔ `romka` می‌سازد
   (`Expand-Archive romka-v0.2.4.zip -DestinationPath C:\`) — مسیر با فاصله و حروف
   فارسی نباشد.
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
# عیب‌یابی:  .venv\Scripts\python.exe scripts\doctor.py   (فقط در نسخهٔ کامل؛ Core این فایل را ندارد)
# ویندوز:  .\scripts\run_tests.ps1
# لینوکس:  ./scripts/setup.sh --test-only   یا:  . .venv/bin/activate && pytest -q
```

انتظار: **۱۵۰ تست عبور می‌کند** (بدون هیچ سرویس خارجی و بدون کلید API).

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

## اگر ویندوز/آنتی‌ویروس هشدار «ویروس» داد

بسته **هیچ فایل اجرایی (`.exe`/`.dll`) ندارد**؛ ۱۳۰ فایل متنی پایتون است. هشدار معمولاً
یکی از این سه است: (۱) پیام SmartScreen برای فایل بدون امضای دیجیتال، (۲) هیوریستیک روی
دو ابزار کمکی در نسخهٔ کامل (`doctor.py` که پروسهٔ مزاحم را می‌بندد و
`verify_provider.py` که کلید API می‌خواند)، (۳) سیاست PowerShell برای اجرای اسکریپت.

**راه‌حل‌ها به‌ترتیب اولویت:**

1. **هش را بررسی کنید** (فایل `.sha256` کنار آرشیو):
   ```powershell
   Get-FileHash .\romka-v0.2.4.zip -Algorithm SHA256
   Get-Content .\romka-v0.2.4.zip.sha256
   ```
2. **نسخهٔ Core را بگیرید** — بدون `doctor.py`، بدون `verify_provider.py`، بدون `deploy/`:
   `downloads/romka-v0.2.4-core.zip` (همهٔ قابلیت‌های اصلی را دارد؛ فقط پورت را خودش
   آزاد نمی‌کند و اگر اشغال باشد با پیام روشن متوقف می‌شود).
3. **بهترین راه:** خودتان از منبع بسازید — `git clone` و بعد
   `python scripts/build_release.py --version 0.2.4 --sha256-file`؛ هش باید یکی باشد.
4. برچسب اینترنت را بعد از تأیید هش بردارید: `Unblock-File .\romka-v0.2.4.zip`
5. گزارش مثبت کاذب: <https://www.microsoft.com/en-us/wdsi/filesubmission>

جزئیات کامل و روش گزارش به هر سازنده: [`docs/ANTIVIRUS.md`](docs/ANTIVIRUS.md)

> ⚠️ آنتی‌ویروس را خاموش نکنید. اگر ناچار شدید، فقط پوشهٔ پروژه را استثنا کنید و آن هم
> بعد از تأیید هش و خواندن کد.

## عیب‌یابی سریع (ابزار داخلی)

اگر صفحهٔ مرورگر آن‌چیزی نبود که باید باشد، اول این را اجرا کنید:

```powershell
.venv\Scripts\python.exe scripts\doctor.py      # ویندوز — فقط نسخهٔ کامل
```
```bash
.venv/bin/python scripts/doctor.py                 # لینوکس/مک
```

این ابزار بدون هیچ کتابخانهٔ خارجی کار می‌کند (حتی وقتی نصب خراب است) و می‌گوید:
Python/venv سالم است یا نه، وابستگی‌ها نصب‌اند یا نه، دیتابیس مهاجرت شده یا نه، و
**چه برنامه‌ای روی پورت گوش می‌دهد**.

### ⚠️ خطای «Error code: 404 · Message: File not found · Nothing matches the given URI»

این صفحه **از ROMKA نیست**. امضای سرور فایل سادهٔ پایتون (`python -m http.server`)
یا CherryPy است. ROMKA برای مسیر ناشناس، JSON برمی‌گرداند:
`{"ok":false,"error":{"code":"http_error",...}}` و هدرش `server: uvicorn` است.

**علت:** پورت شما در اختیار یک سرور دیگر است (اغلب یک `python -m http.server` که از
قبل باز مانده)، پس uvicorn نتوانسته bind شود و شما به همان سرور قدیمی وصل می‌شوید.

**راه‌حل (ساده‌ترین راه — هیچ PIDای تایپ نکنید):**

```powershell
# ۱) ببینید چه چیزی پورت را گرفته (نام برنامه و PID را نشان می‌دهد)
.venv\Scripts\python.exe scripts\doctor.py --only port --port 8000

# ۲) بگذارید خودِ ابزار پورت را آزاد کند (قبلش تأیید می‌گیرد)
.venv\Scripts\python.exe scripts\doctor.py --only port --port 8000 --stop-owner
#    یا یک‌مرحله‌ای: ROMKA را با آزادسازی پورت بالا بیاورید
.\scripts\run_dev.ps1 -FreePort

# ۳) یا فقط پورت دیگری انتخاب کنید
.\scripts\run_dev.ps1 -Port 8010
```

> ⚠️ **در PowerShell هرگز `taskkill /PID <PID> /F` را تایپ نکنید.** کاراکتر `<`
> در PowerShell عملگر ریدایرکت است و این خطا را می‌دهد:
> `The '<' operator is reserved for future use.` (همان خطایی که دیدید).
> اگر خودتان می‌خواهید PID را پیدا کنید، این شکل درست است:
>
> ```powershell
> $ownerPid = (Get-NetTCPConnection -LocalPort 8000 -State Listen).OwningProcess
> Stop-Process -Id $ownerPid -Force
> ```
>
> (نام متغیر را `$ownerPid` گذاشتیم چون `$PID` در PowerShell متغیر خودکارِ
> «شناسهٔ همین نشست» است و قابل مقداردهی نیست.)
> روش بدون وابستگی: `netstat -ano | Select-String ":8000"` سپس
> `taskkill /PID 12345 /F` با **عدد واقعی** به‌جای `<PID>`.

از نسخهٔ ۰٫۲٫۱، `run_dev.ps1` و `run_dev.sh` **قبل از شروع** پورت را بررسی می‌کنند:
اگر ROMKA از قبل بالا باشد فقط مرورگر را باز می‌کنند، و اگر برنامهٔ دیگری آن را گرفته
باشد با پیام روشن متوقف می‌شوند («Nothing was started») تا دوباره گمراه نشوید.

بررسی این‌که پاسخ از ROMKA است:
```powershell
curl.exe -i http://127.0.0.1:8000/api/v1/health
# باید: server: uvicorn  و  {"ok":true,"status":"healthy","version":"0.2.1"}
```

## اگر خطا گرفتید

| خطا | راه‌حل |
|---|---|
| `python` شناخته نمی‌شود | Python را با گزینهٔ «Add to PATH» نصب کنید یا `py -3.11 scripts\...` |
| `Activate.ps1 cannot be loaded` | `Set-ExecutionPolicy -Scope Process Bypass` |
| `Port 8000 already in use` | `.\scripts\run_dev.ps1 -Port 8010` (یا `PORT=8010 ./scripts/run_dev.sh`) |
| صفحهٔ `Error code: 404 / File not found / Nothing matches the given URI` | سرور دیگری روی پورت است؛ `run_dev.ps1 -FreePort` (پورت را آزاد می‌کند) یا `run_dev.ps1 -Port 8010` |
| `The '<' operator is reserved for future use` | جای `<PID>` عدد بگذارید، یا بهتر: `run_dev.ps1 -FreePort` را اجرا کنید |
| `no such table` | `alembic upgrade head` را اجرا کنید (اسکریپت setup خودش انجام می‌دهد) |
| ورود دمو ناموفق | مطمئن شوید `ROMKA_AUTO_DEMO=true` و `ENVIRONMENT=development` است |

نسخه: `0.2.4` · همهٔ ۱۵۰ تست در زمان ساخت این بسته روی محتوای همین zip اجرا شد.
