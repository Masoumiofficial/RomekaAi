from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agents.registry import registry
from app.api.deps import AuthContext, get_auth_context
from app.core.action_engine import action_engine
from app.db.models import AgentRun, FixedEvent, Goal, MemoryItem, Plan, Task
from app.db.session import get_db

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("")
def list_agents() -> dict:
    return {"ok": True, "version": registry.version,
            "max_agents_per_request": 2,
            "load_warnings": registry.load_warnings,
            "items": [{"id": a["id"], "name": a["name"], "title": a["title"],
                       "domain": a["domain"], "mission": a["mission"],
                       "limitations": a["limitations"], "allowed_tools": a["allowed_tools"],
                       "allowed_memory_layers": a["allowed_memory_layers"],
                       "quality_criteria": a["quality_criteria"],
                       "escalation_to": a["escalation_to"], "version": a["version"],
                       "active": a["active"], "color": a["color"], "icon": a["icon"],
                       "anatomy_region": a["anatomy_region"]} for a in registry.agents.values()]}


@router.get("/regions")
def regions(ctx: AuthContext = Depends(get_auth_context),
            db: Session = Depends(get_db)) -> dict:
    """Anatomy map backed by REAL counts, never decorative fake numbers."""
    uid = ctx.user.id
    counts = {
        "tasks": db.query(Task).filter(Task.user_id == uid, Task.status != "done").count(),
        "events": db.query(FixedEvent).filter(FixedEvent.user_id == uid).count(),
        "goals": db.query(Goal).filter(Goal.user_id == uid).count(),
        "memory": db.query(MemoryItem).filter(MemoryItem.user_id == uid,
                                              MemoryItem.is_deleted.is_(False)).count(),
        "plans": db.query(Plan).filter(Plan.user_id == uid).count(),
    }
    out = []
    for r in registry.region_map():
        active = [registry.get(a) for a in r["agents"] if registry.get(a) and registry.get(a)["active"]]
        out.append({**r, "active_agents": [a["name"] for a in active],
                    "inactive_count": len(r["agents"]) - len(active),
                    "real_counts": counts})
    return {"ok": True, "regions": out, "counts": counts}


@router.get("/runs")
def runs(limit: int = 30, ctx: AuthContext = Depends(get_auth_context),
         db: Session = Depends(get_db)) -> dict:
    rows = (db.query(AgentRun).filter(AgentRun.user_id == ctx.user.id)
            .order_by(AgentRun.id.desc()).limit(min(limit, 200)).all())
    return {"ok": True, "items": [{"id": r.id, "agent_id": r.agent_id,
                                    "quality_score": r.quality_score, "verdict": r.verdict,
                                    "duration_ms": r.duration_ms,
                                    "created_at": r.created_at.isoformat()} for r in rows]}


@router.get("/tools")
def tools() -> dict:
    return {"ok": True, "items": [{"name": n, "risk": s.risk,
                                    "description": s.description,
                                    "input_schema": s.input_schema}
                                   for n, s in action_engine.tools.items()]}
