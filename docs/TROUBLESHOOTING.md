# عیب‌یابی — خطاهای رایج و ابزار تشخیص

این سند جزئیات تشخیص را نگه می‌دارد تا [`START_HERE.md`](../START_HERE.md) فقط مسیر
نصب باشد. اگر صفحهٔ مرورگر چیزی نبود که باید باشد، اول از همه این را اجرا کنید:

```powershell
.venv\Scripts\python.exe scripts\doctor.py      # ویندوز — فقط نسخهٔ کامل
```
```bash
.venv/bin/python scripts/doctor.py                 # لینوکس/مک
```

این ابزار بدون هیچ کتابخانهٔ خارجی کار می‌کند (حتی وقتی نصب خراب است) و می‌گوید:
Python/venv سالم است یا نه، وابستگی‌ها نصب‌اند یا نه، دیتابیس مهاجرت شده یا نه، و
**چه برنامه‌ای روی پورت گوش می‌دهد**.

> نسخهٔ `*-core.zip` این فایل را ندارد (عمداً، برای آنتی‌ویروس). در آن نسخه اگر
> پورت اشغال باشد، `run_dev` با پیام روشن متوقف می‌شود؛ برنامهٔ مزاحم را ببندید یا
> `-Port 8010` بدهید.

## جدول خطاها

| خطا | راه‌حل |
|---|---|
| `python` شناخته نمی‌شود | Python را با گزینهٔ «Add to PATH» نصب کنید یا `py -3.11 scripts\setup.ps1` |
| `Python 3.11+ not found` در حالی که پایتون نصب است | اول نسخه را ببینید: `python --version` و `py --list`. اگر ۳٫۱۱ یا جدیدتر بود، مسیر واقعی را بدهید: `.\scripts\setup.ps1 -PythonExe "C:\Python313\python.exe"`. نسخهٔ ۰٫۲٫۸ این حالت را خودش تشخیص می‌دهد (قبل از آن، نسخهٔ ۳٫۱۳/۳٫۱۴ رد می‌شد) |
| `Activate.ps1 cannot be loaded` / `running scripts is disabled` | `Get-ChildItem *.zip \| Unblock-File` و سپس `powershell -NoProfile -ExecutionPolicy RemoteSigned -File .\scripts\setup.ps1` |
| `Port 8000 already in use` | `.\scripts\run_dev.ps1 -Port 8010` (یا `PORT=8010 ./scripts/run_dev.sh`) |
| صفحهٔ `Error code: 404 · File not found · Nothing matches the given URI` | سرور دیگری روی همان پورت است — بخش بعدی |
| `The '<' operator is reserved for future use` | `.\scripts\run_dev.ps1 -FreePort` یا `-Port 8010` |
| `no such table` | `alembic upgrade head` (اسکریپت setup خودش انجام می‌دهد) |
| `failed to locate pyvenv.cfg` | `.venv` نیمه‌کاره مانده (اغلب بعد از پاک‌کردن پوشه یا قطع نصب). از ۰٫۲٫۱۰ خود `setup` تشخیص می‌دهد و می‌سازد؛ دستی: `.\scripts\setup.ps1 -RecreateVenv` (لینوکس: `RECREATE_VENV=1 ./scripts/setup.sh`) |
| `dependency installation failed` | متن خطای `pip` بالاتر را ببینید: شبکه → `$env:PIP_INDEX_URL="https://mirror-pypi.runflare.com/simple"`؛ venv خراب → `-RecreateVenv` |
| ورود دمو ناموفق | `ROMKA_AUTO_DEMO=true` و `ENVIRONMENT=development` باشد |
| `Connection refused` روی `127.0.0.1:8000` | سرور بالا نیست؛ `.\scripts\run_dev.ps1` را اجرا کنید |
| `500` هنگام ثبت‌نام | `docs/STATUS.md` بخش باگ‌های باز؛ لاگ `logs/` را ببینید |

## خطای `404 File not found · Nothing matches the given URI`

این صفحه **از ROMKA نیست**. امضای سرور فایل سادهٔ پایتون (`python -m http.server`)
یا CherryPy است. ROMKA برای مسیر ناشناس JSON برمی‌گرداند:
`{"ok":false,"error":{"code":"http_error",...}}` و هدرش `server: uvicorn` است.

**علت:** پورت در اختیار سرور دیگری است (اغلب یک `python -m http.server` که از قبل
باز مانده)، پس uvicorn نتوانسته bind شود و شما به همان سرور قدیمی وصل می‌شوید.

**راه‌حل (بدون تایپ هیچ PID):**

```powershell
# ۱) ببینید چه چیزی پورت را گرفته
.venv\Scripts\python.exe scripts\doctor.py --only port --port 8000

# ۲) بگذارید خودِ ابزار پورت را آزاد کند (قبلش تأیید می‌گیرد)
.venv\Scripts\python.exe scripts\doctor.py --only port --port 8000 --stop-owner

# ۳) یا یک‌مرحله‌ای / یا پورت دیگر
.\scripts\run_dev.ps1 -FreePort
.\scripts\run_dev.ps1 -Port 8010
```

> ⚠️ **در PowerShell هرگز `taskkill /PID <PID> /F` را تایپ نکنید.** کاراکتر `<`
> عملگر ریدایرکت است و این خطا را می‌دهد:
> `The '<' operator is reserved for future use.`
> اگر خودتان می‌خواهید صاحب پورت را پیدا کنید، شکل درست این است:
>
> ```powershell
> $ownerPid = (Get-NetTCPConnection -LocalPort 8000 -State Listen).OwningProcess
> Stop-Process -Id $ownerPid -Force
> ```
>
> (نام متغیر `$ownerPid` است چون `$PID` در PowerShell متغیر خودکارِ «شناسهٔ همین
> نشست» است و قابل مقداردهی نیست.) روش بدون وابستگی:
> `netstat -ano | Select-String ":8000"` و بعد `taskkill /PID 12345 /F` با **عدد
> واقعی** به‌جای placeholder.

از نسخهٔ ۰٫۲٫۱، `run_dev.ps1` و `run_dev.sh` **قبل از شروع** پورت را بررسی می‌کنند:
اگر ROMKA از قبل بالا باشد فقط مرورگر را باز می‌کنند، و اگر برنامهٔ دیگری آن را گرفته
باشد با پیام روشن متوقف می‌شوند («Nothing was started»).

بررسی این‌که پاسخ از ROMKA است:

```powershell
curl.exe -i http://127.0.0.1:8000/api/v1/health
```

باید هدر `server: uvicorn` و بدنهٔ `{"ok":true,"status":"healthy",...}` ببینید. اگر
هدر `SimpleHTTP` دیدید، سرور دیگری روی پورت است — بخش بالا.

## آنتی‌ویروس

کامل در [`ANTIVIRUS.md`](ANTIVIRUS.md): چرا هشدار می‌گیرید، چطور هش را با
`CHECKSUMS.txt` بسنجید، چطور گزارش Defender را رمزگشایی کنید، و چطور مثبت کاذب را
به Microsoft گزارش دهید.
