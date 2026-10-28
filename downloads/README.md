# downloads — بسته‌های آمادهٔ نصب (build artifacts)

این پوشه آرشیوهای آمادهٔ اجرا را نگه می‌دارد تا بدون clone و بدون build، قابل
دانلود مستقیم باشند. **این‌ها کد منبع نیستند؛ خروجی `scripts/build_release.py`
هستند** و ساختشان قطعی (deterministic) است، پس بازسازی همان commit باید همان
بایت‌ها و همان sha256 را بدهد.

## کدام فایل را بگیرم؟

| فایل | نسخه | برای چه کسی |
|---|---|---|
| `romka-v0.2.17.zip` | 0.2.17 — **کامل** | نسخهٔ پیش‌فرض؛ همهٔ ابزارها از جمله `doctor.py` |
| `romka-v0.2.17-core.zip` | 0.2.17 — **Core** | اگر آنتی‌ویروس/Defender هشدار داد |
| [`CHECKSUMS.txt`](CHECKSUMS.txt) | — | هش هر دو آرشیو، **بدون نیاز به دانلود** (در مرورگر باز کنید) |
| `romka-v0.2.17.zip.sha256` · `romka-v0.2.17-core.zip.sha256` | — | همان عدد، کنار هر فایل (اختیاری) |

تفاوت دو نسخه فقط سه فایل و یک پوشه است: `scripts/doctor.py` (فهرست پروسه‌ها،
بستن پروسهٔ اشغال‌کنندهٔ پورت)، `scripts/verify_provider.py` (خواندن کلید API از
متغیر محیطی و یک درخواست آزمایشی) و `deploy/` (اسکریپت‌های systemd/nginx/بکاپ).
**هیچ‌کدام برای اجرای ROMKA لازم نیستند**؛ در نسخهٔ Core اگر پورت اشغال باشد،
`run_dev` با پیام روشن متوقف می‌شود و باید خودتان برنامهٔ مزاحم را ببندید.

سابقه: ~~`romka-v0.2.0.zip`~~، ~~`romka-v0.2.1.zip`~~، ~~`romka-v0.2.2.zip`~~،
~~`romka-v0.2.3.zip`~~، ~~`romka-v0.2.4.zip`~~ جایگزین شده‌اند.

> فایل `.sha256` یک **دانلود جدا** است؛ اگر آن را نگرفتید خطای
> `Cannot find path ... .sha256` طبیعی است. برای تأیید، همان عدد را از
> `CHECKSUMS.txt` در مرورگر بخوانید و با `Get-FileHash` مقایسه کنید.
>
> هش داخل خود آرشیو تکرار نمی‌شود؛ مرجع، `CHECKSUMS.txt` است تا با هر بازسازی خودش
> هم‌زمان به‌روز شود.

## بازسازی و بررسی

```bash
python scripts/build_release.py --sha256-file                      # کامل
python scripts/build_release.py --profile core --sha256-file       # Core
sha256sum release/romka-v0.2.17.zip        # ویندوز: Get-FileHash -Algorithm SHA256
```

اگر عدد خروجی با فایل `.sha256` یکی بود، فایل بایتی همان چیزی است که تست شد.

## نصب پس از دانلود

```bash
unzip romka-v0.2.17.zip && cd romka
./scripts/setup.sh && ./scripts/run_dev.sh
```

```powershell
Expand-Archive .\romka-v0.2.17.zip -DestinationPath C:\ ; cd C:\romka
.\scripts\setup.ps1 ; .\scripts\run_dev.ps1
```

## «آنتی‌ویروس می‌گوید ویروس است»

بسته **هیچ فایل اجرایی (`.exe`/`.dll`/`.msi`) ندارد** — فایل‌ها متنی هستند. هشدار
معمولاً SmartScreen برای فایل بدون امضای دیجیتال، یا هیوریستیک روی
`doctor.py`/`verify_provider.py` است. سه گام: (۱) هش را با فایل `.sha256` مقایسه
کنید، (۲) نسخهٔ Core را بگیرید، (۳) بهترین راه: خودتان از منبع بسازید.
راهنمای کامل: [`docs/ANTIVIRUS.md`](../docs/ANTIVIRUS.md).

راهنمای نصب کامل: [`START_HERE.md`](../START_HERE.md) در ریشهٔ همین بسته.
