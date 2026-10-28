"""Layered, scoped memory. Shared memory is NOT unlimited access for all agents.

Layers: session | preference | project | event | agent | retrievable
Confidence: verified | inferred | stale
Sensitivity: public | personal | sensitive
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.ai.router import SENSITIVE_MARKER
from app.core.errors import NotFound, PermissionDenied, ValidationFailed
from app.db.base import utcnow
from app.db.models import MemoryItem

log = logging.getLogger("romka.memory")

LAYERS = ("session", "preference", "project", "event", "agent", "retrievable")
CONFIDENCE = ("verified", "inferred", "stale")
SENSITIVITY = ("public", "personal", "sensitive")
SOURCES = ("user", "inferred", "import", "system", "channel")

_TOKEN = re.compile(r"[\u0600-\u06FF\u0750-\u077F\w]+", re.UNICODE)


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN.findall(text) if len(t) > 1}


class MemoryEngine:
    def store(
        self, db: Session, *, user_id: int, layer: str, key: str, value: dict | str | list,
        source: str = "user", confidence: str = "verified",
        sensitivity: str = "personal", agent_scope: list[str] | None = None,
        tags: list[str] | None = None, expires_at: datetime | None = None,
        supersede: bool = True,
    ) -> MemoryItem:
        if layer not in LAYERS:
            raise ValidationFailed(f"لایه حافظه «{layer}» نامعتبر است.", details={"allowed": list(LAYERS)})
        if confidence not in CONFIDENCE or sensitivity not in SENSITIVITY or source not in SOURCES:
            raise ValidationFailed("یکی از ویژگیهای حافظه نامعتبر است.")
        if not isinstance(key, str) or not 1 <= len(key) <= 200:
            raise ValidationFailed("کلید حافظه نامعتبر است.")
        payload = value if isinstance(value, dict) else {"value": value}
        previous = []
        if supersede:
            previous = (db.query(MemoryItem)
                        .filter(MemoryItem.user_id == user_id, MemoryItem.layer == layer,
                                MemoryItem.key == key, MemoryItem.is_deleted.is_(False))
                        .all())
            for old in previous:
                old.is_deleted = True
                old.confidence = "stale"
        item = MemoryItem(
            user_id=user_id, layer=layer, key=key, value=payload, source=source,
            confidence=confidence, sensitivity=sensitivity,
            agent_scope=agent_scope or [], tags=tags or [], expires_at=expires_at,
        )
        db.add(item)
        db.flush()
        for old in previous:
            old.superseded_by = item.id
        db.flush()
        return item

    def retrieve(
        self, db: Session, *, user_id: int, agent_id: str | None = None,
        layers: list[str] | None = None, query: str | None = None,
        include_sensitive: bool = False, include_inferred: bool = True,
        exclude_keys: set[tuple[str, str]] | None = None, limit: int = 20,
    ) -> list[MemoryItem]:
        """agent_id=None means the user themselves (full access)."""
        now = utcnow()
        rows = (db.query(MemoryItem)
                .filter(MemoryItem.user_id == user_id, MemoryItem.is_deleted.is_(False))
                .all())
        out: list[tuple[float, MemoryItem]] = []
        q_tokens = _tokens(query or "")
        for item in rows:
            if exclude_keys and (item.layer, item.key) in exclude_keys:
                continue
            if item.expires_at is not None:
                exp = item.expires_at
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                if exp <= now:
                    continue
            if layers and item.layer not in layers:
                continue
            if agent_id is not None:
                if item.agent_scope and agent_id not in item.agent_scope:
                    continue
                if item.sensitivity == "sensitive" and not include_sensitive:
                    continue
                # Stale values are never supplied to an agent. Inferences need
                # an explicit request; normal model context does not request them.
                if item.confidence == "stale":
                    continue
                if item.confidence == "inferred" and not include_inferred:
                    continue
            # agent_id=None means the user themselves: they always see their own
            # data (including sensitive items). The sensitive filter above guards
            # AI-agent access only.
            haystack = f"{item.key} {' '.join(item.tags or [])} {json.dumps(item.value, ensure_ascii=False)}"
            score = 1.0
            if q_tokens:
                overlap = len(q_tokens & _tokens(haystack))
                if overlap == 0:
                    continue
                score = float(overlap) / len(q_tokens)
            score += 0.2 if item.confidence == "verified" else 0.0
            score += min(item.created_at.timestamp() / 1e12, 0.01)
            out.append((score, item))
        out.sort(key=lambda pair: (-pair[0], -pair[1].id))
        return [item for _, item in out[:limit]]

    def context_for_agent(
        self, db: Session, *, user_id: int, agent_id: str, query: str,
        allowed_layers: list[str], include_sensitive: bool = False,
    ) -> tuple[str, list[dict], bool]:
        """Returns (prompt-safe text, sources, has_sensitive)."""
        # Ambiguous keys are withheld, not promoted to facts. Conflicts are
        # computed across the owner's active, unexpired records, without placing
        # the suppressed values or sensitive records into the provider prompt.
        blocked = {(c["layer"], c["key"]) for c in self.conflicts(db, user_id=user_id)}
        items = self.retrieve(db, user_id=user_id, agent_id=agent_id, query=query,
                              layers=allowed_layers, include_sensitive=include_sensitive,
                              include_inferred=False, exclude_keys=blocked, limit=8)
        lines: list[str] = []
        sources: list[dict] = []
        has_sensitive = False
        for item in items:
            tag = f"{item.layer}/{item.key} [{item.confidence}, منبع: {item.source}]"
            value = json.dumps(item.value, ensure_ascii=False)
            if item.sensitivity == "sensitive":
                has_sensitive = True
                lines.append(f"{SENSITIVE_MARKER} {tag}: {value}")
            else:
                lines.append(f"- {tag}: {value}")
            sources.append({"id": item.id, "layer": item.layer, "key": item.key,
                            "confidence": item.confidence, "source": item.source,
                            "sensitivity": item.sensitivity})
        return "\n".join(lines), sources, has_sensitive

    def conflicts(self, db: Session, *, user_id: int) -> list[dict]:
        """Detect stale/contradictory records so the core can ASK instead of inventing."""
        rows = (db.query(MemoryItem)
                .filter(MemoryItem.user_id == user_id, MemoryItem.is_deleted.is_(False))
                .all())
        grouped: dict[tuple[str, str], list[MemoryItem]] = {}
        now = utcnow()
        for r in rows:
            exp = r.expires_at
            if exp is not None:
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                if exp <= now:
                    continue
            grouped.setdefault((r.layer, r.key), []).append(r)
        out = []
        for (layer, key), group in grouped.items():
            values = {json.dumps(g.value, sort_keys=True, ensure_ascii=False) for g in group}
            if len(values) > 1 or any(g.confidence != "verified" for g in group):
                out.append({"layer": layer, "key": key, "active_versions": len(group),
                            "distinct_values": len(values),
                            "message": f"داده‌های متناقض، قدیمی یا تأییدنشده برای «{key}» وجود دارد."})
        return out

    def get(self, db: Session, *, user_id: int, item_id: int) -> MemoryItem:
        item = db.query(MemoryItem).filter(MemoryItem.id == item_id).first()
        if item is None or item.is_deleted:
            raise NotFound("مورد حافظه پیدا نشد.")
        if item.user_id != user_id:
            raise PermissionDenied("دسترسی به حافظه کاربر دیگر مجاز نیست.")
        return item

    def update(self, db: Session, *, user_id: int, item_id: int, value: dict) -> MemoryItem:
        item = self.get(db, user_id=user_id, item_id=item_id)
        # Preserve the original row and permissions; editing one conflicted
        # record must not silently supersede unrelated active versions.
        updated = MemoryItem(user_id=user_id, layer=item.layer, key=item.key,
                             value=value, source="user", confidence="verified",
                             sensitivity=item.sensitivity, agent_scope=list(item.agent_scope or []),
                             tags=list(item.tags or []), expires_at=item.expires_at)
        db.add(updated)
        db.flush()
        item.is_deleted = True
        item.confidence = "stale"
        item.superseded_by = updated.id
        db.flush()
        return updated

    def forget(self, db: Session, *, user_id: int, item_id: int) -> MemoryItem:
        item = self.get(db, user_id=user_id, item_id=item_id)
        item.is_deleted = True
        db.flush()
        return item

    def export_all(self, db: Session, *, user_id: int) -> list[dict]:
        return [self.serialize(i) for i in
                db.query(MemoryItem).filter(MemoryItem.user_id == user_id).order_by(MemoryItem.id).all()]

    @staticmethod
    def serialize(item: MemoryItem) -> dict:
        return {
            "id": item.id, "layer": item.layer, "key": item.key, "value": item.value,
            "source": item.source, "confidence": item.confidence,
            "sensitivity": item.sensitivity, "agent_scope": item.agent_scope,
            "tags": item.tags, "created_at": item.created_at.isoformat(),
            "expires_at": item.expires_at.isoformat() if item.expires_at else None,
            "superseded_by": item.superseded_by, "is_deleted": item.is_deleted,
        }


memory_engine = MemoryEngine()
