# downloads — بسته‌های آمادهٔ نصب (build artifacts)

این پوشه آرشیوهای آمادهٔ اجرا را نگه می‌دارد تا بدون clone و بدون build، قابل
دانلود مستقیم باشند. **این‌ها کد منبع نیستند؛ خروجی `scripts/build_release.py`
هستند** و ساختشان قطعی (deterministic) است، پس بازسازی همان commit باید همان
بایت‌ها و همان sha256 را بدهد.

| فایل | نسخه | sha256 |
|---|---|---|
| `romka-v0.2.0.zip` | 0.2.0 | `43231b84da22a553df6092f1bf95921ba033d84a4eec28cb30152b6be3d7be8a` |

## بازسازی و بررسی

```bash
python scripts/build_release.py --version 0.2.0 --sha256-file
sha256sum release/romka-v0.2.0.zip        # ویندوز: Get-FileHash -Algorithm SHA256
```

## نصب پس از دانلود

```bash
unzip romka-v0.2.0.zip -d romka && cd romka
./scripts/setup.sh && ./scripts/run_dev.sh
```

راهنمای کامل: [`START_HERE.md`](../START_HERE.md) در ریشهٔ همین بسته.
