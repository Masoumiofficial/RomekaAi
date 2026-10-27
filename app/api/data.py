"""Goals, projects and their decisions — the business/project control surface."""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth_context
from app.core.errors import NotFound
from app.db.models import Goal, Project, Task
from app.db.session import get_db

router = APIRouter(prefix="/data", tags=["data"])


class GoalIn(BaseModel):
    title: str = Field(min_length=1, max_length=400)
    horizon: str = Field(default="weekly", pattern="^(daily|weekly|monthly|quarterly|long_term)$")
    priority: int = Field(default=3, ge=1, le=5)
    success_metric: str = Field(default="", max_length=400)
    target_date: date | None = None
    project_id: int | None = None


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    goal_text: str = Field(default="", max_length=1000)
    status: str = Field(default="active", max_length=20)
    priority: int = Field(default=3, ge=1, le=5)
    due_date: date | None = None
    success_metrics: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)


@router.get("/goals")
def list_goals(ctx: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)) -> dict:
    rows = db.query(Goal).filter(Goal.user_id == ctx.user.id).order_by(Goal.priority, Goal.id).all()
    return {"ok": True, "items": [_goal(r) for r in rows], "count": len(rows)}


def _goal(r: Goal) -> dict:
    return {"id": r.id, "title": r.title, "horizon": r.horizon, "priority": r.priority,
            "success_metric": r.success_metric, "status": r.status,
            "target_date": r.target_date.isoformat() if r.target_date else None,
            "project_id": r.project_id}


@router.post("/goals")
def create_goal(p: GoalIn, ctx: AuthContext = Depends(get_auth_context),
                db: Session = Depends(get_db)) -> dict:
    row = Goal(user_id=ctx.user.id, **p.model_dump())
    db.add(row)
    db.flush()
    return {"ok": True, "item": _goal(row)}


@router.delete("/goals/{goal_id}")
def delete_goal(goal_id: int, ctx: AuthContext = Depends(get_auth_context),
                db: Session = Depends(get_db)) -> dict:
    row = db.query(Goal).filter(Goal.id == goal_id, Goal.user_id == ctx.user.id).first()
    if row is None:
        raise NotFound("هدف پیدا نشد.")
    db.delete(row)
    db.flush()
    return {"ok": True}


def _project(r: Project, db: Session) -> dict:
    open_tasks = db.query(Task).filter(Task.project_id == r.id, Task.status != "done").count()
    done_tasks = db.query(Task).filter(Task.project_id == r.id, Task.status == "done").count()
    return {"id": r.id, "name": r.name, "description": r.description, "goal": r.goal_text,
            "status": r.status, "priority": r.priority,
            "due_date": r.due_date.isoformat() if r.due_date else None,
            "success_metrics": r.success_metrics, "blockers": r.blockers,
            "decisions": r.decisions, "open_tasks": open_tasks, "done_tasks": done_tasks,
            "progress_pct": round(100 * done_tasks / (open_tasks + done_tasks)) if (open_tasks + done_tasks) else 0}


@router.get("/projects")
def list_projects(ctx: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)) -> dict:
    rows = db.query(Project).filter(Project.user_id == ctx.user.id).order_by(Project.priority, Project.id).all()
    return {"ok": True, "items": [_project(r, db) for r in rows], "count": len(rows)}


@router.post("/projects")
def create_project(p: ProjectIn, ctx: AuthContext = Depends(get_auth_context),
                   db: Session = Depends(get_db)) -> dict:
    row = Project(user_id=ctx.user.id, **p.model_dump())
    db.add(row)
    db.flush()
    return {"ok": True, "item": _project(row, db)}


@router.post("/projects/{project_id}/decisions")
def add_decision(project_id: int, payload: dict,
                 ctx: AuthContext = Depends(get_auth_context),
                 db: Session = Depends(get_db)) -> dict:
    row = db.query(Project).filter(Project.id == project_id, Project.user_id == ctx.user.id).first()
    if row is None:
        raise NotFound("پروژه پیدا نشد.")
    text = str(payload.get("text", ""))[:500]
    if not text:
        from app.core.errors import ValidationFailed
        raise ValidationFailed("متن تصمیم خالی است.")
    row.decisions = list(row.decisions or []) + [{"text": text, "at": datetime.now().isoformat()}]
    db.flush()
    return {"ok": True, "item": _project(row, db)}
