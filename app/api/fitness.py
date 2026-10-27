from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth_context
from app.db.models import FitnessProfile, WorkoutLog
from app.db.session import get_db
from app.fitness import BodyInput, estimate_energy, meal_plan, progression, workout_plan

router = APIRouter(prefix="/fitness", tags=["fitness"])


class AssessmentIn(BaseModel):
    age: int = Field(ge=10, le=100)
    height_cm: float = Field(ge=80, le=250)
    weight_kg: float = Field(ge=20, le=400)
    sex: str = Field(default="male", pattern="^(male|female|unspecified)$")
    activity: str = Field(default="moderate", pattern="^(sedentary|light|moderate|high)$")
    goal: str = Field(default="maintain", pattern="^(cut|maintain|bulk)$")
    experience: str = Field(default="beginner", pattern="^(beginner|intermediate|advanced)$")
    days_per_week: int = Field(default=3, ge=1, le=6)
    session_minutes: int = Field(default=60, ge=20, le=180)
    equipment: list[str] = Field(default_factory=list)
    injuries: list[str] = Field(default_factory=list)
    food_preferences: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)


class LogIn(BaseModel):
    exercise: str = Field(min_length=1, max_length=200)
    sets: int = Field(ge=1, le=20)
    reps: int = Field(ge=1, le=100)
    weight_kg: float = Field(ge=0, le=500)
    rpe: int = Field(default=7, ge=1, le=10)
    pain_flag: bool = False
    planned_sets: int | None = Field(default=None, ge=1, le=20)
    notes: str = Field(default="", max_length=1000)
    day: date | None = Field(default=None, alias="date")


def _body(f: FitnessProfile, payload: AssessmentIn | None = None) -> BodyInput:
    p = payload or AssessmentIn(
        age=f.age or 30, height_cm=f.height_cm or 175, weight_kg=f.weight_kg or 75,
        goal=f.goal or "maintain", experience=f.experience or "beginner",
        days_per_week=f.days_per_week or 3, session_minutes=f.session_minutes or 60,
        equipment=f.equipment or [], injuries=f.injuries or [],
        food_preferences=f.food_preferences or [], allergies=f.allergies or [])
    return BodyInput(weight_kg=p.weight_kg, height_cm=p.height_cm, age=p.age,
                     sex=p.sex, activity=p.activity, goal=p.goal, experience=p.experience,
                     days_per_week=p.days_per_week, session_minutes=p.session_minutes,
                     equipment=p.equipment, injuries=p.injuries,
                     food_preferences=p.food_preferences, allergies=p.allergies)


@router.post("/assessment")
def assessment(p: AssessmentIn, ctx: AuthContext = Depends(get_auth_context),
               db: Session = Depends(get_db)) -> dict:
    f = db.query(FitnessProfile).filter(FitnessProfile.user_id == ctx.user.id).first()
    if f is None:
        f = FitnessProfile(user_id=ctx.user.id)
        db.add(f)
    for k, v in p.model_dump().items():
        setattr(f, k, v)
    db.flush()
    body = _body(f, p)
    energy = estimate_energy(body)
    return {"ok": True, "energy": energy, "workout": workout_plan(body), "meals": meal_plan(energy, body)}


@router.get("/overview")
def overview(ctx: AuthContext = Depends(get_auth_context),
             db: Session = Depends(get_db)) -> dict:
    f = db.query(FitnessProfile).filter(FitnessProfile.user_id == ctx.user.id).first()
    if f is None or f.weight_kg is None:
        return {"ok": True, "ready": False,
                "message": "برای محاسبه برنامه، ابتدا ارزیابی بدنی (سن، قد، وزن) را تکمیل کنید."}
    p = AssessmentIn(age=f.age or 30, height_cm=f.height_cm or 175, weight_kg=f.weight_kg or 75,
                     sex=f.sex or "unspecified", activity=f.activity or "moderate",
                     goal=f.goal, experience=f.experience,
                     days_per_week=f.days_per_week, session_minutes=f.session_minutes,
                     equipment=f.equipment or [], injuries=f.injuries or [],
                     food_preferences=f.food_preferences or [],
                     allergies=f.allergies or [])
    body = _body(f, p)
    energy = estimate_energy(body)
    logs = [{"id": r.id, "date": r.date.isoformat(), "exercise": r.exercise, "sets": r.sets,
             "reps": r.reps, "weight_kg": r.weight_kg, "rpe": r.rpe,
             "pain_flag": r.pain_flag, "notes": r.notes}
            for r in db.query(WorkoutLog).filter(WorkoutLog.user_id == ctx.user.id)
            .order_by(WorkoutLog.date, WorkoutLog.id).all()]
    by_exercise: dict[str, list[dict]] = {}
    for r in logs:
        by_exercise.setdefault(r["exercise"], []).append(r)
    suggestions = {k: progression(v) for k, v in by_exercise.items()}
    return {"ok": True, "ready": True, "energy": energy, "workout": workout_plan(body),
            "meals": meal_plan(energy, body), "logs": logs[-30:],
            "progression": suggestions, "profile": {
                "age": f.age, "height_cm": f.height_cm, "weight_kg": f.weight_kg,
                "goal": f.goal, "experience": f.experience, "days_per_week": f.days_per_week,
                "injuries": f.injuries, "allergies": f.allergies}}


@router.post("/logs")
def add_log(p: LogIn, ctx: AuthContext = Depends(get_auth_context),
            db: Session = Depends(get_db)) -> dict:
    row = WorkoutLog(user_id=ctx.user.id, date=p.day or date.today(),
                     exercise=p.exercise, sets=p.sets, reps=p.reps,
                     weight_kg=p.weight_kg, rpe=p.rpe, pain_flag=p.pain_flag,
                     notes=p.notes)
    db.add(row)
    db.flush()
    rows = [{"date": r.date.isoformat(), "exercise": r.exercise, "sets": r.sets,
             "reps": r.reps, "weight_kg": r.weight_kg, "rpe": r.rpe,
             "pain_flag": r.pain_flag,
             "planned_sets": p.planned_sets if r.id == row.id else r.sets}
            for r in db.query(WorkoutLog).filter(WorkoutLog.user_id == ctx.user.id,
                                                  WorkoutLog.exercise == p.exercise)
            .order_by(WorkoutLog.date, WorkoutLog.id).all()]
    return {"ok": True, "log": {"id": row.id, "exercise": row.exercise},
            "progression": progression(rows)}
