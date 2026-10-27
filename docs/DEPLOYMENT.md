# DEPLOYMENT — استقرار روی VPS لینوکسی

> وضعیت: اسکریپتها و پیکربندیها نوشته شدهاند، ولی روی VPS واقعی اجرا/تأیید نشدهاند.
> پیش از استفاده، مقادیر نمونه (دامنه، کلمه عبور، مسیرها) را تغییر دهید.

## معماری استقرار

```
Internet ──HTTPS──> nginx (443) ──proxy──> uvicorn/gunicorn (127.0.0.1:8000)
                                              │
                                              ├── PostgreSQL (localhost:5432)
                                              └── systemd (restart, logs)
                    cron/systemd timer ──> backup.sh ──> encrypted offsite copy
```

سابدامین سایت شخصی (مثلاً `romka.example.com`) فقط نقطهٔ دسترسی است؛ هسته هیچ
وابستهای به وردپرس یا CMS ندارد. اتصال احتمالی به وردپرس باید از طریق API جداگانه
و با کلید محدودشده انجام شود.

## ۱) پیشنیازها

```bash
sudo apt update && sudo apt install -y python3.11 python3.11-venv nginx postgresql certbot python3-certbot-nginx
sudo -u postgres createuser romka --pwprompt
sudo -u postgres createdb romka -O romka
```

## ۲) کد و محیط

```bash
sudo mkdir -p /opt/romka && sudo chown $USER /opt/romka
git clone https://github.com/Masoumiofficial/RomekaAi.git /opt/romka/app
cd /opt/romka/app
python3.11 -m venv .venv
.venv/bin/pip install -r requirements-prod.txt
cp deploy/env.production.example /opt/romka/.env
chmod 600 /opt/romka/.env
# حتماً SECRET_KEY، DATABASE_URL و COOKIE_SECURE=true را تنظیم کنید
```

## ۳) مهاجرت دیتابیس

```bash
cd /opt/romka/app
set -a; . /opt/romka/.env; set +a
.venv/bin/alembic upgrade head
```

مسیر بازگشت: `alembic downgrade -1` (قبل از هر ارتقا بکآپ بگیرید).

## ۴) سرویس systemd

`deploy/systemd/romka.service` را در `/etc/systemd/system/` قرار دهید:

```bash
sudo cp deploy/systemd/romka.service /etc/systemd/system/romka.service
sudo systemctl daemon-reload
sudo systemctl enable --now romka
sudo systemctl status romka
journalctl -u romka -f
```

## ۵) nginx و HTTPS

```bash
sudo cp deploy/nginx/romka.conf /etc/nginx/sites-available/romka.conf
# دامنه را در فایل جایگزین کنید
sudo ln -s /etc/nginx/sites-available/romka.conf /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d romka.example.com
```

## ۶) بررسی سلامت

```bash
curl -fsS https://romka.example.com/api/v1/health
curl -fsS https://romka.example.com/api/v1/status | jq .runtime_warnings
```

`health` اتصال DB را چک میکند. `status` هشدارهای پیکربندی (SQLite، COOKIE_SECURE،
نبود کلید) را صادقانه لیست میکند.

## ۷) پشتیبانگیری و بازیابی

```bash
sudo cp deploy/backup.sh /usr/local/bin/romka-backup.sh
sudo chmod +x /usr/local/bin/romka-backup.sh
# تایمر روزانه (نمونه)
sudo cp deploy/systemd/romka-backup.timer /etc/systemd/system/
sudo cp deploy/systemd/romka-backup.service /etc/systemd/system/
sudo systemctl enable --now romka-backup.timer
```

**تست restore حتماً انجام شود**: بکآپ را در یک دیتابیس موقت `pg_restore` کنید و
`alembic current` را بررسی کنید. بدون تست restore، بکآپ معتبر نیست.

## ۸) لاگ و پایش

- لاگها: `journalctl -u romka` (JSON با redaction اسرار).
- رخدادهای امنیتی: جدول `security_events` و `GET /api/v1/security-events`.
- مصرف مدل: جدول `ai_usage` و `GET /api/v1/budget`.
- پیشنهاد:پایش ساده (`node_exporter` + alert روی disk/CPU/5xx) در فاز بعد.

## ۹) بهروزرسانی امن

```bash
cd /opt/romka/app
git pull --ff-only
.venv/bin/pip install -r requirements.txt
.venv/bin/alembic upgrade head
sudo systemctl restart romka
curl -fsS https://romka.example.com/api/v1/health
```

## چکلیست قبل از اعلام production

- [ ] `ENVIRONMENT=production`, `SECRET_KEY` قوی, `COOKIE_SECURE=true`
- [ ] PostgreSQL + بکآپ خودکار + **تست restore انجامشده**
- [ ] HTTPS/HSTS و `frame-ancestors 'none'` در CSP
- [ ] `ROMKA_AUTO_DEMO=false` (غیرفعال شدن ورود مهمان)
- [ ] محدودیت نرخ مبتنی بر Redis (فعلاً درونپردازهای است)
- [ ] تست بار و ممیزی امنیتی
- [ ] حذف `.romka_dev_secret` و فایلهای `romka.db` قدیمی
