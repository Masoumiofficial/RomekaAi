from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agents.orchestrator import CoreOrchestrator
from app.api.deps import AuthContext, get_auth_context
from app.config import Settings, get_settings
from app.core.errors import NotFound
from app.db.models import Conversation, Message
from app.db.session import get_db

router = APIRouter(prefix="/chat", tags=["chat"])


class SendIn(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    conversation_id: int | None = Field(default=None, gt=0)
    include_history: bool = False  # explicit consent, off by default


@router.get("/conversations")
def conversations(ctx: AuthContext = Depends(get_auth_context),
                  db: Session = Depends(get_db)) -> dict:
    rows = (db.query(Conversation).filter(Conversation.user_id == ctx.user.id)
            .order_by(Conversation.created_at.desc()).limit(50).all())
    return {"ok": True, "items": [{"id": r.id, "title": r.title,
                                    "created_at": r.created_at.isoformat()} for r in rows]}


@router.get("/conversations/{conversation_id}/messages")
def messages(conversation_id: int, ctx: AuthContext = Depends(get_auth_context),
             db: Session = Depends(get_db)) -> dict:
    conv = (db.query(Conversation).filter(Conversation.id == conversation_id,
                                          Conversation.user_id == ctx.user.id).first())
    if conv is None:
        raise NotFound("گفتوگو پیدا نشد.")
    rows = (db.query(Message).filter(Message.conversation_id == conv.id)
            .order_by(Message.id).all())
    return {"ok": True, "items": [{
        "id": r.id, "role": r.role, "content": r.content,
        "active_agent_ids": r.active_agent_ids, "sources": r.sources,
        "warnings": r.warnings, "confidence": r.confidence,
        "created_at": r.created_at.isoformat()} for r in rows]}


@router.post("/send")
def send(p: SendIn, ctx: AuthContext = Depends(get_auth_context),
         db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> dict:
    core = CoreOrchestrator(db, user_id=ctx.user.id, settings=settings)
    return core.handle(p.text, conversation_id=p.conversation_id, include_history=p.include_history)


@router.post("/stream")
def stream(p: SendIn, ctx: AuthContext = Depends(get_auth_context),
           db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> StreamingResponse:
    core = CoreOrchestrator(db, user_id=ctx.user.id, settings=settings)

    # Validate before starting the response; streaming generators run after the
    # status line is sent and cannot turn a late exception into an HTTP 404.
    if p.conversation_id is not None:
        core._conversation(p.conversation_id)

    def gen():
        for event in core.stream(p.text, conversation_id=p.conversation_id,
                                 include_history=p.include_history):
            yield f"event: {event['event']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
