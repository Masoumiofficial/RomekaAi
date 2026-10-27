# Software Bill of Materials — ROMKA v0.1.0

تولیدشده از `GET /api/v1/skills/sbom` (schema `romka-sbom/1.0`). فقط مؤلفههایی که
وضعیت `active` یا `approved` دارند، «ادغامشده» محسوب میشوند؛ بقیه صرفاً رکورد تحقیقاند.

| مؤلفه | نسخه | مجوز | منبع | وضعیت | ریسک | امتیاز |
|---|---|---|---|---|---|---|
| python-dateutil | 2.9.0.post0 | Apache-2.0 OR BSD-3-Clause (تأیید از LICENSE) | github.com/dateutil/dateutil | approved/integrated | low | 96 |
| FastAPI | 0.162.0 | MIT | github.com/fastapi/fastapi | approved | low | 94 |
| SQLAlchemy + Alembic | 2.1.6 / 1.20.1 | MIT | github.com/sqlalchemy/sqlalchemy | approved | low | 98 |
| Pydantic / pydantic-settings | 2.14.1 / 2.16.1 | MIT | github.com/pydantic/pydantic | dependency | low | — |
| Starlette | 1.10.0 | BSD-3-Clause | github.com/encode/starlette | dependency | low | — |
| Jinja2 | 3.1.6 | BSD-3-Clause | pallets/jinja | dependency | low | — |
| httpx | 0.28.1 | BSD-3-Clause | encode/httpx | dependency | low | — |
| itsdangerous | 2.2.0 | BSD-3-Clause | pallets/itsdangerous | dependency | low | — |
| python-multipart | 0.0.32 | Apache-2.0 | encode/starlette deps | dependency | low | — |
| six | 1.17.0 | MIT | bcannon/six | transitive (dateutil) | low | — |
| pytest / pytest-cov | 8.4.2 / 6.3.0 | MIT | pytest-dev | dev-only | low | — |

**Pinning:** وابستگیها در `requirements.txt` با کران بالا محدود شدهاند، ولی
هش دقیق/commit برای کاندیداهای تحقیقاتی ثبت نشده (`NOT PINNED` در خروجی SBOM).
اقدام بعدی: اضافهکردن `pip-compile --generate-hashes` و `pip-audit` به CI.

**کاندیداهای رد/معوق:** fullcalendar, Chart.js, APScheduler, LangGraph, crewAI, mem0,
MCP servers, anthropics/skills, AutoGen — جزئیات در [OSINT-AUDIT.md](OSINT-AUDIT.md).
