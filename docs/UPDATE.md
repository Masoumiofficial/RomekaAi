# به‌روزرسانی ROMKA روی سیستم خودتان

این راهنما برای کسی است که ROMKA را قبلاً نصب کرده و حالا نسخهٔ تازه (**۰٫۲٫۲۲**) را
می‌خواهد. همهٔ دستورهای PowerShell همان‌طور که نوشته شده‌اند قابل اجرا هستند — هیچ
توکن `<PLACEHOLDER>` در آن‌ها نیست. مسیر نصب را `C:\romka` فرض می‌کنیم؛ اگر جایی
دیگری نصب شده، همان مسیر را بگذارید.

> **اگر همین حالا ۰٫۲٫۲۱ را دانلود و extract کرده‌اید، همین راهنما را ادامه بدهید.**
> ۰٫۲٫۲۲ یک باگ واقعی در مسیر به‌روزرسانی را می‌بندد: بعد از extract کردن آرشیو روی
> پوشهٔ قدیمی، پایتون می‌توانست کد نسخهٔ قبلی را اجرا کند (پاصفحه نسخهٔ تازه را
> نشان می‌داد ولی برنامه قدیمی کار می‌کرد). نصب ۰٫۲٫۲۲ این وضع را برطرف می‌کند.

---

## ۱) سرور را ببندید

پنجرهٔ `run_dev.ps1` را با `Ctrl+C` یا بستن پنجره متوقف کنید. اگر پنجره‌ای باز
نمانده ولی پیام «address already in use» گرفتید، یک پروسهٔ پنهان پورت ۸۰۰۰ را گرفته
است. بستهٔ کامل (غیر از `-core`) ابزار تشخیص دارد:

```powershell
python scripts/doctor.py --port 8000
```

این دستور فقط می‌گوید چه پروسه‌ای پورت را گرفته و **خودش چیزی را نمی‌بندد**. در بستهٔ
`-core` این فایل نیست و کافی است پنجرهٔ باز ماندهٔ ROMKA را ببندید.

---

## ۲) پشتیبان — این قدم را رد نکنید

```powershell
cd C:\romka
New-Item -ItemType Directory -Force backups | Out-Null
$stamp = Get-Date -Format "yyyy-MM-dd-HHmm"
Copy-Item .env (Join-Path backups ".env-$stamp") -ErrorAction SilentlyContinue
Copy-Item romka.db (Join-Path backups "romka-$stamp.db") -ErrorAction SilentlyContinue
Copy-Item .romka_dev_secret (Join-Path backups ".romka_dev_secret-$stamp") -ErrorAction SilentlyContinue
if (Test-Path data) { Copy-Item data (Join-Path backups "data-$stamp") -Recurse -Force }
Get-ChildItem backups
```

سه فایل `.env`، `romka.db` و `.romka_dev_secret` داخل هیچ zip نیستند، پس با
به‌روزرسانی کدها از دست نمی‌روند — ولی پشتیبان دستی همیشه مطمئن‌تر است.

---

## ۳) گرفتن نسخهٔ تازه

### مسیر الف — با git (امن‌ترین، بدون هشدار Mark-of-the-Web)

فایل git هیچ «برچسب اینترنت‌اندیشه» ندارد، پس آنتی‌ویروس و SmartScreen چیزی
نمی‌گویند. اگر ROMKA را با `git clone` گرفته‌اید:

```powershell
cd C:\romka
git status --short
git fetch origin
git checkout arena/4ebd498f-romekaai
git pull --ff-only origin arena/4ebd498f-romekaai
```

اگر `git status` گفت «not a git repository»، یعنی با zip نصب کرده‌اید؛ بروید سر
مسیر ب.

### مسیر ب — با zip دانلودشده

**الف) بررسی هش** (بعد از دانلود، قبل از باز کردن):

```powershell
cd $env:USERPROFILE\Downloads
Unblock-File .\romka-v0.2.22-core.zip
Get-FileHash -Algorithm SHA256 .\romka-v0.2.22-core.zip
```

خروجی خط دوم را با مقدار کنار `romka-v0.2.22-core.zip` در `downloads/CHECKSUMS.txt`
روی گیت‌هاب مقایسه کنید. **عدد باید مو‌به‌مو یکی باشد.** اگر نخورد، فایل را نصب
نکنید و دوباره دانلود کنید.

**ب) باز کردن روی پوشهٔ قبلی:**

```powershell
Expand-Archive -Force -DestinationPath C:\ .\romka-v0.2.22-core.zip
```

> **مهم — از کجا اجرا می‌کنید؟** این دستور باید از پوشهٔ `Downloads` اجرا شود (همان
> جای خط بالا). اگر از داخل `C:\romka` اجرا کنید، zip یک پوشهٔ تودرتو
> `C:\romka\romka` می‌سازد و **هیچ فایلی جایگزین نمی‌شود** — برنامه همان کد قدیمی را
> اجرا می‌کند و شما فکر می‌کنید به‌روز شده‌اید. بعد از extract این را چک کنید:
>
> ```powershell
> Test-Path C:\romka\romka
> ```
>
> اگر `True` برگرداند، پوشهٔ تودرتو را پاک کنید (`Remove-Item C:\romka\romka -Recurse -Force`)
> و دستور را از `Downloads` دوباره بزنید.

`-Force` فایل‌های کد را جایگزین می‌کند. `.env`، `romka.db`، `.venv` و `data/` داخل
zip نیستند، پس دست‌نخورده می‌مانند.

**ج) اگر بستهٔ کامل گرفته‌اید** (`romka-v0.2.22.zip` بدون `-core`)، دستورها همان‌اند،
فقط نام فایل را عوض کنید:

```powershell
Unblock-File .\romka-v0.2.22.zip
Get-FileHash -Algorithm SHA256 .\romka-v0.2.22.zip
Expand-Archive -Force -DestinationPath C:\ .\romka-v0.2.22.zip
```

---

## ۴) نصب و مهاجرت دیتابیس

```powershell
cd C:\romka
.\scripts\setup.ps1
```

`setup.ps1` چه می‌کند:

1. **بایت‌کد کهنه را پاک می‌کند** (پوشه‌های `__pycache__` و فایل‌های `.pyc`/`.pyo`،
   به‌جز `.venv`). این همان چیزی است که باگ مسیر به‌روزرسانی را می‌بندد.
2. `.venv` سالم است، اگر بود **دوباره نمی‌سازد** (اگر خراب باشد بازمی‌سازد؛ `.env` و
   دیتابیس را دست نمی‌زند).
3. وابستگی‌ها را از `requirements-dev.txt` نصب می‌کند.
4. `.env` **فقط اگر نبود** از `.env.example` می‌سازد؛ تنظیمات شما پاک نمی‌شود.
5. `alembic upgrade head` را اجرا می‌کند؛ این مرحله اسکیمای دیتابیس را به نسخهٔ تازه
   می‌رساند و داده‌های قبلی حفظ می‌شود.
6. آخرین کار، اجرای کل سوییت تست است. اگر قرمز شد، اسکریپت با خطا تمام می‌شود.

اگر pip به‌خاطر شبکه یا SSL شکست خورد (برای کاربران ایران رایج است):

```powershell
$env:PIP_INDEX_URL="https://mirror-pypi.runflare.com/simple"
.\scripts\setup.ps1
```

اگر `.venv` خراب بود و پیام قفل‌بودن گرفت:

```powershell
.\scripts\setup.ps1 -RecreateVenv
```

---

## ۵) آزمون و اجرا

```powershell
cd C:\romka
.\scripts\run_tests.ps1
.\scripts\run_dev.ps1
```

سپس <http://127.0.0.1:8000/auth> — همان `demo@romka.local` / `RomkaDemo2026!`.

---

## ۶) مطمئن شوید واقعاً به‌روز شد

در پایین ستون کناری، کنار «نسخه» باید `v0.2.22` باشد. اگر `v0.2.21` دیدید، مرورگر
از کش فایل‌های CSS/JS قدیمی را دارد: یک بار `Ctrl+Shift+R` بزنید.

دکمهٔ **«گفتگو با رومکا»** باید شکل تازه داشته باشد (حباب با زمان، «در حال نوشتن»،
دکمهٔ پرش به پایین). در **پنل صوتی** پایین صفحه، گزینهٔ «فعال‌سازی با گفتن رومکا»
را می‌بینید؛ پیش‌فرض خاموش است و تا روشنش نکنید میکروفون روشن نمی‌شود.

**اگر قبلاً ۰٫۲٫۲۱ را روی ۰٫۲٫۲۰ extract کرده‌اید** و رفتار برنامه عجیب بود (نسخهٔ
تازه در پاصفحه ولی امکانات تازه کار نکرد)، همین باگ بایت‌کد بود. `setup.ps1` نسخهٔ
جدید آن را پاک می‌کند؛ فقط مرحلهٔ ۳ و ۴ را دوباره انجام دهید.

---

## اگر آنتی‌ویروس هشدار داد

۱) `docs/ANTIVIRUS.md` را بخوانید. بسته هیچ `.exe`/`.dll` ندارد و هش معتبر یعنی
فایل همان بایت‌های منتشرشده است — این «بی‌خطر بودن» را تضمین نمی‌کند ولی نشان
می‌دهد وسط راه تغییر نکرده.

۲) **هرگز آنتی‌ویروس را خاموش نکنید.** مسیر بدون هشدار: `git clone` (مسیر الف) یا
بستهٔ `-core`.

۳) نام دقیق هشدار را نگه دار (ThreatName و ThreatID) و در مخزن گزارش بدهید؛ پاسخ
معمولاً کمتر از ۲۴ ساعت می‌آید.

---

## اگر چیزی خراب شد

- مهاجرت دیتابیس خطا داد: پشتیبان را برگردانید — `romka.db` مرحلهٔ ۲ را به ریشهٔ
  پروژه کپی کنید، بعد `.\scripts\setup.ps1` را دوباره بزنید.
- صفحه باز نمی‌شود یا رفتار عجیب دارد: `docs/TROUBLESHOOTING.md` را ببینید. اگر
  بستهٔ کامل (غیر از `-core`) را نصب کرده‌اید، `python scripts/doctor.py` هم مشکل
  رایج نصب و پورت را نشان می‌دهد.
- می‌خواهید به نسخهٔ قبلی برگردید: پوشهٔ پروژه را عوض کنید (مثلاً
  `git checkout` به همان کامیت قبلی) و `.\scripts\setup.ps1` را بزنید؛ دیتابیس
  مهاجرت‌شده را از پشتیبان برگردانید.
