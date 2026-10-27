# ARCHITECTURE — معماری سیستم

## تصمیم کلیدی: Modular Monolith

یک واحد استقرار (FastAPI + Uvicorn)، ماژولهای داخلی جداشده و مرزهای واضح. دلیل:
تککاربره در فاز اول، اجرای ساده روی ویندوز، استقرار تکرارپذیر روی VPS، تستپذیری بالا،
هزینه نگهداری پایین. میکروسرویسها وقتی معنا دارند که مقیاس و تیم مستقل وجود داشته باشد.

## لایهها

```
┌──────────────────────────────────────────────────────────────┐
│ 1. UI       Jinja2 templates + vanilla JS/CSS (RTL, dark/light)│
│ 2. Channels TelegramAdapter / BaleAdapter (ChannelAdapter)     │
├──────────────────────────────────────────────────────────────┤
│ 3. API      FastAPI /api/v1 · auth · CSRF · rate-limit · errors│
├──────────────────────────────────────────────────────────────┤
│ 4. CORE     CoreOrchestrator · AgentRegistry · Critic          │
│ 5. Engines  Memory · Planning · Action · Fitness               │
│ 6. AI       AIRouter · LocalProvider · OpenAICompatible        │
│ 7. Skills   SkillRegistry · evaluation · license · SBOM        │
├──────────────────────────────────────────────────────────────┤
│ 8. Data     SQLAlchemy 2.x + Alembic → SQLite / PostgreSQL     │
│ 9. Ops      JSON logging w/ redaction · security events · usage│
└──────────────────────────────────────────────────────────────┘
```

### جریان یک پیام گفتوگو

1. API نشست و CSRF را بررسی میکند و پیام کاربر را ذخیره میکند.
2. `CoreOrchestrator` حوزهها را با رتبهبندی کلماتکلیدی تشخیص میدهد؛
   **حداکثر ۲ متخصص** انتخاب میشود (هسته مرکزی رومکا جداگانه نقد میکند).
3. برای هر متخصص، فقط لایههای مجاز حافظه و فقط موارد در `agent_scope` بازیابی میشوند.
4. دادهها بهعنوان «داده» (نه دستور) در prompt قرار میگیرند؛ Prompt Injection در لایه
   حافظه، روتِر و منتقد فیلتر میشود.
5. `AIRouter` بودجه/حلقه/دسترسی/حریم خصوصی را بررسی و فراخوانی را انجام میدهد.
6. `Critic` پاسخ را با قواعد قابل اندازهگیری (قطعیت بیجا، تناقض، عدم قطعیت، تزریق)
   ارزیابی میکند. پیام، منابع، هشدارها و هزینه در DB ذخیره میشوند.

### جریان یک برنامه روزانه

1. ورودی طبیعی فارسی → `parse_natural_request` (هیوریستیک، مستندشده) → وظایف/رویدادها.
2. `planning.service` وظایف، تعهدات ثابت و پروفایل را از DB میخواند.
3. `planning.engine` روی اعداد «دقیقه از نیمهشب» کار میکند (مستقل از timezone):
   ادغام بازههای مشغول → یافتن اسلات آزاد → مرتبسازی توپولوژیک وابستگیها →
   اولویت/موعد/ظرفیت/انرژی → تخصیص + بافر → هشدار غیرواقعبینانه.
4. `validate_plan` بهصورت مستقل برنامه را بازبینی میکند (عدم تداخل، مرزها، مدت،
   وابستگی، موعد، ظرفیت). بدون `valid: true` برنامه نمایش داده نمیشود.
5. نتیجه به همراه `PlanBlocks` نسخهدار ذخیره میشود. `replan` نسخه بعدی میسازد و
   `diff` جابهجاییها را گزارش میدهد.

## مدل داده (۲۱ جدول)

| گروه | جداول |
|---|---|
| هویت | `users`, `user_profiles`, `channel_identities`, `settings` |
| برنامه | `tasks`, `fixed_events`, `plans`, `plan_blocks`, `goals` |
| پروژه | `projects` |
| گفتوگو | `conversations`, `messages`, `agent_runs` |
| حافظه | `memory_items` |
| اجرا | `action_records`, `ai_usage`, `security_events` |
| مهارت | `skills`, `skill_usage` |
| سلامت | `fitness_profiles`, `workout_logs` |

همهٔ جداول حاوی داده شخصی `user_id` دارند و کوئریها در لایه API بر اساس آن فیلتر
میشوند. کلیدهای خارجی با `ON DELETE CASCADE` و `PRAGMA foreign_keys=ON` محافظت میشوند.

## نقاط توسعه

- متخصص جدید: یک ورودی در `app/agents/definitions.json` (بدون تغییر هسته).
- ابزار جدید: ثبت `ToolSpec` در `app/core/action_engine.py` (امنیت در کد، نه کانفیگ).
- ارائهدهنده جدید: پیادهسازی `BaseProvider` و اضافهکردن به `AIRouter`.
- کانال جدید: پیادهسازی `ChannelAdapter` (منطق مشترک تغییر نمیکند).
- دیتابیس: تغییر مدل → `alembic revision --autogenerate` → بررسی → `upgrade head`.

## ADRها

[0001](DECISIONS/0001-modular-monolith.md) · [0002](DECISIONS/0002-database-and-migrations.md) ·
[0003](DECISIONS/0003-deterministic-planning-engine.md) · [0004](DECISIONS/0004-ai-provider-layer.md) ·
[0005](DECISIONS/0005-agent-registry-and-tool-security.md) · [0006](DECISIONS/0006-auth-and-web-ui.md) ·
[0007](DECISIONS/0007-skill-registry-no-auto-execution.md) · [0008](DECISIONS/0008-oss-audit-and-dateutil.md)
