# START HERE — ROMKA

ROMKA روی سیستم خودتان اجرا می‌شود: یک برنامهٔ وب محلی با دیتابیس SQLite، بدون
سرور بیرونی و بدون ارسال داده به ما. هیچ کلید API و هیچ توکنی داخل این بسته نیست؛
فایل‌های حساس (`romka.db`، `.env`، `.romka_dev_secret`) عمداً حذف شده‌اند و اولین
اجرا خودش آن‌ها را می‌سازد.

بسته فقط **متن** است: پایتون، HTML، CSS، مارک‌داون و اسکریپت‌های نصب. هیچ فایل
اجرایی (`.exe`/`.dll`/`.msi`) داخلش نیست.

---

## ویندوز — چهار قدم

پیش‌نیاز: **Python 3.11، 3.12، 3.13 یا 3.14** از
<https://www.python.org/downloads/windows/> (در نصب، تیک `Add python.exe to PATH` را
بزنید). هر چهار نسخه در CI اجرا می‌شوند؛ همین‌طور نصب‌کنندهٔ ویندوز
(`setup.ps1`) و `run_dev.ps1` روی ویندوز واقعی تست می‌شوند.

**۱) در پوشهٔ `Downloads` (جایی که zip را ذخیره کرده‌اید):**

```powershell
Get-ChildItem *.zip | Unblock-File
Get-ChildItem *.zip | Expand-Archive -DestinationPath C:\
```

خودِ zip یک پوشهٔ `C:\romka` می‌سازد. مسیر با فاصله و حروف فارسی نباشد.

**۲) نصب:**

```powershell
cd C:\romka
.\scripts\setup.ps1
```

**۳) اجرا:**

```powershell
.\scripts\run_dev.ps1
```

**۴) مرورگر:** <http://127.0.0.1:8000/auth>

ورود آزمایشی (فقط محیط توسعه): `demo@romka.local` / `RomkaDemo2026!`
این رمز عمومی است؛ برای سرور واقعی `ROMKA_AUTO_DEMO=false` بگذارید.

---

## لینوکس / مک

```bash
unzip romka.zip && cd romka
./scripts/setup.sh
./scripts/run_dev.sh
```

سپس <http://127.0.0.1:8000/auth> و همان اعتبارنامه.

---

## آیا درست کار می‌کند؟

```powershell
.\scripts\run_tests.ps1          # ویندوز
```
```bash
./scripts/setup.sh --test-only   # لینوکس/مک
```

انتظار: همهٔ تست‌ها عبور می‌کنند، بدون هیچ سرویس خارجی و بدون کلید API.

سالم بودن سرور: <http://127.0.0.1:8000/api/v1/health> باید `{"ok": true}` بدهد.

---

## اگر ویندوز یا آنتی‌ویروس هشدار داد

بسته هیچ فایل اجرایی ندارد، پس هشدار معمولاً از موتور «یادگیری ماشین» آنتی‌ویروس
است (نام‌هایی که به `!ml` ختم می‌شوند) یا پیام SmartScreen برای ناشر بدون امضای
دیجیتال. **هرگز آنتی‌ویروس را خاموش نکنید.** به‌ترتیب:

1. **هش فایل را مقایسه کنید:** عدد خروجی `Get-ChildItem *.zip | Get-FileHash -Algorithm SHA256`
   را با `downloads/CHECKSUMS.txt` در مخزن (در مرورگر، بدون دانلود) بسنجید.
2. **نسخهٔ `*-core.zip` را بگیرید:** همان محصول، بدون `scripts/doctor.py`، بدون
   `scripts/verify_provider.py` و بدون `deploy/` (سه سطحی که هیوریستیک را تحریک می‌کنند).
3. **نصب بدون دانلود:** `git clone` بزنید و `python scripts/build_release.py --sha256-file`
   را اجرا کنید؛ فایل‌های clone‌شده برچسب «از اینترنت» نمی‌گیرند.
4. **گزارش مثبت کاذب** (راه‌حل قطعی برای همه): <https://www.microsoft.com/en-us/wdsi/filesubmission>

شرح کامل، جدول رمزگشایی گزارش Defender و روش گزارش به هر سازنده:
[`docs/ANTIVIRUS.md`](docs/ANTIVIRUS.md)

---

> اگر `failed to locate pyvenv.cfg` دیدید، یعنی `.venv` نیمه‌کاره مانده است:
> `.\scripts\setup.ps1 -RecreateVenv` آن را از نو می‌سازد (نسخهٔ ۰٫۲٫۱۰ خودش
> این کار را خودکار انجام می‌دهد).

## عیب‌یابی

خطاهای رایج (پورت اشغال، `404 File not found` از یک سرور دیگر، پیام‌های PowerShell،
پایگاه‌دادهٔ مهاجرت‌نشده) و ابزار تشخیص داخلی در
[`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) آمده‌اند.

---

## اتصال یک مدل واقعی (اختیاری)

بدون کلید API، برنامه با «موتور محلی قطعی» کار می‌کند: بدون اینترنت، بدون هزینه.
برای پاسخ‌های زبانی واقعی، یک ارائه‌دهندهٔ OpenAI-compatible (مثل GapGPT) را در
`.env` تنظیم کنید. روش گام‌به‌گام و محدودیت‌های هزینه:
[`docs/AI-PROVIDERS.md`](docs/AI-PROVIDERS.md)

---

## چه چیزی واقعاً کار می‌کند (و چه چیزی نه)

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
