# AI PROVIDERS — وضعیت واقعی پشتیبانی

> قاعده غیرقابل مذاکره: «هیچ API/سرویسی بدون بررسی مستندات و آزمون عملی، پشتیبانی-
> شده اعلام نمیشود.» جدول زیر دقیقاً همین تفکیک را نشان میدهد.

| ارائهدهنده | کد | مستندات | تست زنده | وضعیت |
|---|---|---|---|---|
| موتور محلی قطعی رومکا | ✅ `LocalDeterministicProvider` | داخلی | ✅ بله | **پیشفرض، کاملاً تستشده** |
| OpenAI-compatible (شامل درگاههای سازگار) | ✅ `OpenAICompatibleProvider` | `/chat/completions` استاندارد | ❌ بدون کلید | Implemented / **live Verified: خیر** |
| GPT / GapGPT / سایر درگاههای سازگار | از طریق آداپتور بالا با `AI_PRIMARY_BASE_URL` | — | ❌ | قابل پیکربندی، تأییدنشده |
| Gemini (OpenAI-compat endpoint) | از طریق آداپتور بالا | — | ❌ | قابل پیکربندی، تأییدنشده |
| Claude (API بومی `messages`) | ❌ پیادهسازی نشده | — | ❌ | **Planned** |
| مدل محلی (Ollama / llama.cpp OpenAI-compat) | از طریق آداپتور بالا | — | ❌ | قابل پیکربندی، تأییدنشده |
| Function/Tool calling مدل | ❌ | — | ❌ | Planned؛ ابزارها فعلاً فقط توسط هسته فراخوانی میشوند |
| Streaming | ✅ SSE در `BaseProvider.stream` و `/api/v1/chat/stream` | — | ✅ با موتور محلی | Implemented + Tested |

## پیکربندی

```env
AI_PRIMARY_PROVIDER=openai_compatible
AI_PRIMARY_BASE_URL=https://your-gateway.example/v1
AI_PRIMARY_API_KEY=...          # فقط در .env؛ هرگز در Git
AI_PRIMARY_MODEL=your-model-name
AI_FALLBACK_PROVIDER=openai_compatible   # یا خالی
AI_ALLOW_FALLBACK=true                    # فقط در صورت تأیید حریم خصوصی
AI_DAILY_BUDGET_USD=1.00
AI_MONTHLY_BUDGET_USD=20.00
AI_MAX_RETRIES=1
AI_TIMEOUT_SECONDS=30
AI_MAX_CALLS_PER_REQUEST=3
AI_ALLOW_SENSITIVE_TO_EXTERNAL=false
```

**توجه:** `AI_PRIMARY_BASE_URL` باید به ریشهای اشاره کند که `/chat/completions` زیر آن
قرار دارد. آداپتور فقط از `Authorization: Bearer` و JSON استاندارد استفاده میکند؛
هیچ SDK اختصاصی vendored نشده است.

## معماری لایه

```
CoreOrchestrator ──> AIRouter ──> BaseProvider (interface)
                                   ├─ LocalDeterministicProvider
                                   └─ OpenAICompatibleProvider (httpx)
```

`AIRouter` مسئول:
- انتخاب ارائهدهنده بر اساس `tier` (cheap/standard/premium) و پیکربندی؛
- برآورد هزینه پیش از عملیات و سقف روزانه/ماهانه؛
- `retry` محدود با backoff (فقط خطاهای قابل بازیابی)؛
- fallback فقط با `AI_ALLOW_FALLBACK=true` و همخوانی کلاس حریم خصوصی؛
- تشخیص حلقه (هش درخواست تکراری) و سقف تعداد فراخوانی؛
- ثبت هر تلاش (موفق/ناموفق) در `ai_usage` شامل توکنها، هزینه و تأخیر؛
- جلوگیری از ارسال داده حساس به ارائهدهنده خارجی.

## برآورد هزینه

`PRICE_TABLE` در `app/ai/providers.py` فقط برای **برآورد سقف** است (USD/۱M توکن).
توکنها بهصورت محافظهکارانه (`~۳ کاراکتر/توکن`) تخمین زده میشوند تا کمتر از حد
واقعی برآورد نشود. هزینه واقعی هنگامی که ارائهدهنده `usage` بدهد، از همان استفاده
میشود. اپراتور باید قیمت قرارداد خود را جایگزین کند.

## سناریو E — قطع ارائهدهنده

1. خطا تشخیص و `AIUsage(status=error)` ثبت میشود.
2. حداکثر `AI_MAX_RETRIES+1` تلاش (بدون حلقه بیپایان).
3. در صورت `AI_ALLOW_FALLBACK`، ابتدا ارائهدهنده ثانویه همکلاس، سپس موتور محلی.
4. اگر همه شکست بخورند، هسته پاسخ «تخریب graceful» میدهد: پیام کاربر **ذخیره میشود**
   و هزینه بیسقف ایجاد نمیشود.
5. وضعیت واقعی در `warnings` و `/api/v1/status` قابل مشاهده است.

##Privacy

دادههای `sensitivity=sensitive` هرگز به ارائهدهنده خارجی ارسال نمیشوند، مگر اینکه
هم `RouteContext.allow_sensitive` و هم `AI_ALLOW_SENSITIVE_TO_EXTERNAL` روشن باشند.
حافظهای که به متخصصداده میشود ابتدا بر اساس لایه و `agent_scope` فیلتر میشود.
