# EVALUATION — ارزیابی کیفیت و نتایج واقعی تستها

دستور تکمیل:

```bash
.venv/bin/python -m pytest -q --cov=app --cov-report=term-missing
```

**نتیجه (۲۰۲۶-۱۰-۲۷):** `59 passed` · پوشش کلی **۸۲٪** · ۳٬۰۴۸ خط، ۵۵۱ خط پوششنشده.

## معیارها و محل تست

| معیار | تست | نتیجه |
|---|---|---|
| صحت محاسبات زمانی | `test_planning.py` (۱۲ تست) | ✅ |
| نبود تداخل در برنامه | `validate_plan` + `test_no_overlap_and_validation` | ✅ |
| رعایت محدودیتها (ظرفیت/موعد/وابستگی/بافر) | `test_dependencies_and_deadlines`, `test_capacity_and_unrealistic_warning` | ✅ |
| کیفیت ارجاع به متخصص | `test_selection_caps_at_two_specialists`, سناریو D | ✅ |
| سازگاری پاسخ متخصصها | `test_critic_flags_false_certainty_and_missing_uncertainty` | ✅ |
| صحت ذخیره/بازیابی حافظه | `test_memory.py` (۶ تست) | ✅ |
| کنترل هزینه | `test_ai_router.py` (۷ تست) | ✅ |
| پایداری در برابر قطع سرویس | `test_bounded_retry_and_opt_in_fallback`, سناریو E | ✅ |
| صحت مجوزدهی | `test_security.py` (۷ تست) + `test_channels.py` (۵ تست) | ✅ |
| مجوز اجرای ابزارها | `test_action_engine_requires_approval_for_high_risk` | ✅ |
| تجربه کاربری (مسیرها) | `test_health_and_pages` | ✅ (HTML) |
| مهاجرت دیتابیس | `alembic upgrade head` / `downgrade base` / `upgrade head` | ✅ |
| استقرار VPS / بار / امنیت خارجی | — | ❌ انجام نشد |

## سناریوهای پذیرش (اجرا شده)

| سناریو | تست | نتیجه |
|---|---|---|
| **A** شروع روز | `test_scenario_A_start_of_day` | ✅ ۳ وظیفه + ۲ رویداد، برنامه معتبر، بافر > ۰ |
| **B** تغییر برنامه | `test_scenario_B_replan_after_long_meeting` | ✅ نسخه ۲، کار انجامشده حفظ، تداخل جلسه/ناهار گزارش شد |
| **C** پیشرفت تمرین | `test_scenario_C_workout_progression` | ✅ افزایش تدریجی فقط در شرایط ایمن؛ درد → توقف افزایش |
| **D** پرسش چندتخصصی | `test_scenario_D_multi_specialist_question` | ✅ ≤۲ متخصص، منابع، هشدار، نقد، هزینه |
| **E** قطع ارائهدهنده | `test_scenario_E_provider_outage_degrades_gracefully` | ✅ پاسخ تخریب graceful، پیام ذخیره، بدون حلقه |
| **F** دسترسی غیرمجاز | `test_channels.py`, `test_scenario_F_unauthorized_channel` | ✅ رد + ثبت رخداد + عدم افشا |
| **G** استفاده از حافظه | `test_scenario_G_memory_is_used_not_invented` | ✅ منبع دقیق در پاسخ، قابل مشاهده/حذف |

## تستهای امنیتی

- CSRF، نشست دستکاریشده/منقضی، هش رمز Saltدار؛
- جداسازی داده دو کاربر (`test_cross_user_data_isolation`)؛
- محدودسازی ابزارها و لایههای حافظه از فایل پیکربندی؛
- وتوی مجوز/دسترسی در رجیستری مهارتها؛
- وبحوک جعلی و فرستنده غیرمجاز پیامرسانها؛
- جلوگیری از ارسال داده حساس به ارائهدهنده خارجی.

## محدودیتهای ارزیابی (صادقانه)

- سرویسهای خارجی (LLM، تلگرام، بله) فقط با **mock** تست شدهاند؛ هیچکدام live Verified نیستند.
- ارزیابی کیفیت خروجی AI مبتنی بر قواعد است، نه داوری LLM انسانی؛ دقت واقعی پاسخهای
  تخصصی پس از اتصال مدل و داده واقعی باید سنجیده شود.
- تست بار، تست استرس، پایش منابع و ممیزی نفوذ خارجی انجام نشدهاند.
- پوشش ۸۲٪ بهمعنای بیکیفیتی مطلق نیست؛ مسیرهای نمایشی UI و برخی شاخههای خطا
  پوشش کمتری دارند (گزارش `--cov-report=term-missing` موجود است).
