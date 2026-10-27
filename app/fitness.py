"""Fitness & nutrition domain logic. Estimates, never diagnoses.

Energy: Mifflin-St Jeor (estimate, not a measurement).
Progression: double-progression rules with explicit safety gates. No automatic
load increase when pain, high RPE, missed sets, or insufficient data is present.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BodyInput:
    weight_kg: float
    height_cm: float
    age: int
    sex: str = "male"                   # male | female | unspecified
    activity: str = "moderate"          # sedentary | light | moderate | high
    goal: str = "maintain"              # cut | maintain | bulk
    experience: str = "beginner"
    days_per_week: int = 3
    session_minutes: int = 60
    equipment: list[str] | None = None
    injuries: list[str] | None = None
    food_preferences: list[str] | None = None
    allergies: list[str] | None = None


_ACTIVITY = {"sedentary": 1.2, "light": 1.375, "moderate": 1.55, "high": 1.725}
_GOAL_ADJ = {"cut": -0.18, "maintain": 0.0, "bulk": 0.12}


def estimate_energy(b: BodyInput) -> dict:
    if b.weight_kg <= 0 or b.height_cm <= 0 or b.age <= 0:
        raise ValueError("برای برآورد انرژی، وزن، قد و سن لازم است.")
    # Mifflin-St Jeor. For "unspecified" we average the two sex constants.
    offset = 5 if b.sex == "male" else -161 if b.sex == "female" else -78
    bmr = 10 * b.weight_kg + 6.25 * b.height_cm - 5 * b.age + offset
    tdee = bmr * _ACTIVITY.get(b.activity, 1.55)
    kcal = int(round(tdee * (1 + _GOAL_ADJ.get(b.goal, 0.0)) / 10) * 10)
    protein_g = round(b.weight_kg * (2.0 if b.goal == "cut" else 1.7), 0)
    fat_g = round(kcal * 0.25 / 9, 0)
    carbs_g = max(0, round((kcal - protein_g * 4 - fat_g * 9) / 4, 0))
    return {
        "bmr_kcal": int(round(bmr)), "tdee_kcal": int(round(tdee)), "target_kcal": kcal,
        "protein_g": int(protein_g), "fat_g": int(fat_g), "carbs_g": int(carbs_g),
        "water_ml": int(round(b.weight_kg * 35 / 100) * 100),
        "method": "Mifflin-St Jeor × activity factor (تخمین، نه اندازهگیری قطعی)",
        "disclaimer": "در صورت بیماری، دارو، بارداری، سابقه اختلال خوردن یا علامت هشدار، "
                      "حتماً با پزشک یا متخصص تغذیه مشورت کنید.",
    }


def workout_plan(b: BodyInput) -> dict:
    """Rule-based session template. All numbers are starting points, not prescriptions."""
    eq = set(b.equipment or [])
    has_gym = "gym" in eq or "dumbbell" in eq or "barbell" in eq
    injured_knee = any("زانو" in x or "knee" in x.lower() for x in (b.injuries or []))
    injured_shoulder = any("شانه" in x or "shoulder" in x.lower() for x in (b.injuries or []))
    splits = {
        1: ["full_body"], 2: ["upper", "lower"],
        3: ["push", "pull", "legs"],
        4: ["upper", "lower", "push", "pull"],
        5: ["push", "pull", "legs", "upper", "core"],
        6: ["push", "pull", "legs", "push", "pull", "legs"],
    }
    days = min(max(b.days_per_week, 1), 6)
    names = splits[days]
    sets = 3 if b.experience == "beginner" else 4
    rep_range = "8–12" if b.experience != "advanced" else "6–10"
    rest = 90 if b.experience == "beginner" else 120

    pools = {
        "legs": [
            ("اسکوات با وزن بدن" if not has_gym else "اسکوات با هالتر", "چهارسر / سرینی", "دمبل یا هالتر", "پرس پا", "زانوها همجهت پنجهها"),
            ("لانج" if not injured_knee else "پل سرینی", "سرینی / همسترینگ", "استپ", "ددلیفت رومانیایی", "بدون درد زانو"),
        ],
        "push": [
            ("شنا سوئدی" if not has_gym else "پرس سینه دمبل", "سینه / پشت بازو", "پرس سینه", "پرس بالا سینه", "شانهها را بالا نگه ندارید" if injured_shoulder else "کتلبل"),
            ("پرس سرشانه" if not injured_shoulder else "بالا آوردن جانبی سبک", "شانه", "دمبل", "پرس آرنولدی", "در درد شانه توقف کنید"),
        ],
        "pull": [
            ("بارفیکس کمکی" if has_gym else "روئینگ با کش", "پشت / جلوبازو", "لتپولداون", "روئینگ دمبل", "کشش کامل بدون تاب"),
            ("ددلیفت سبک" if has_gym else "پل سرینی", "همسترینگ / کمر", "کettlebell", "ددلیفت رومانیایی", "ستون فقرات خنثی"),
        ],
        "upper": [
            ("پرس سینه" if has_gym else "شنا سوئدی", "سینه", "دمبل", "پرس دمبل", "کنترل وزنه"),
            ("روئینگ", "پشت", "کش", "لتپولداون", "شانهها پایین"),
        ],
        "lower": [
            ("اسکوات", "چهارسر", "دمبل", "پرس پا", "عمق کنترلشده"),
            ("پل سرینی", "سرینی", "وزن بدن", "هیپ تراست", "بدون قوس کمر"),
        ],
        "core": [("پلانک", "مرکزی", "وزن بدن", "ددباگ", "تنفس منظم")],
        "full_body": [
            ("اسکوات", "پایینتنه", "دمبل", "پرس پا", "زانو همجهت پنجه"),
            ("پرس سینه" if has_gym else "شنا سوئدی", "بالاتنه", "دمبل", "پرس دمبل", "کتلبل"),
            ("روئینگ", "پشت", "کش", "لتپولداون", "بدون تاب"),
        ],
    }
    sessions = []
    for i, name in enumerate(names):
        exercises = []
        for ex, muscles, equip, alt, cue in pools.get(name, pools["full_body"]):
            exercises.append({
                "name": ex, "target_muscles": muscles, "equipment": equip,
                "sets": sets, "reps": rep_range, "rest_seconds": rest,
                "intensity": "RPE 7 (۲–۳ تکرار در ذخیره)", "weight_selection":
                    "وزنهای انتخاب کنید که بتوانید تمام ست را با تکنیک صحیح و RPE ۷ تمام کنید. "
                    "هیچ وزنهای بدون سابقه عملکرد تجویز نمیشود.",
                "technique": cue, "alternative": alt,
                "safety": "درد تیز، سرگیجه یا بیحسی = توقف فوری." ,
                "progression_rule": "فقط اگر تمام ست بدون درد و RPE≤۸ کامل شد، جلسه بعد +۱ تکرار یا ۲.۵٪ وزنه پیشنهاد شود.",
                "deload_rule": "در صورت درد، RPE≥۹، افت عملکرد یا خواب کم، همان بار را حفظ یا کاهش دهید.",
            })
        sessions.append({
            "day": i + 1, "title": f"جلسه {i+1} — {name}", "goal": f"توسعه {name}",
            "warmup": "۵–۸ دقیقه هوازی سبک + ۲ ست گرمکردن وزن بدن",
            "exercises": exercises,
            "cooldown": "۵ دقیقه کشش ملایم",
            "estimated_minutes": b.session_minutes,
        })
    return {"version": "1.0", "days": days, "sessions": sessions,
            "rest_days": 7 - days,
            "note": "برنامه نقطه شروع است و باید بر اساس پاسخ ثبتشده بدن اصلاح شود."}


def progression(log_rows: list[dict]) -> dict:
    """Compare the two most recent logged sessions for one exercise.

    log_rows: [{date, exercise, sets, reps, weight_kg, rpe, pain_flag}, ...]
    """
    if len(log_rows) < 2:
        return {"decision": "hold", "can_increase": False,
                "message": "داده کافی نیست. بدون دو جلسه ثبتشده، افزایش بار مجاز نیست."}
    rows = sorted(log_rows, key=lambda r: str(r.get("date", "")))
    prev, last = rows[-2], rows[-1]
    volume_prev = float(prev.get("sets", 0)) * float(prev.get("reps", 0)) * float(prev.get("weight_kg", 0))
    volume_last = float(last.get("sets", 0)) * float(last.get("reps", 0)) * float(last.get("weight_kg", 0))
    reasons: list[str] = []
    if last.get("pain_flag"):
        reasons.append("درد ثبت شده است.")
    if float(last.get("rpe", 7)) >= 9:
        reasons.append("شدت درکشده ۹ یا بیشتر است.")
    if volume_last < volume_prev * 0.95:
        reasons.append("حجم تمرین نسبت به جلسه قبل افت کرده است.")
    if float(last.get("sets", 0)) < float(last.get("planned_sets", last.get("sets", 0))):
        reasons.append("همه ستهای برنامه کامل نشدهاند.")
    if reasons:
        return {"decision": "hold_or_reduce", "can_increase": False, "reasons": reasons,
                "volume_change_pct": round(100 * (volume_last - volume_prev) / max(volume_prev, 1), 1),
                "message": "افزایش بار متوقف شد. همان بار را حفظ کنید یا در صورت تداوم درد کاهش دهید.",
                "safety": "درد مداوم نیازمند ارزیابی متخصص انسانی است."}
    delta = max(2.5, round(float(last.get("weight_kg", 0)) * 0.025, 1))
    return {"decision": "increase", "can_increase": True,
            "suggested_weight_kg": round(float(last.get("weight_kg", 0)) + delta, 1),
            "alternative": "بهجای وزنه، یک تکرار به هر ست اضافه کنید.",
            "volume_change_pct": round(100 * (volume_last - volume_prev) / max(volume_prev, 1), 1),
            "message": "شرایط افزایش تدریجی فراهم است؛ پیشنهاد، نه دستور. به پاسخ بدن توجه کنید.",
            "safety": "در صورت درد یا افت عملکرد، افزایش را لغو کنید."}


def meal_plan(energy: dict, b: BodyInput) -> dict:
    kcal = energy["target_kcal"]
    p, f, c = energy["protein_g"], energy["fat_g"], energy["carbs_g"]
    allerg = set(b.allergies or [])
    def swap(primary: str, alternative: str) -> str:
        return alternative if primary in allerg else primary
    meals = [
        {"time": "07:30", "title": "صبحانه", "items": [
            {"name": swap("تخممرغ", "توفو"), "amount": "۲ عدد (~۱۰۰گ)", "kcal": 155, "protein_g": 13},
            {"name": "نان سبوسدار", "amount": "۶۰گ", "kcal": 150, "protein_g": 6},
            {"name": "ماست کمچرب", "amount": "۱۵۰گ", "kcal": 90, "protein_g": 9}],
         "alternatives": ["جو دوسر + شیر", "عدسی"]},
        {"time": "13:00", "title": "ناهار", "items": [
            {"name": swap("مرغ", "حبوبات پخته"), "amount": "۱۵۰گ", "kcal": 250, "protein_g": 45},
            {"name": "برنج قهوهای پخته", "amount": "۱۸۰گ", "kcal": 220, "protein_g": 5},
            {"name": "سبزیجات بخارپز", "amount": "۲۰۰گ", "kcal": 70, "protein_g": 4}],
         "alternatives": ["ماهی + سیبزمینی", "خوراک عدس"]},
        {"time": "17:00", "title": "میانوعده پیش از تمرین", "items": [
            {"name": "موز", "amount": "۱ عدد (~۱۲۰گ)", "kcal": 105, "protein_g": 1},
            {"name": swap("پروتئین وی", "ماست یونانی"), "amount": "۱ پیمانه / ۱۵۰گ", "kcal": 120, "protein_g": 20}],
         "alternatives": ["خرما + شیر", "نان + پنیر"]},
        {"time": "20:30", "title": "شام", "items": [
            {"name": swap("گوشت قرمز کمچرب", "تخممرغ یا قارچ"), "amount": "۱۲۰گ", "kcal": 220, "protein_g": 32},
            {"name": "سالاد سبز + روغن زیتون", "amount": "۲۵۰گ + ۱۰گ", "kcal": 130, "protein_g": 4}],
         "alternatives": ["مرغ + کینوآ", "سوپ حبوبات"]},
    ]
    return {"target_kcal": kcal, "macros": {"protein_g": p, "fat_g": f, "carbs_g": c},
            "water_ml": energy["water_ml"], "meals": meals,
            "note": "مقادیر تخمینی و نقطه شروع هستند؛ روند وزن ۲–۳ هفتهای ملاک اصلاح تدریجی است، نه نوسان روزانه.",
            "budget_note": "با بودجه محدود، حبوبات و تخممرغ جایگزینهای کمهزینه پروتئین هستند." if b.food_preferences else "",
            "shopping_list": ["تخممرغ", "نان سبوسدار", "ماست", "مرغ", "برنج قهوهای", "سبزیجات", "موز", "روغن زیتون"]}
