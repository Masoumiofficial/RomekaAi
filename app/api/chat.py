from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.agents.orchestrator import CoreOrchestrator
from app.api.deps import AuthContext, get_auth_context
from app.config import Settings, get_settings
from app.core.errors import NotFound
from app.db.models import Conversation, Message, MessageFeedback
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
    feedback = {f.message_id: f for f in db.query(MessageFeedback)
                .join(Message, Message.id == MessageFeedback.message_id)
                .filter(Message.conversation_id == conv.id, MessageFeedback.user_id == ctx.user.id).all()}
    return {"ok": True, "items": [{
        "id": r.id, "role": r.role, "content": r.content,
        "feedback": ({"rating": feedback[r.id].rating, "reason": feedback[r.id].reason}
                     if r.id in feedback else None),
        "active_agent_ids": r.active_agent_ids, "sources": r.sources,
        "warnings": r.warnings, "confidence": r.confidence,
        "created_at": r.created_at.isoformat()} for r in rows]}


class FeedbackIn(BaseModel):
    rating: Literal["helpful", "not_helpful"]
    reason: Literal["", "incorrect", "irrelevant", "unclear", "unsafe", "other"] = ""


def _owned_assistant_message(message_id: int, user_id: int, db: Session) -> Message:
    message = (db.query(Message).join(Conversation, Message.conversation_id == Conversation.id)
               .filter(Message.id == message_id, Message.role == "assistant",
                       Conversation.user_id == user_id).first())
    if message is None:
        raise NotFound("پاسخ پیدا نشد.")
    return message


@router.get("/feedback/summary")
def feedback_summary(ctx: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)) -> dict:
    """User's own voluntary ratings, not a model-quality benchmark."""
    counts = dict(db.query(MessageFeedback.rating, func.count(MessageFeedback.id))
                  .filter(MessageFeedback.user_id == ctx.user.id)
                  .group_by(MessageFeedback.rating).all())
    helpful, unhelpful = counts.get("helpful", 0), counts.get("not_helpful", 0)
    return {"ok": True, "helpful": helpful, "not_helpful": unhelpful,
            "total": helpful + unhelpful}


@router.put("/messages/{message_id}/feedback")
def put_feedback(message_id: int, p: FeedbackIn, ctx: AuthContext = Depends(get_auth_context),
                 db: Session = Depends(get_db)) -> dict:
    _owned_assistant_message(message_id, ctx.user.id, db)
    row = (db.query(MessageFeedback).filter(MessageFeedback.user_id == ctx.user.id,
                                             MessageFeedback.message_id == message_id).first())
    if row is None:
        row = MessageFeedback(user_id=ctx.user.id, message_id=message_id, rating=p.rating, reason="")
        db.add(row)
    row.rating = p.rating
    row.reason = p.reason if p.rating == "not_helpful" else ""
    db.flush()
    return {"ok": True, "feedback": {"rating": row.rating, "reason": row.reason}}


@router.delete("/messages/{message_id}/feedback")
def delete_feedback(message_id: int, ctx: AuthContext = Depends(get_auth_context),
                    db: Session = Depends(get_db)) -> dict:
    _owned_assistant_message(message_id, ctx.user.id, db)
    row = (db.query(MessageFeedback).filter(MessageFeedback.user_id == ctx.user.id,
                                             MessageFeedback.message_id == message_id).first())
    if row is not None:
        db.delete(row)
        db.flush()
    return {"ok": True}


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
