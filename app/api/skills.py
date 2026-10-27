from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth_context, require_role
from app.db.models import Skill, SkillUsage
from app.db.session import get_db
from app.skills.registry import PERMISSIVE_LICENSES, evaluate_candidate, sandbox_check, skill_registry

router = APIRouter(prefix="/skills", tags=["skills"])


def _s(r: Skill) -> dict:
    return {"id": r.id, "slug": r.slug, "name": r.name, "domain": r.domain,
            "source_url": r.source_url, "license": r.license_spdx, "version": r.version,
            "pinned_commit": r.source_commit, "risk": r.risk_level,
            "permissions": r.required_permissions, "status": r.status,
            "score": r.score, "evaluation_notes": r.evaluation_notes,
            "test_result": r.test_result, "activated_at": r.activated_at.isoformat() if r.activated_at else None}


@router.get("")
def list_skills(ctx: AuthContext = Depends(get_auth_context),
                db: Session = Depends(get_db)) -> dict:
    rows = db.query(Skill).order_by(Skill.slug).all()
    return {"ok": True, "items": [_s(r) for r in rows], "count": len(rows),
            "permissive_licenses": sorted(PERMISSIVE_LICENSES),
            "audit_date": skill_registry.catalog["audit_date"]}


@router.get("/evaluations")
def evaluations() -> dict:
    return {"ok": True, "source": skill_registry.catalog["source"],
            "audit_date": skill_registry.catalog["audit_date"],
            "items": skill_registry.evaluations()}


@router.get("/sbom")
def sbom(ctx: AuthContext = Depends(get_auth_context),
         db: Session = Depends(get_db)) -> dict:
    return {"ok": True, **skill_registry.sbom(db)}


@router.post("/evaluate")
def evaluate_custom(payload: dict,
                    ctx: AuthContext = Depends(require_role("owner"))) -> dict:
    result = evaluate_candidate(payload)
    result["sandbox"] = sandbox_check(payload)
    return {"ok": True, "evaluation": result}


@router.post("/{slug}/activate")
def activate(slug: str, ctx: AuthContext = Depends(require_role("owner")),
             db: Session = Depends(get_db)) -> dict:
    return {"ok": True, "item": _s(skill_registry.activate(db, slug))}


@router.post("/{slug}/deactivate")
def deactivate(slug: str, payload: dict | None = None,
               ctx: AuthContext = Depends(require_role("owner")),
               db: Session = Depends(get_db)) -> dict:
    return {"ok": True, "item": _s(skill_registry.deactivate(db, slug,
                                                             reason=(payload or {}).get("reason", "")))}


@router.post("/{slug}/rollback")
def rollback(slug: str, ctx: AuthContext = Depends(require_role("owner")),
             db: Session = Depends(get_db)) -> dict:
    return {"ok": True, "item": _s(skill_registry.rollback(db, slug))}


@router.get("/usage")
def usage(ctx: AuthContext = Depends(get_auth_context),
          db: Session = Depends(get_db)) -> dict:
    rows = db.query(SkillUsage).order_by(SkillUsage.id.desc()).limit(100).all()
    return {"ok": True, "items": [{"id": r.id, "skill_id": r.skill_id,
                                    "action": r.action, "detail": r.detail,
                                    "created_at": r.created_at.isoformat()} for r in rows]}
