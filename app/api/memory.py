from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth_context
from app.core.errors import ValidationFailed
from app.db.session import get_db
from app.memory.engine import LAYERS, memory_engine

router = APIRouter(prefix="/memory", tags=["memory"])


class MemoryIn(BaseModel):
    layer: str = Field(pattern="^(session|preference|project|event|agent|retrievable)$")
    key: str = Field(min_length=1, max_length=200)
    value: dict | list | str
    sensitivity: str = Field(default="personal", pattern="^(public|personal|sensitive)$")
    source: str = Field(default="user", pattern="^(user|inferred|import|system|channel)$")
    confidence: str = Field(default="verified", pattern="^(verified|inferred|stale)$")
    tags: list[str] = Field(default_factory=list)
    agent_scope: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None


@router.get("")
def list_memory(layer: str | None = None, q: str | None = None,
                include_sensitive: bool = False,
                ctx: AuthContext = Depends(get_auth_context),
                db: Session = Depends(get_db)) -> dict:
    layers = [layer] if layer else None
    if layers and layer not in LAYERS:
        raise ValidationFailed("لایه نامعتبر است.")
    rows = memory_engine.retrieve(db, user_id=ctx.user.id, query=q, layers=layers,
                                  include_sensitive=include_sensitive, limit=200)
    return {"ok": True, "items": [memory_engine.serialize(r) for r in rows],
            "count": len(rows), "layers": list(LAYERS)}


@router.post("")
def create_memory(p: MemoryIn, ctx: AuthContext = Depends(get_auth_context),
                  db: Session = Depends(get_db)) -> dict:
    item = memory_engine.store(
        db, user_id=ctx.user.id, layer=p.layer, key=p.key, value=p.value,
        source=p.source, confidence=p.confidence, sensitivity=p.sensitivity,
        agent_scope=p.agent_scope, tags=p.tags, expires_at=p.expires_at)
    return {"ok": True, "item": memory_engine.serialize(item)}


@router.put("/{item_id}")
def update_memory(item_id: int, payload: dict,
                  ctx: AuthContext = Depends(get_auth_context),
                  db: Session = Depends(get_db)) -> dict:
    if "value" not in payload or not isinstance(payload["value"], dict):
        raise ValidationFailed("فیلد value از نوع object لازم است.")
    item = memory_engine.update(db, user_id=ctx.user.id, item_id=item_id, value=payload["value"])
    return {"ok": True, "item": memory_engine.serialize(item)}


@router.delete("/{item_id}")
def delete_memory(item_id: int, ctx: AuthContext = Depends(get_auth_context),
                  db: Session = Depends(get_db)) -> dict:
    item = memory_engine.forget(db, user_id=ctx.user.id, item_id=item_id)
    return {"ok": True, "deleted": True, "item": memory_engine.serialize(item)}


@router.get("/conflicts")
def conflicts(ctx: AuthContext = Depends(get_auth_context),
              db: Session = Depends(get_db)) -> dict:
    return {"ok": True, "items": memory_engine.conflicts(db, user_id=ctx.user.id)}


@router.get("/export")
def export(ctx: AuthContext = Depends(get_auth_context),
           db: Session = Depends(get_db)) -> dict:
    return {"ok": True, "items": memory_engine.export_all(db, user_id=ctx.user.id)}
